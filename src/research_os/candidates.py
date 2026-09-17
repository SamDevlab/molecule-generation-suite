"""Candidate generation and evidence-aware ranking boundaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import random
import uuid
from typing import Any, Iterable


class GenerationMethod(str, Enum):
    RANDOM = "RANDOM"
    RULE_BASED = "RULE_BASED"
    LIBRARY_SEARCH = "LIBRARY_SEARCH"
    ENUMERATION = "ENUMERATION"
    ML_GENERATIVE = "ML_GENERATIVE"
    OPTIMIZATION = "OPTIMIZATION"
    LEGACY_IMPORT = "LEGACY_IMPORT"


@dataclass(frozen=True)
class Candidate:
    representation: str
    method: GenerationMethod
    candidate_id: str = field(default_factory=lambda: f"CAND-{uuid.uuid4().hex[:12].upper()}")
    synthetic: bool = True
    source_dataset_id: str | None = None
    source_run_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["method"] = self.method.value
        return data


class CandidateGenerator:
    """Boundary that labels every generated candidate as synthetic."""

    def __init__(self, *, seed: int | None = None):
        self.random = random.Random(seed)

    def generate(self, method: GenerationMethod | str, candidates: Iterable[str] = (), *, source_dataset_id: str | None = None, source_run_id: str | None = None, metadata: dict[str, Any] | None = None, limit: int | None = None) -> tuple[Candidate, ...]:
        selected_method = method if isinstance(method, GenerationMethod) else GenerationMethod(str(method))
        values = [str(value).strip() for value in candidates if str(value).strip()]
        if selected_method == GenerationMethod.RANDOM and values:
            self.random.shuffle(values)
        if limit is not None:
            if limit < 0:
                raise ValueError("limit must be non-negative")
            values = values[:limit]
        return tuple(Candidate(value, selected_method, source_dataset_id=source_dataset_id, source_run_id=source_run_id, metadata=dict(metadata or {})) for value in values)


@dataclass(frozen=True)
class CandidateEvaluation:
    candidate_id: str
    metric: str
    value: float | None
    direction: str
    evidence: str
    status: str
    ood: bool = False
    uncertainty: float | None = None
    conditions: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    protocol_id: str | None = None
    explanation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CandidateRanking:
    metric: str
    direction: str
    ranked: tuple[CandidateEvaluation, ...]
    excluded: tuple[CandidateEvaluation, ...] = ()
    exclusion_reasons: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"metric": self.metric, "direction": self.direction, "ranked": [item.to_dict() for item in self.ranked], "excluded": [item.to_dict() for item in self.excluded], "exclusion_reasons": dict(self.exclusion_reasons)}

    @staticmethod
    def rank(evaluations: Iterable[CandidateEvaluation], *, metric: str, direction: str = "max", include_ood: bool = False, include_indeterminate: bool = False) -> "CandidateRanking":
        direction = direction.lower()
        if direction not in {"max", "min"}:
            raise ValueError("direction must be 'max' or 'min'")
        ranked: list[CandidateEvaluation] = []
        excluded: list[CandidateEvaluation] = []
        reasons: dict[str, str] = {}
        for evaluation in evaluations:
            reason = None
            if evaluation.metric != metric:
                reason = "METRIC_MISMATCH"
            elif evaluation.value is None:
                reason = "MISSING_VALUE"
            elif not include_ood and evaluation.ood:
                reason = "OUT_OF_DOMAIN"
            elif not include_indeterminate and evaluation.status in {"INDETERMINATE", "INSUFFICIENT_EVIDENCE", "SKIPPED"}:
                reason = evaluation.status
            if reason:
                excluded.append(evaluation)
                reasons[evaluation.candidate_id] = reason
            else:
                ranked.append(evaluation)
        ranked.sort(key=lambda item: float(item.value), reverse=direction == "max")
        return CandidateRanking(metric, direction, tuple(ranked), tuple(excluded), reasons)

