from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Sequence
import uuid

from research_os.core.hashing import sha256_json
from research_os.core.types import GateResult, GateStatus, RunManifest
from research_os.orchestration.registry import LabRegistry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowPlanError(ValueError):
    pass


@dataclass(frozen=True)
class PlanStep:
    """Materialized, explicit work request; it is the only unit the runner executes."""

    step_id: str
    lab: str
    inputs: dict[str, Any]
    experiment: str = "default"
    requires: tuple[str, ...] = ()
    consumed_evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowPlan:
    steps: tuple[PlanStep, ...]
    plan_id: str = field(default_factory=lambda: f"PLAN-{uuid.uuid4().hex[:12].upper()}")
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {"plan_id": self.plan_id, "created_at": self.created_at, "steps": [asdict(step) for step in self.steps]}


@dataclass
class WorkflowStepRecord:
    step_id: str
    lab: str
    experiment: str
    inputs: dict[str, Any]
    requires: tuple[str, ...]
    consumed_evidence_ids: tuple[str, ...] = ()
    produced_evidence_ids: tuple[str, ...] = ()
    status: str = "PENDING"
    first_loss: GateResult | None = None
    started_at: str | None = None
    completed_at: str | None = None
    skip_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.first_loss is not None:
            data["first_loss"] = asdict(self.first_loss)
            data["first_loss"]["status"] = self.first_loss.status.value
        return data


@dataclass
class PlanRun:
    plan_id: str = field(default_factory=lambda: f"PLAN-{uuid.uuid4().hex[:12].upper()}")
    created_at: str = field(default_factory=_now)
    runs: dict[str, RunManifest] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)
    steps: dict[str, WorkflowStepRecord] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return bool(self.steps) and all(record.status == "PASS" for record in self.steps.values())

    @property
    def first_loss(self) -> WorkflowStepRecord | None:
        return next((record for record in self.steps.values() if record.status != "PASS"), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "runs": {step_id: _run_to_dict(run) for step_id, run in self.runs.items()},
            "skipped": dict(self.skipped),
            "steps": {step_id: record.to_dict() for step_id, record in self.steps.items()},
        }


def _run_to_dict(run: RunManifest) -> dict[str, Any]:
    data = asdict(run)
    data["evidence"] = [{**asdict(evidence), "level": evidence.level.value} for evidence in run.evidence]
    data["gates"] = [{**asdict(gate), "status": gate.status.value} for gate in run.gates]
    data["provenance"] = [record.to_dict() for record in run.provenance]
    data["status"] = run.status
    data["digest"] = run.digest()
    return data


class ResearchOrchestrator:
    """Executes only a validated, materialized lab plan."""

    def __init__(self, registry: LabRegistry):
        self.registry = registry

    def materialize(self, steps: Sequence[PlanStep]) -> WorkflowPlan:
        materialized = tuple(steps)
        if any(not isinstance(step, PlanStep) for step in materialized):
            raise WorkflowPlanError("workflow steps must be explicit PlanStep instances")
        ids = [step.step_id for step in materialized]
        if len(ids) != len(set(ids)):
            raise WorkflowPlanError("plan step_id values must be unique")
        known = set(ids)
        for step in materialized:
            unknown = set(step.requires) - known
            if unknown:
                raise WorkflowPlanError(f"step {step.step_id} has unknown dependencies: {sorted(unknown)}")
            if not step.step_id.strip() or not step.lab.strip():
                raise WorkflowPlanError("plan step_id and lab cannot be empty")
        remaining = list(materialized)
        ordered: list[PlanStep] = []
        done: set[str] = set()
        while remaining:
            ready = [step for step in remaining if set(step.requires).issubset(done)]
            if not ready:
                raise WorkflowPlanError("workflow dependencies contain a cycle")
            ordered.extend(ready)
            done.update(step.step_id for step in ready)
            remaining = [step for step in remaining if step.step_id not in done]
        return WorkflowPlan(tuple(ordered))

    def run(self, steps: Sequence[PlanStep] | WorkflowPlan) -> PlanRun:
        if isinstance(steps, WorkflowPlan):
            validated = self.materialize(steps.steps)
            plan = WorkflowPlan(validated.steps, plan_id=steps.plan_id, created_at=steps.created_at)
        else:
            plan = self.materialize(steps)
        result = PlanRun(plan_id=plan.plan_id, created_at=plan.created_at)
        for step in plan.steps:
            dependencies = [result.steps[dependency] for dependency in step.requires]
            unmet = [dependency.step_id for dependency in dependencies if dependency.status != "PASS"]
            consumed = _unique((*step.consumed_evidence_ids, *(evidence_id for dependency in dependencies for evidence_id in dependency.produced_evidence_ids)))
            record = WorkflowStepRecord(step.step_id, step.lab, step.experiment, dict(step.inputs), tuple(step.requires), consumed_evidence_ids=consumed, started_at=_now())
            if unmet:
                reason = f"upstream requirements not satisfied: {', '.join(unmet)}"
                loss = GateResult("GATE-WORKFLOW-UPSTREAM", "WORKFLOW-UPSTREAM-001", GateStatus.SKIPPED, reason, evidence_ids=consumed)
                record.status = "SKIPPED"
                record.first_loss = loss
                record.skip_reason = reason
                record.completed_at = _now()
                result.skipped[step.step_id] = reason
                result.steps[step.step_id] = record
                continue
            try:
                run = self.registry.get(step.lab).run(dict(step.inputs), experiment=step.experiment)
            except Exception as exc:
                run = RunManifest(lab=step.lab, experiment=step.experiment, inputs=dict(step.inputs))
                run.gates.append(GateResult("GATE-WORKFLOW-EXECUTION", "WORKFLOW-EXECUTION-001", GateStatus.FAIL, "lab execution failed before producing a result", diagnostics={"error_type": type(exc).__name__, "error": str(exc)}))
            record.status = "PASS" if run.passed else "FAIL"
            record.first_loss = run.first_loss
            record.produced_evidence_ids = tuple(evidence.evidence_id for evidence in run.evidence)
            record.completed_at = _now()
            result.runs[step.step_id] = run
            result.steps[step.step_id] = record
        return result

    def write_ledger(self, plan_run: PlanRun, root: str | Path) -> Path:
        target = Path(root) / plan_run.plan_id
        target.mkdir(parents=True, exist_ok=False)
        payload = plan_run.to_dict()
        payload["digest"] = sha256_json(payload)
        (target / "workflow.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return target


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))
