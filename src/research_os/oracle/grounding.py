"""Deterministic guards for model narration over recorded scientific data."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from typing import Any

from research_os.core.types import EvidenceLevel


LLM_OUTPUT_CANNOT_CREATE_SCIENTIFIC_EVIDENCE = "LLM_OUTPUT_CANNOT_CREATE_SCIENTIFIC_EVIDENCE"
_LEVEL_ORDER = {level.value: index for index, level in enumerate((EvidenceLevel.E0_HEURISTIC, EvidenceLevel.E1_ML, EvidenceLevel.E2_COMPUTATIONAL, EvidenceLevel.E3_PHYSICS, EvidenceLevel.E4_CURATED_EXPERIMENTAL, EvidenceLevel.E5_VALIDATED_EXPERIMENTAL))}


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
