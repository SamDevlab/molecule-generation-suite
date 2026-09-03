"""Typed public records for the persistent Research OS ledger.

The ledger deliberately stores an index, not a second copy of a research
bundle.  Every record in this module is therefore safe to reconstruct from a
bundle directory.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class LedgerError(RuntimeError):
    """Base error for ledger operations."""

    rule_id = "LEDGER-000"

    def __init__(self, message: str, *, rule_id: str | None = None):
        super().__init__(message)
        if rule_id is not None:
            self.rule_id = rule_id


class LedgerSchemaError(LedgerError):
    rule_id = "LEDGER-SCHEMA-001"


class LedgerIntegrityError(LedgerError):
    rule_id = "LEDGER-BUNDLE-001"


class LedgerConflictError(LedgerError):
    rule_id = "LEDGER-RUN-CONFLICT-001"


class LineageCycleError(LedgerError):
    rule_id = "LEDGER-LINEAGE-CYCLE-001"


class LedgerOperationStatus(str, Enum):
    REGISTERED = "REGISTERED"
    ALREADY_REGISTERED = "ALREADY_REGISTERED"
    REMOVED = "REMOVED"
    NOT_FOUND = "NOT_FOUND"


class ReproducibilityStatus(str, Enum):
    REPRODUCED = "REPRODUCED"
    REPRODUCED_WITH_ENVIRONMENT_CHANGE = "REPRODUCED_WITH_ENVIRONMENT_CHANGE"
    DIVERGED = "DIVERGED"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    INDETERMINATE = "INDETERMINATE"


class LedgerVerificationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class RunIndexRecord:
    run_id: str
    bundle_id: str
    bundle_path: str
    bundle_hash: str
    status: str
    sealed: bool
    lab: str | None = None
    experiment: str | None = None
    workflow_id: str | None = None
    plan_id: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    git_commit: str | None = None
    environment_id: str | None = None
    environment_hash: str | None = None
    first_loss_rule_id: str | None = None
    first_loss_status: str | None = None
    parent_run_id: str | None = None
    rerun_of: str | None = None
    supersedes: str | None = None
    index_created_at: str | None = None
    index_updated_at: str | None = None
    tags: tuple[str, ...] = ()
    dataset_ids: tuple[str, ...] = ()
    claim_ids: tuple[str, ...] = ()
    model_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    engine_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for name in ("tags", "dataset_ids", "claim_ids", "model_ids", "evidence_ids", "engine_ids"):
            data[name] = list(data[name])
        return data


@dataclass(frozen=True)
class RunDependency:
    downstream_run_id: str
    upstream_run_id: str
    relation: str = "depends_on"
    created_at: str | None = None

    @property
    def run_id(self) -> str:
        return self.downstream_run_id

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClaimIndexRecord:
    claim_id: str
    run_id: str
    statement: str = ""
    status: str | None = None
    minimum_evidence_level: str | None = None
    evidence_ids: tuple[str, ...] = ()
    created_at: str | None = None
    conditions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_ids"] = list(self.evidence_ids)
        return data


@dataclass(frozen=True)
class EvidenceIndexRecord:
    evidence_id: str
    run_id: str
    kind: str
    level: str
    source: str | None = None
    provenance_ids: tuple[str, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["provenance_ids"] = list(self.provenance_ids)
        return data


@dataclass(frozen=True)
class LineageGraph:
    run_id: str
    ancestors: tuple[str, ...] = ()
    descendants: tuple[str, ...] = ()
    dependencies: tuple[RunDependency, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "ancestors": list(self.ancestors),
            "descendants": list(self.descendants),
            "dependencies": [item.to_dict() for item in self.dependencies],
        }


@dataclass(frozen=True)
class WorkflowStepIndex:
    workflow_run_id: str
    step_id: str
    run_id: str | None
    status: str
    ordinal: int
    first_loss_rule_id: str | None = None
    first_loss_status: str | None = None
    requires: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["requires"] = list(self.requires)
        return data


@dataclass(frozen=True)
class WorkflowExecution:
    workflow_run_id: str
    plan_id: str
    status: str
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    first_loss_step_id: str | None = None
    first_loss_rule_id: str | None = None
    git_commit: str | None = None
    environment_id: str | None = None
    environment_hash: str | None = None
    rerun_of: str | None = None
    steps: tuple[WorkflowStepIndex, ...] = ()

    @property
    def workflow_id(self) -> str:
        return self.workflow_run_id

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = [item.to_dict() for item in self.steps]
        return data


@dataclass(frozen=True)
class WorkflowComparison:
    original_workflow_id: str
    rerun_workflow_id: str
    status: ReproducibilityStatus
    same_plan: bool | None
    same_inputs: bool | None
    same_config: bool | None
    same_datasets: bool | None
    same_code: bool | None
    same_environment: bool | None
    steps_compared: tuple[str, ...] = ()
    first_divergence_step: str | None = None
    first_divergence_rule_id: str | None = None
    differences: tuple[str, ...] = ()
    first_divergence: "FirstDivergence | None" = None
    engine_differences: tuple[str, ...] = ()

    @property
    def same_dataset_hashes(self) -> bool | None:
        return self.same_datasets

    @property
    def same_code_commit(self) -> bool | None:
        return self.same_code

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["steps_compared"] = list(self.steps_compared)
        data["differences"] = list(self.differences)
        data["first_divergence"] = self.first_divergence.to_dict() if self.first_divergence else None
        data["engine_differences"] = list(self.engine_differences)
        return data


@dataclass(frozen=True)
class FirstDivergence:
    step_id: str
    rule_id: str | None
    reason: str
    original_value: Any = None
    rerun_value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegressionFinding:
    category: str
    severity: str
    message: str
    step_id: str | None = None
    rule_id: str | None = None
    original_value: Any = None
    rerun_value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LedgerGate:
    rule_id: str
    status: str
    reason: str
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LedgerVerificationResult:
    status: str
    gates: tuple[LedgerGate, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    @property
    def first_loss(self) -> LedgerGate | None:
        return next((gate for gate in self.gates if gate.status != "PASS"), None)

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "gates": [gate.to_dict() for gate in self.gates]}


@dataclass(frozen=True)
class RebuildReport:
    indexed: tuple[str, ...] = ()
    already_registered: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    failures: tuple[dict[str, Any], ...] = ()

    @property
    def count(self) -> int:
        return len(self.indexed) + len(self.already_registered)

    def to_dict(self) -> dict[str, Any]:
        return {
            "indexed": list(self.indexed),
            "already_registered": list(self.already_registered),
            "skipped": list(self.skipped),
            "failures": list(self.failures),
            "count": self.count,
        }


@dataclass(frozen=True)
class WorkflowRerunResult:
    plan_run: Any
    bundle: Any
    comparison: WorkflowComparison

    @property
    def workflow_id(self) -> str:
        return str(getattr(self.plan_run, "plan_id"))

    def to_dict(self) -> dict[str, Any]:
        return {"workflow_id": self.workflow_id, "bundle": getattr(self.bundle, "root", None), "comparison": self.comparison.to_dict()}


@dataclass(frozen=True)
class LedgerRegistration:
    run_id: str
    status: LedgerOperationStatus
    bundle_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data
