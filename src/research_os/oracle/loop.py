"""Bounded autonomous research loop with explicit stop conditions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable

from research_os.oracle.models import ResearchGap


@dataclass(frozen=True)
class LoopLimits:
    max_steps: int = 20
    max_runs: int = 20
    max_candidates: int = 1000
    max_iterations: int = 10
    max_failures: int = 3
    stop_on_indeterminate: bool = True
    stop_on_required_engine_missing: bool = True
    stop_on_evidence_requirement_met: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LoopResult:
    status: str
    iterations: int
    steps: int
    runs: int
    candidates: int
    failures: int
    gaps: tuple[ResearchGap, ...] = ()
    stop_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "iterations": self.iterations, "steps": self.steps, "runs": self.runs, "candidates": self.candidates, "failures": self.failures, "gaps": [gap.to_dict() for gap in self.gaps], "stop_reason": self.stop_reason}


@dataclass(frozen=True)
class CodexLoopTurn:
    iteration: int
    prompt: str
    planning: Any
    execution: dict[str, Any]
    gaps: tuple[ResearchGap, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"iteration": self.iteration, "prompt": self.prompt, "planning": self.planning.to_dict() if hasattr(self.planning, "to_dict") else self.planning, "execution": dict(self.execution), "gaps": [gap.to_dict() for gap in self.gaps]}


@dataclass(frozen=True)
class CodexLoopResult:
    status: str
    iterations: int
    steps: int
    runs: int
    candidates: int
    failures: int
    turns: tuple[CodexLoopTurn, ...] = ()
    gaps: tuple[ResearchGap, ...] = ()
    stop_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "iterations": self.iterations, "steps": self.steps, "runs": self.runs, "candidates": self.candidates, "failures": self.failures, "turns": [turn.to_dict() for turn in self.turns], "gaps": [gap.to_dict() for gap in self.gaps], "stop_reason": self.stop_reason}


class CodexDrivenResearchLoop:
    """Bounded Question -> Plan -> Execute -> Gap -> Codex loop.

    ``execute`` receives a validated PlanningResult and is the only callback
    allowed to run scientific work.  The model can propose the next plan, but
    cannot change the immutable LoopLimits or create Evidence.
    """

    def __init__(self, planner: Any, *, limits: LoopLimits | None = None):
        self.planner = planner
        self.limits = limits or LoopLimits()

    def run(self, prompt: str, *, execute: Callable[[Any], dict[str, Any]], evaluate: Callable[[dict[str, Any]], tuple[ResearchGap, ...]], context: dict[str, Any] | None = None, memory: list[dict[str, Any]] | None = None) -> CodexLoopResult:
        current_prompt = str(prompt)
        current_memory = list(memory or ())
        iterations = steps = runs = candidates = failures = 0
        turns: list[CodexLoopTurn] = []
        gaps: tuple[ResearchGap, ...] = ()
        while iterations < self.limits.max_iterations:
            if steps >= self.limits.max_steps or runs >= self.limits.max_runs or candidates >= self.limits.max_candidates:
                return CodexLoopResult("STOPPED", iterations, steps, runs, candidates, failures, tuple(turns), gaps, "resource_limit")
            iterations += 1
            try:
                planning = self.planner.ask(current_prompt, memory=current_memory, context=context)
                if planning.validation.status != "PASS":
                    return CodexLoopResult("INDETERMINATE" if planning.validation.status == "INDETERMINATE" else "FAILED", iterations, steps, runs, candidates, failures, tuple(turns), gaps, "plan_validation")
                result = dict(execute(planning))
                step_count = int(result.get("steps", len(planning.plan.steps)))
                run_count = int(result.get("runs", 0))
                candidate_count = int(result.get("candidates", 0))
                if steps + step_count > self.limits.max_steps or runs + run_count > self.limits.max_runs or candidates + candidate_count > self.limits.max_candidates:
                    return CodexLoopResult("STOPPED", iterations, steps, runs, candidates, failures, tuple(turns), gaps, "resource_limit")
                steps += step_count
                runs += run_count
                candidates += candidate_count
                if result.get("required_engine_missing") or (result.get("status") == "INDETERMINATE" and self.limits.stop_on_indeterminate):
                    turn = CodexLoopTurn(iterations, current_prompt, planning, result, ())
                    return CodexLoopResult("INDETERMINATE", iterations, steps, runs, candidates, failures, (*turns, turn), (), "required_engine_missing" if result.get("required_engine_missing") else "indeterminate")
                gaps = tuple(evaluate(result))
                turn = CodexLoopTurn(iterations, current_prompt, planning, result, gaps)
                turns.append(turn)
                if not gaps and self.limits.stop_on_evidence_requirement_met:
                    return CodexLoopResult("COMPLETED", iterations, steps, runs, candidates, failures, tuple(turns), gaps, "evidence_requirement_met")
                if any(_gap_requires_unavailable_ceiling(gap, result) for gap in gaps):
                    return CodexLoopResult("STOPPED", iterations, steps, runs, candidates, failures, tuple(turns), gaps, "EXPERIMENTAL_VALIDATION_REQUIRED")
                followup = self.planner.provider.propose_followup([gap.to_dict() for gap in gaps])
                current_prompt = str(followup.get("text") or followup.get("objective") or "Continue using only the recorded evidence gaps.")
                current_memory = [*current_memory, {"kind": "codex_loop_turn", "payload": turn.to_dict()}]
            except Exception:
                failures += 1
                if failures >= self.limits.max_failures:
                    return CodexLoopResult("FAILED", iterations, steps, runs, candidates, failures, tuple(turns), gaps, "max_failures")
        return CodexLoopResult("STOPPED", iterations, steps, runs, candidates, failures, tuple(turns), gaps, "max_iterations")


def _gap_requires_unavailable_ceiling(gap: ResearchGap, result: dict[str, Any]) -> bool:
    observed = {"E0_HEURISTIC": 0, "E1_ML": 1, "E2_COMPUTATIONAL": 2, "E3_PHYSICS": 3, "E4_CURATED_EXPERIMENTAL": 4, "E5_VALIDATED_EXPERIMENTAL": 5}
    current = max((observed.get(str(value), -1) for value in result.get("evidence_levels") or ()), default=-1)
    required = observed.get(gap.required_evidence.value, -1)
    return required >= 4 and current < required and any("experimental" in item.lower() or "clinical" in item.lower() for item in gap.missing_information)


class AutonomousResearchLoop:
    def __init__(self, limits: LoopLimits | None = None):
        self.limits = limits or LoopLimits()

    def run(self, execute: Callable[[int], dict[str, Any]], evaluate: Callable[[dict[str, Any]], tuple[ResearchGap, ...]]) -> LoopResult:
        iterations = steps = runs = candidates = failures = 0
        gaps: tuple[ResearchGap, ...] = ()
        while iterations < self.limits.max_iterations:
            if steps >= self.limits.max_steps or runs >= self.limits.max_runs or candidates >= self.limits.max_candidates:
                return LoopResult("STOPPED", iterations, steps, runs, candidates, failures, gaps, "resource_limit")
            iterations += 1
            try:
                result = execute(iterations)
                steps += int(result.get("steps", 1))
                runs += int(result.get("runs", 1))
                candidates += int(result.get("candidates", 0))
                if result.get("status") == "INDETERMINATE" and self.limits.stop_on_indeterminate:
                    return LoopResult("INDETERMINATE", iterations, steps, runs, candidates, failures, gaps, "indeterminate")
                if result.get("required_engine_missing") and self.limits.stop_on_required_engine_missing:
                    return LoopResult("INDETERMINATE", iterations, steps, runs, candidates, failures, gaps, "required_engine_missing")
            except Exception:
                failures += 1
                if failures >= self.limits.max_failures:
                    return LoopResult("FAILED", iterations, steps, runs, candidates, failures, gaps, "max_failures")
                continue
            gaps = evaluate(result)
            if not gaps and self.limits.stop_on_evidence_requirement_met:
                return LoopResult("COMPLETED", iterations, steps, runs, candidates, failures, gaps, "evidence_requirement_met")
        return LoopResult("STOPPED", iterations, steps, runs, candidates, failures, gaps, "max_iterations")
