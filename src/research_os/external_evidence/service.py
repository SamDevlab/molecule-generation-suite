"""Guarded integration helpers; updates never overwrite historical records."""

from __future__ import annotations

from typing import Any, Mapping, Sequence
import uuid

from research_os.external_evidence.models import EvidenceDependencyAssessment, ExternalEvidenceUpdate


class ExternalEvidenceIntegrator:
    """Evaluate dependency and evidence-level compatibility without promotion."""

    def __init__(self) -> None:
        self.updates: list[ExternalEvidenceUpdate] = []
        self.dependencies: list[EvidenceDependencyAssessment] = []

    def add_update(self, update: ExternalEvidenceUpdate) -> ExternalEvidenceUpdate:
        if not update.valid:
            raise ValueError("invalid ExternalEvidenceUpdate digest")
        if any(item.update_id == update.update_id for item in self.updates):
            raise ValueError(f"update already registered: {update.update_id}")
        self.updates.append(update)
        return update

    def assess_dependency(self, evidence_ids: Sequence[str], metadata: Mapping[str, Mapping[str, Any]]) -> EvidenceDependencyAssessment:
        selected = [metadata[str(evidence_id)] for evidence_id in evidence_ids if str(evidence_id) in metadata]
        def shared(field: str) -> tuple[str, ...]:
            values: list[set[str]] = []
            for item in selected:
                value = item.get(field) or ()
                values.append({str(entry) for entry in (value if isinstance(value, (list, tuple, set)) else (value,)) if entry})
            return tuple(sorted(set.intersection(*values))) if values else ()
        shared_sources = shared("source_ids")
        shared_datasets = shared("dataset_ids")
        shared_models = shared("model_ids")
        shared_runs = shared("run_ids")
        shared_publications = shared("publication_ids")
        overlap_count = sum(bool(value) for value in (shared_sources, shared_datasets, shared_models, shared_runs, shared_publications))
        if len(selected) < len(tuple(evidence_ids)):
            status = "UNKNOWN"
            notes = ("one or more evidence metadata records are missing",)
        elif overlap_count >= 3 or shared_runs:
            status = "DEPENDENT"
            notes = ("shared run/dataset/model lineage means repeated records are not independent confirmations",)
        elif overlap_count:
            status = "PARTIALLY_DEPENDENT"
            notes = ("at least one provenance dimension is shared; evidence must not be counted as fully independent",)
        else:
            status = "INDEPENDENT"
            notes = ("no shared registered provenance dimension was found",)
        result = EvidenceDependencyAssessment(f"DEP-{uuid.uuid4().hex[:12].upper()}", tuple(str(item) for item in evidence_ids), shared_sources, shared_datasets, shared_models, shared_runs, shared_publications, status, notes)
        self.dependencies.append(result)
        return result

    @staticmethod
    def level_guard(current_level: str, target_level: str, *, actual_experiment: bool = False) -> dict[str, Any]:
        order = {"TEST_SYNTHETIC": -1, "E0_HEURISTIC": 0, "E1_ML": 1, "E2_COMPUTATIONAL": 2, "E3_PHYSICS": 3, "E4_CURATED_EXPERIMENTAL": 4, "E5_VALIDATED_EXPERIMENTAL": 5}
        current = order.get(str(current_level), -1)
        target = order.get(str(target_level), -1)
        allowed = target <= current or (target >= 4 and actual_experiment)
        return {"current_level": current_level, "target_level": target_level, "actual_experiment": actual_experiment, "promotion_allowed": allowed, "reason": "same-or-lower level" if target <= current else "an actual eligible experiment is required"}


__all__ = ["ExternalEvidenceIntegrator"]
