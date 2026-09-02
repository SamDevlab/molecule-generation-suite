from __future__ import annotations

from research_os.core.types import EvidenceLevel, GateResult, GateStatus
from research_os.datasets.schema import DatasetManifest, DatasetSourceType


_EXPERIMENTAL_LEVELS = {EvidenceLevel.E4_CURATED_EXPERIMENTAL, EvidenceLevel.E5_VALIDATED_EXPERIMENTAL}


def is_experimental_ground_truth(manifest: DatasetManifest) -> bool:
    """Return true only for a dataset explicitly eligible for experimental claims."""
    if manifest.is_synthetic or manifest.experimental_fraction <= 0:
        return False
    if not any(level in _EXPERIMENTAL_LEVELS for level in manifest.evidence_levels):
        return False
    allowed = {DatasetSourceType.EXPERIMENTAL, DatasetSourceType.CURATED_EXPERIMENTAL}
    return bool(manifest.source_types) and set(manifest.source_types).issubset(allowed)


def dataset_ground_truth_gate(manifest: DatasetManifest, *, requested_level: EvidenceLevel = EvidenceLevel.E4_CURATED_EXPERIMENTAL) -> GateResult:
    """Prevent ML/heuristic predictions from becoming experimental truth silently."""
    if not manifest.source_types:
        return GateResult("GATE-DATASET-PROVENANCE", "DATASET-GT-001", GateStatus.INSUFFICIENT_EVIDENCE, "dataset source_types are required before a ground-truth claim")
    if manifest.is_synthetic:
        return GateResult("GATE-DATASET-PROVENANCE", "DATASET-GT-002", GateStatus.INSUFFICIENT_EVIDENCE, "synthetic or ML-generated data cannot be treated as experimental ground truth", diagnostics={"source_types": [source.value for source in manifest.source_types], "synthetic_fraction": manifest.synthetic_fraction})
    if any(source.is_computational for source in manifest.source_types) or manifest.computational_fraction > 0:
        return GateResult("GATE-DATASET-PROVENANCE", "DATASET-GT-003", GateStatus.INSUFFICIENT_EVIDENCE, "computational data requires computational evidence classification; it is not experimental ground truth")
    if manifest.experimental_fraction <= 0:
        return GateResult("GATE-DATASET-PROVENANCE", "DATASET-GT-004", GateStatus.INSUFFICIENT_EVIDENCE, "dataset has no declared experimental fraction")
    level_order = {EvidenceLevel.E0_HEURISTIC: 0, EvidenceLevel.E1_ML: 1, EvidenceLevel.E2_COMPUTATIONAL: 2, EvidenceLevel.E3_PHYSICS: 3, EvidenceLevel.E4_CURATED_EXPERIMENTAL: 4, EvidenceLevel.E5_VALIDATED_EXPERIMENTAL: 5}
    observed_max = max((level_order[level] for level in manifest.evidence_levels), default=-1)
    if observed_max < level_order.get(requested_level, 0):
        return GateResult("GATE-DATASET-PROVENANCE", "DATASET-GT-005", GateStatus.INSUFFICIENT_EVIDENCE, "dataset evidence level does not support the requested experimental claim", diagnostics={"requested_level": requested_level.value, "observed_levels": [level.value for level in manifest.evidence_levels]})
    if not is_experimental_ground_truth(manifest):
        return GateResult("GATE-DATASET-PROVENANCE", "DATASET-GT-006", GateStatus.INSUFFICIENT_EVIDENCE, "dataset provenance is not sufficient for experimental ground truth")
    return GateResult("GATE-DATASET-PROVENANCE", "DATASET-GT-001", GateStatus.PASS, "dataset is explicitly classified as experimental ground truth")


# Explicit descriptive alias for callers validating the forbidden transition.
ml_prediction_to_experimental_gate = dataset_ground_truth_gate
