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

