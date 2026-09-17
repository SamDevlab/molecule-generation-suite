"""Typed contracts for the v3.8 reproduction and stress benchmark."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
import uuid

from research_os.core.hashing import sha256_json
from research_os.reproducibility import ReproducibilityStatus


class StressStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class ReproductionCase:
    case_id: str
    target: str
    original_reference: str
    rerun_reference: str
    status: ReproducibilityStatus | str
    original_digest: str
    rerun_digest: str
    environment: Mapping[str, Any] = field(default_factory=dict)
    first_divergence: Mapping[str, Any] | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        status = self.status if isinstance(self.status, ReproducibilityStatus) else ReproducibilityStatus(str(self.status))
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "environment", dict(self.environment or {}))
        object.__setattr__(self, "notes", tuple(str(item) for item in self.notes))
        if status == ReproducibilityStatus.DIVERGED and not self.first_divergence:
            raise ValueError("DIVERGED reproduction cases require first_divergence")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["notes"] = list(self.notes)
        return data


@dataclass(frozen=True)
class StressTestResult:
    stress_id: str
    title: str
    expected: str
    observed: str
    status: StressStatus | str
    details: Mapping[str, Any] = field(default_factory=dict)
    result_id: str = field(default_factory=lambda: f"STRESS-RESULT-{uuid.uuid4().hex[:12].upper()}")

    def __post_init__(self) -> None:
        status = self.status if isinstance(self.status, StressStatus) else StressStatus(str(self.status))
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "details", dict(self.details or {}))

    @property
    def passed(self) -> bool:
        return self.status == StressStatus.PASS

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["passed"] = self.passed
        return data


@dataclass(frozen=True)
class ReproductionStressBenchmark:
    protocol_version: str
    branch: str
    git_commit: str
    started_at: str
    completed_at: str
    reproduction_cases: tuple[ReproductionCase, ...]
    stress_tests: tuple[StressTestResult, ...]
    environment_comparison: Mapping[str, Any]
    acceptance: Mapping[str, Any]
    status: str
    source_policy: str
    benchmark_id: str = field(default_factory=lambda: f"BENCH-V38-{uuid.uuid4().hex[:12].upper()}")

    def __post_init__(self) -> None:
        object.__setattr__(self, "reproduction_cases", tuple(self.reproduction_cases))
        object.__setattr__(self, "stress_tests", tuple(self.stress_tests))
        object.__setattr__(self, "environment_comparison", dict(self.environment_comparison or {}))
        object.__setattr__(self, "acceptance", dict(self.acceptance or {}))
        if self.status not in {"PASS", "FAIL", "INDETERMINATE"}:
            raise ValueError(f"unknown benchmark status: {self.status}")

    @property
    def digest(self) -> str:
        return sha256_json(self.to_dict(include_digest=False))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        data = {
            "benchmark_id": self.benchmark_id,
            "protocol_version": self.protocol_version,
            "branch": self.branch,
            "git_commit": self.git_commit,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "reproduction_cases": [item.to_dict() for item in self.reproduction_cases],
            "stress_tests": [item.to_dict() for item in self.stress_tests],
            "environment_comparison": dict(self.environment_comparison),
            "acceptance": dict(self.acceptance),
            "status": self.status,
            "source_policy": self.source_policy,
        }
        if include_digest:
            data["digest"] = self.digest
        return data

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReproductionStressBenchmark":
        reproductions = tuple(
            ReproductionCase(
                case_id=str(item["case_id"]),
                target=str(item["target"]),
                original_reference=str(item["original_reference"]),
                rerun_reference=str(item["rerun_reference"]),
                status=item["status"],
                original_digest=str(item["original_digest"]),
                rerun_digest=str(item["rerun_digest"]),
                environment=item.get("environment") or {},
                first_divergence=item.get("first_divergence"),
                notes=tuple(item.get("notes") or ()),
            )
            for item in payload.get("reproduction_cases") or ()
        )
        stresses = tuple(
            StressTestResult(
                stress_id=str(item["stress_id"]),
                title=str(item["title"]),
                expected=str(item["expected"]),
                observed=str(item["observed"]),
                status=item["status"],
                details=item.get("details") or {},
                result_id=str(item.get("result_id") or f"STRESS-RESULT-{uuid.uuid4().hex[:12].upper()}"),
            )
            for item in payload.get("stress_tests") or ()
        )
        fields = {
            key: payload[key]
            for key in (
                "protocol_version",
                "branch",
                "git_commit",
                "started_at",
                "completed_at",
                "environment_comparison",
                "acceptance",
                "status",
                "source_policy",
            )
            if key in payload
        }
        fields["benchmark_id"] = str(payload.get("benchmark_id") or f"BENCH-V38-{uuid.uuid4().hex[:12].upper()}")
        fields["reproduction_cases"] = reproductions
        fields["stress_tests"] = stresses
        return cls(**fields)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["ReproducibilityStatus", "ReproductionCase", "ReproductionStressBenchmark", "StressStatus", "StressTestResult", "now_iso"]
