"""Deterministic guards for model narration over recorded scientific data."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable

from research_os.core.types import EvidenceLevel


LLM_OUTPUT_CANNOT_CREATE_SCIENTIFIC_EVIDENCE = "LLM_OUTPUT_CANNOT_CREATE_SCIENTIFIC_EVIDENCE"
_LEVEL_ORDER = {level.value: index for index, level in enumerate((EvidenceLevel.E0_HEURISTIC, EvidenceLevel.E1_ML, EvidenceLevel.E2_COMPUTATIONAL, EvidenceLevel.E3_PHYSICS, EvidenceLevel.E4_CURATED_EXPERIMENTAL, EvidenceLevel.E5_VALIDATED_EXPERIMENTAL))}


class GroundingStatus(str, Enum):
    GROUNDED = "GROUNDED"
    NO_GROUNDED_ANSWER = "NO_GROUNDED_ANSWER"


class GroundingFailureCode(str, Enum):
    NONE = "NONE"
    INVALID_RESPONSE_TYPE = "INVALID_RESPONSE_TYPE"
    MISSING_GROUNDED_RECORD_IDS = "MISSING_GROUNDED_RECORD_IDS"
    INVALID_GROUNDED_RECORD_IDS_TYPE = "INVALID_GROUNDED_RECORD_IDS_TYPE"
    EMPTY_GROUNDING_FOR_GROUNDED_ANSWER = "EMPTY_GROUNDING_FOR_GROUNDED_ANSWER"
    UNKNOWN_GROUNDED_RECORD_ID = "UNKNOWN_GROUNDED_RECORD_ID"
    FORBIDDEN_SCIENTIFIC_FIELD = "FORBIDDEN_SCIENTIFIC_FIELD"
    INVALID_GROUNDING_STATUS = "INVALID_GROUNDING_STATUS"


_FORBIDDEN_SCIENTIFIC_FIELDS = frozenset({
    "evidence", "evidence_level", "runs", "bundle", "bundle_id",
    "scientific_result", "experimental_result", "engine_result",
})


def find_forbidden_scientific_fields(value: Any) -> tuple[str, ...]:
    """Return paths to fields that would let a model manufacture authority."""
    found: list[str] = []

    def visit(item: Any, path: str = "") -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                key_text = str(key)
                child_path = f"{path}.{key_text}" if path else key_text
                if key_text.lower() in _FORBIDDEN_SCIENTIFIC_FIELDS:
                    found.append(child_path)
                visit(child, child_path)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f"{path}[{index}]")

    visit(value)
    return tuple(dict.fromkeys(found))


def _response_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GroundingValidationResult:
    valid: bool
    failure_code: str
    returned_ids: tuple[str, ...]
    unknown_ids: tuple[str, ...]
    known_ids_count: int
    missing_grounding_field: bool
    grounding_status: str | None
    forbidden_fields: tuple[str, ...]
    response_type: str
    response_hash: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["returned_ids"] = list(self.returned_ids)
        value["unknown_ids"] = list(self.unknown_ids)
        value["forbidden_fields"] = list(self.forbidden_fields)
        return value


def validate_grounding(response: Any, known_ids: Iterable[str]) -> GroundingValidationResult:
    """Validate the explicit Live grounding contract without accepting empty ``all`` results."""
    known = {str(item) for item in known_ids}
    response_type = type(response).__name__
    response_hash = _response_hash(response)
    if not isinstance(response, dict):
        return GroundingValidationResult(False, GroundingFailureCode.INVALID_RESPONSE_TYPE.value, (), (), len(known), True, None, (), response_type, response_hash)
    forbidden = find_forbidden_scientific_fields(response)
    if forbidden:
        raw_ids = response.get("grounded_record_ids")
        returned = tuple(item for item in raw_ids if isinstance(item, str)) if isinstance(raw_ids, list) else ()
        unknown = tuple(sorted(set(returned) - known))
        return GroundingValidationResult(False, GroundingFailureCode.FORBIDDEN_SCIENTIFIC_FIELD.value, returned, unknown, len(known), "grounded_record_ids" not in response, response.get("grounding_status") if isinstance(response.get("grounding_status"), str) else None, forbidden, response_type, response_hash)
    if "grounded_record_ids" not in response:
        return GroundingValidationResult(False, GroundingFailureCode.MISSING_GROUNDED_RECORD_IDS.value, (), (), len(known), True, response.get("grounding_status") if isinstance(response.get("grounding_status"), str) else None, (), response_type, response_hash)
    raw_ids = response["grounded_record_ids"]
    if not isinstance(raw_ids, list) or not all(isinstance(item, str) for item in raw_ids):
        returned = tuple(item for item in raw_ids if isinstance(item, str)) if isinstance(raw_ids, list) else ()
        unknown = tuple(sorted(set(returned) - known))
        return GroundingValidationResult(False, GroundingFailureCode.INVALID_GROUNDED_RECORD_IDS_TYPE.value, returned, unknown, len(known), False, response.get("grounding_status") if isinstance(response.get("grounding_status"), str) else None, (), response_type, response_hash)
    returned_ids = tuple(raw_ids)
    unknown_ids = tuple(sorted(set(returned_ids) - known))
    grounding_status = response.get("grounding_status")
    if grounding_status not in {item.value for item in GroundingStatus}:
        return GroundingValidationResult(False, GroundingFailureCode.INVALID_GROUNDING_STATUS.value, returned_ids, unknown_ids, len(known), False, str(grounding_status) if grounding_status is not None else None, (), response_type, response_hash)
    if grounding_status == GroundingStatus.NO_GROUNDED_ANSWER.value and returned_ids:
        return GroundingValidationResult(False, GroundingFailureCode.INVALID_GROUNDING_STATUS.value, returned_ids, unknown_ids, len(known), False, grounding_status, (), response_type, response_hash)
    if grounding_status == GroundingStatus.GROUNDED.value and not returned_ids:
        return GroundingValidationResult(False, GroundingFailureCode.EMPTY_GROUNDING_FOR_GROUNDED_ANSWER.value, returned_ids, (), len(known), False, grounding_status, (), response_type, response_hash)
    if unknown_ids:
        return GroundingValidationResult(False, GroundingFailureCode.UNKNOWN_GROUNDED_RECORD_ID.value, returned_ids, unknown_ids, len(known), False, grounding_status, (), response_type, response_hash)
    return GroundingValidationResult(True, GroundingFailureCode.NONE.value, returned_ids, (), len(known), False, grounding_status, (), response_type, response_hash)


@dataclass(frozen=True)
class NarrationGroundingResult:
    status: str
    reason: str
    unknown_evidence_ids: tuple[str, ...] = ()
    unknown_run_ids: tuple[str, ...] = ()
    observed_evidence_level: str | None = None

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["unknown_evidence_ids"] = list(self.unknown_evidence_ids)
        data["unknown_run_ids"] = list(self.unknown_run_ids)
        return data


def validate_narration(narration: dict[str, Any], recorded: dict[str, Any], *, expected_status: str | None = None) -> NarrationGroundingResult:
    """Check that live narration references only IDs and status from records.

    This gate deliberately does not try to prove arbitrary prose.  It makes
    the safe boundary explicit: live model prose is usable only when its
    structured references resolve to the recorded execution and its stated
    evidence level/status do not exceed those records.
    """
    if not isinstance(narration, dict) or not str(narration.get("summary", "")).strip():
        return NarrationGroundingResult("FAIL", "narration summary is missing")
    actual_evidence = _recorded_evidence(recorded)
    actual_evidence_ids = {str(item.get("evidence_id")) for item in actual_evidence if item.get("evidence_id")}
    actual_runs = recorded.get("runs") if isinstance(recorded.get("runs"), dict) else {}
    actual_run_ids = {str(item.get("run_id")) for item in actual_runs.values() if isinstance(item, dict) and item.get("run_id")}
    cited_evidence = {str(value) for value in narration.get("evidence_ids") or ()}
    cited_runs = {str(value) for value in narration.get("run_ids") or ()}
    unknown_evidence = tuple(sorted(cited_evidence - actual_evidence_ids))
    unknown_runs = tuple(sorted(cited_runs - actual_run_ids))
    if unknown_evidence or unknown_runs:
        return NarrationGroundingResult("FAIL", "narration references records not present in the execution", unknown_evidence, unknown_runs)
    actual_status = str(expected_status or recorded.get("status") or "")
    stated_status = str(narration.get("status") or "")
    if stated_status and actual_status and stated_status != actual_status:
        return NarrationGroundingResult("FAIL", "narration status contradicts recorded execution status")
    observed = max((_LEVEL_ORDER.get(str(item.get("level")), -1) for item in actual_evidence), default=-1)
    observed_name = next((key for key, value in _LEVEL_ORDER.items() if value == observed), None)
    summary = str(narration.get("summary", ""))
    # Numeric scientific values must remain in the recorded Evidence payload;
    # accepting model-repeated decimals would make prose an alternate source
    # of truth.  IDs and canonical evidence labels are explicitly exempt.
    summary_without_ids = re.sub(r"\b(?:EVD|RUN|PLAN|JOB|Q|SESSION)-[A-Z0-9-]+\b|\bE[0-5](?:_[A-Z]+)*\b", "", summary.upper())
    if re.search(r"(?<![A-Z])[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?", summary_without_ids):
        return NarrationGroundingResult("FAIL", "narration contains numeric scientific content outside the recorded payload", observed_evidence_level=observed_name)
    requested_levels = [match.upper().replace("-", "_") for match in re.findall(r"\bE[0-5](?:[_-][A-Z]+)+\b", summary.upper())]
    if any(_LEVEL_ORDER.get(level, -1) > observed for level in requested_levels):
        return NarrationGroundingResult("FAIL", "narration states an evidence level above the recorded ceiling", observed_evidence_level=observed_name)
    return NarrationGroundingResult("PASS", "narration references only recorded execution data", observed_evidence_level=observed_name)


def _recorded_evidence(recorded: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(recorded.get("evidence"), list):
        return [item for item in recorded["evidence"] if isinstance(item, dict)]
    runs = recorded.get("runs") if isinstance(recorded.get("runs"), dict) else {}
    return [evidence for run in runs.values() if isinstance(run, dict) for evidence in run.get("evidence") or () if isinstance(evidence, dict)]
