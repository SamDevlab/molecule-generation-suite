from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, Protocol, Sequence, TypeVar

from research_os.core.types import GateStatus


class SplitStrategy(str, Enum):
    RANDOM = "random_split"
    RANDOM_SPLIT = "random_split"
    SCAFFOLD = "scaffold_split"
    SCAFFOLD_SPLIT = "scaffold_split"
    CLUSTER = "cluster_split"
    CLUSTER_SPLIT = "cluster_split"
    SOURCE = "source_split"
    SOURCE_SPLIT = "source_split"
    TEMPORAL = "temporal_split"
    TEMPORAL_SPLIT = "temporal_split"
    GROUP = "group_split"
    GROUP_SPLIT = "group_split"
    EXTERNAL_TEST = "external_test"


T = TypeVar("T")


@dataclass(frozen=True)
class DataSplit(Generic[T]):
    strategy: SplitStrategy
    train: tuple[T, ...]
    validation: tuple[T, ...]
    test: tuple[T, ...]
    seed: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def train_count(self) -> int:
        return len(self.train)

    @property
    def validation_count(self) -> int:
        return len(self.validation)

    @property
    def test_count(self) -> int:
        return len(self.test)

    def counts(self) -> dict[str, int]:
        return {"train": self.train_count, "validation": self.validation_count, "test": self.test_count}


@dataclass(frozen=True)
class ValidationGate:
    gate_id: str
    rule_id: str
    status: GateStatus
    reason: str
    evidence_ids: tuple[str, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationReport:
    model_id: str | None
    task: str | None
    split_strategy: SplitStrategy
    train_count: int
    validation_count: int
    test_count: int
    seed: int | None
    metrics: dict[str, float]
    gates: tuple[ValidationGate, ...]
    external_test_acceptable: bool | None = None
    applicability_domain: ApplicabilityDomainResult | None = None
    out_of_domain_score: float | None = None
    prediction_interval: dict[str, Any] | None = None
    calibration: dict[str, Any] | None = None

    @property
    def passed(self) -> bool:
        return bool(self.gates) and all(g.status == GateStatus.PASS for g in self.gates)

    @property
    def first_loss(self) -> ValidationGate | None:
        return next((gate for gate in self.gates if gate.status != GateStatus.PASS), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "task": self.task,
            "split_strategy": self.split_strategy.value,
            "train_count": self.train_count,
            "validation_count": self.validation_count,
            "test_count": self.test_count,
            "seed": self.seed,
            "metrics": dict(self.metrics),
            "gates": [
                {**gate.__dict__, "status": gate.status.value, "evidence_ids": list(gate.evidence_ids)}
                for gate in self.gates
            ],
            "external_test_acceptable": self.external_test_acceptable,
            "applicability_domain": self.applicability_domain.to_dict() if self.applicability_domain else None,
            "out_of_domain_score": self.out_of_domain_score,
            "prediction_interval": self.prediction_interval,
            "calibration": self.calibration,
        }


@dataclass(frozen=True)
class ApplicabilityDomainResult:
    in_domain: bool
    score: float | None
    method: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class SupportsApplicabilityDomain(Protocol):
    def assess(self, features: Sequence[Any]) -> ApplicabilityDomainResult: ...
