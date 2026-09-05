"""Immutable contracts for integrating versioned external evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence
import uuid

from research_os.core.hashing import sha256_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tuple(values: Sequence[Any] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in values or ())


@dataclass(frozen=True)
class ExternalEvidenceUpdate:
    update_id: str
    source_id: str
    source_version: str
    dataset_id_optional: str | None
    evidence_ids: tuple[str, ...]
    affected_claim_ids: tuple[str, ...]
    affected_gap_ids: tuple[str, ...]
    affected_decision_ids: tuple[str, ...]
    compatibility_assessment: str | Mapping[str, Any]
    conflicts: tuple[str, ...]
    resulting_revisions: tuple[str, ...]
    created_at: str = field(default_factory=_now)
    digest: str | None = None

    def __post_init__(self) -> None:
        for name in ("evidence_ids", "affected_claim_ids", "affected_gap_ids", "affected_decision_ids", "conflicts", "resulting_revisions"):
            object.__setattr__(self, name, _tuple(getattr(self, name)))
        if not self.update_id.strip() or not self.source_id.strip() or not self.source_version.strip():
            raise ValueError("ExternalEvidenceUpdate requires source identity and version")
        if self.digest is None:
            object.__setattr__(self, "digest", sha256_json(self._hash_payload()))

    def _hash_payload(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("digest", None)
        for name in ("evidence_ids", "affected_claim_ids", "affected_gap_ids", "affected_decision_ids", "conflicts", "resulting_revisions"):
            data[name] = list(getattr(self, name))
        return data

    @property
    def valid(self) -> bool:
        return self.digest == sha256_json(self._hash_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_payload(), "digest": self.digest}


@dataclass(frozen=True)
class EvidenceDependencyAssessment:
    assessment_id: str
    evidence_ids: tuple[str, ...]
    shared_sources: tuple[str, ...]
    shared_datasets: tuple[str, ...]
    shared_models: tuple[str, ...]
    shared_runs: tuple[str, ...]
    shared_publications: tuple[str, ...]
    independence_status: str
    notes: tuple[str, ...] = ()
    created_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        for name in ("evidence_ids", "shared_sources", "shared_datasets", "shared_models", "shared_runs", "shared_publications", "notes"):
            object.__setattr__(self, name, _tuple(getattr(self, name)))
        if self.independence_status not in {"INDEPENDENT", "PARTIALLY_DEPENDENT", "DEPENDENT", "UNKNOWN"}:
            raise ValueError("unknown evidence independence status")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for name in ("evidence_ids", "shared_sources", "shared_datasets", "shared_models", "shared_runs", "shared_publications", "notes"):
            data[name] = list(getattr(self, name))
        return data


class ValidationCampaignStatus(str, Enum):
    VALIDATED = "VALIDATED"
    PARTIALLY_VALIDATED = "PARTIALLY_VALIDATED"
    FAILED_VALIDATION = "FAILED_VALIDATION"
    NO_ELIGIBLE_EXTERNAL_DATA = "NO_ELIGIBLE_EXTERNAL_DATA"
    INCOMPATIBLE_EXTERNAL_DATA = "INCOMPATIBLE_EXTERNAL_DATA"
    BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"


@dataclass(frozen=True)
class ExternalValidationCampaign:
    """Append-only validation attempt with an explicit independence audit."""

    campaign_id: str
    target_claim_id: str
    current_evidence: tuple[str, ...]
    required_validation: str
    candidate_sources: tuple[str, ...]
    candidate_datasets: tuple[str, ...]
    independence_assessments: tuple[dict[str, Any], ...]
    selected_validation_source: str | None
    protocol: dict[str, Any]
    result: dict[str, Any]
    claim_revision_ids: tuple[str, ...]
    decision_revision_ids: tuple[str, ...]
    status: ValidationCampaignStatus
    created_at: str = field(default_factory=_now)
    digest: str | None = None

    def __post_init__(self) -> None:
        for name in ("current_evidence", "candidate_sources", "candidate_datasets", "claim_revision_ids", "decision_revision_ids"):
            object.__setattr__(self, name, _tuple(getattr(self, name)))
        object.__setattr__(self, "independence_assessments", tuple(dict(item) for item in self.independence_assessments))
        object.__setattr__(self, "protocol", dict(self.protocol))
        object.__setattr__(self, "result", dict(self.result))
        object.__setattr__(self, "status", self.status if isinstance(self.status, ValidationCampaignStatus) else ValidationCampaignStatus(str(self.status)))
        if not self.campaign_id.strip() or not self.target_claim_id.strip() or not self.required_validation.strip():
            raise ValueError("ExternalValidationCampaign requires campaign, target claim and validation requirement")
        if self.status in {ValidationCampaignStatus.VALIDATED, ValidationCampaignStatus.PARTIALLY_VALIDATED, ValidationCampaignStatus.FAILED_VALIDATION} and not self.selected_validation_source:
            raise ValueError("a completed external validation requires a selected source")
        if self.digest is None:
            object.__setattr__(self, "digest", sha256_json(self._payload()))

    def _payload(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("digest", None)
        for name in ("current_evidence", "candidate_sources", "candidate_datasets", "claim_revision_ids", "decision_revision_ids"):
            data[name] = list(getattr(self, name))
        data["independence_assessments"] = [dict(item) for item in self.independence_assessments]
        data["status"] = self.status.value
        return data

    @property
    def valid(self) -> bool:
        return self.digest == sha256_json(self._payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}


class ExternalValidationCampaignStore:
    """In-memory append-only store used by live campaign artifacts."""

    def __init__(self) -> None:
        self._campaigns: list[ExternalValidationCampaign] = []

    def append(self, campaign: ExternalValidationCampaign) -> ExternalValidationCampaign:
        if not campaign.valid:
            raise ValueError("invalid ExternalValidationCampaign digest")
        if any(item.campaign_id == campaign.campaign_id for item in self._campaigns):
            raise ValueError(f"validation campaign already registered: {campaign.campaign_id}")
        self._campaigns.append(campaign)
        return campaign

    def list(self) -> tuple[ExternalValidationCampaign, ...]:
        return tuple(self._campaigns)


__all__ = ["EvidenceDependencyAssessment", "ExternalEvidenceUpdate", "ExternalValidationCampaign", "ExternalValidationCampaignStore", "ValidationCampaignStatus"]
