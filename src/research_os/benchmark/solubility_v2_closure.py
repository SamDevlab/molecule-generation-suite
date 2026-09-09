"""Closure checks for ONLINE-EXP-001 v2.

This module does not tune the accepted v2 model. It measures seed sensitivity
of the frozen hybrid structural protocol and compares the source dataset with a
structure-unique sensitivity view that excludes conflicting duplicate targets
without averaging them.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import statistics
from typing import Any, Mapping, Sequence

from research_os.benchmark.solubility import SolubilityBenchmarkError, SolubilityRecord, dataset_hash
from research_os.benchmark.solubility_v2 import (
    PROTOCOL_VERSION_V2,
    V2SplitEvaluation,
    _applicability,
    _fit_predict,
    canonical_identity,
    describe,
    hybrid_structural_split,
    structural_overlap_count,
)
from research_os.core.hashing import sha256_json

ROBUSTNESS_PROTOCOL = "research-os.online-exp-001.v2.robustness-v1"
SENSITIVITY_PROTOCOL = "research-os.online-exp-001.v2.unique-nonconflicting-v1"
DEFAULT_SEEDS = (7, 21, 42, 84, 101)


@dataclass(frozen=True)
class ScalarSummary:
    n: int
    mean: float
    stdev: float | None
    minimum: float
    maximum: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class CuratedDatasetView:
    records: tuple[SolubilityRecord, ...]
    original_record_count: int
    original_unique_structures: int
    kept_record_count: int
    conflicting_structure_groups_excluded: int
    conflicting_records_excluded: int
    same_target_duplicate_groups_collapsed: int
    redundant_same_target_records_collapsed: int
    lineage_hash: str

    def metadata(self) -> dict[str, Any]:
        return {
            "original_record_count": self.original_record_count,
            "original_unique_structures": self.original_unique_structures,
            "kept_record_count": self.kept_record_count,
            "conflicting_structure_groups_excluded": self.conflicting_structure_groups_excluded,
            "conflicting_records_excluded": self.conflicting_records_excluded,
            "same_target_duplicate_groups_collapsed": self.same_target_duplicate_groups_collapsed,
            "redundant_same_target_records_collapsed": self.redundant_same_target_records_collapsed,
            "lineage_hash": self.lineage_hash,
            "dataset_hash": dataset_hash(self.records),
        }


@dataclass(frozen=True)
class FrozenV2SeedResult:
    seed: int
    train_count: int
    validation_count: int
    test_count: int
    structural_overlap_count: int
    test_mae: float
    test_rmse: float
    test_r2: float
    ad_threshold: float
    in_domain_count: int
    out_of_domain_count: int
    in_domain_rmse: float | None
    out_of_domain_rmse: float | None
    similarity_bins: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: value for key, value in self.__dict__.items() if key != "similarity_bins"},
            "similarity_bins": [dict(item) for item in self.similarity_bins],
        }


def _summarize(values: Sequence[float]) -> ScalarSummary:
    data = [float(value) for value in values]
    if not data:
        raise SolubilityBenchmarkError("closure summary requires at least one value")
    return ScalarSummary(
        n=len(data),
        mean=statistics.fmean(data),
        stdev=statistics.stdev(data) if len(data) > 1 else None,
        minimum=min(data),
        maximum=max(data),
    )


def unique_nonconflicting_view(records: Sequence[SolubilityRecord]) -> CuratedDatasetView:
    """Return one record per non-conflicting canonical structure.

    Groups with multiple distinct measured targets are excluded completely.
    Exact/same-target duplicates are collapsed deterministically to one source
    row; no target averaging or imputation occurs.
    """
    groups: dict[str, list[SolubilityRecord]] = defaultdict(list)
    for record in records:
        canonical, _ = canonical_identity(record.smiles)
        groups[canonical].append(record)

    kept: list[SolubilityRecord] = []
    conflicting_groups = conflicting_records = 0
    same_target_groups = redundant_same_target_records = 0
    decisions: list[dict[str, Any]] = []

    for canonical in sorted(groups):
        group = sorted(groups[canonical], key=lambda item: (item.compound_id, item.smiles, item.measured_log_s_mol_l))
        targets = {round(float(item.measured_log_s_mol_l), 12) for item in group}
        if len(targets) > 1:
            conflicting_groups += 1
            conflicting_records += len(group)
            decisions.append({
                "canonical": canonical,
                "action": "exclude_conflicting_group",
                "source_rows": [item.compound_id for item in group],
                "targets": sorted(targets),
            })
            continue
        kept.append(group[0])
        if len(group) > 1:
            same_target_groups += 1
            redundant_same_target_records += len(group) - 1
            decisions.append({
                "canonical": canonical,
                "action": "keep_one_same_target_duplicate",
                "kept": group[0].compound_id,
                "dropped": [item.compound_id for item in group[1:]],
                "target": next(iter(targets)),
            })
        else:
            decisions.append({"canonical": canonical, "action": "keep_unique", "kept": group[0].compound_id})

    lineage_hash = sha256_json({
        "protocol": SENSITIVITY_PROTOCOL,
        "source_dataset_hash": dataset_hash(records),
        "decisions": decisions,
    })
    return CuratedDatasetView(
        records=tuple(kept),
        original_record_count=len(records),
        original_unique_structures=len(groups),
        kept_record_count=len(kept),
        conflicting_structure_groups_excluded=conflicting_groups,
        conflicting_records_excluded=conflicting_records,
        same_target_duplicate_groups_collapsed=same_target_groups,
        redundant_same_target_records_collapsed=redundant_same_target_records,
        lineage_hash=lineage_hash,
    )


def run_frozen_v2_seed(records: Sequence[SolubilityRecord], *, seed: int) -> FrozenV2SeedResult:
    """Run only the frozen v2 combined-RF + applicability-domain core."""
    split = hybrid_structural_split(records, validation_size=0.1, test_size=0.1, seed=seed)
    overlap = structural_overlap_count(split)
    if overlap:
        raise SolubilityBenchmarkError(f"structural group leakage detected in closure run: {overlap}")
    combined = _fit_predict(split, "random_forest_combined", "descriptors+morgan", seed)
    evaluation = V2SplitEvaluation(
        strategy="hybrid_structural",
        train_count=len(split.train),
        validation_count=len(split.validation),
        test_count=len(split.test),
        structural_overlap_count=overlap,
        target_distribution={
            "train": describe([item.measured_log_s_mol_l for item in split.train]),
            "validation": describe([item.measured_log_s_mol_l for item in split.validation]),
            "test": describe([item.measured_log_s_mol_l for item in split.test]),
        },
        models=(combined,),
    )
    domain = _applicability(split, evaluation)
    domain_summary = domain.model_summaries[0]
    return FrozenV2SeedResult(
        seed=seed,
        train_count=len(split.train),
        validation_count=len(split.validation),
        test_count=len(split.test),
        structural_overlap_count=overlap,
        test_mae=combined.test_metrics.mae,
        test_rmse=combined.test_metrics.rmse,
        test_r2=combined.test_metrics.r2,
        ad_threshold=domain.threshold,
        in_domain_count=domain_summary.in_domain_count,
        out_of_domain_count=domain_summary.out_of_domain_count,
        in_domain_rmse=None if domain_summary.in_domain_metrics is None else domain_summary.in_domain_metrics.rmse,
        out_of_domain_rmse=None if domain_summary.out_of_domain_metrics is None else domain_summary.out_of_domain_metrics.rmse,
        similarity_bins=tuple(item.to_dict() for item in domain.combined_rf_similarity_bins),
    )


def run_v2_robustness(records: Sequence[SolubilityRecord], *, seeds: Sequence[int] = DEFAULT_SEEDS) -> dict[str, Any]:
    if not seeds:
        raise SolubilityBenchmarkError("v2 robustness requires at least one seed")
    runs = tuple(run_frozen_v2_seed(records, seed=int(seed)) for seed in seeds)
    threshold = _summarize([run.ad_threshold for run in runs])
    rmse = _summarize([run.test_rmse for run in runs])
    mae = _summarize([run.test_mae for run in runs])
    r2 = _summarize([run.test_r2 for run in runs])
    ood_count = _summarize([float(run.out_of_domain_count) for run in runs])
    id_rmse_values = [run.in_domain_rmse for run in runs if run.in_domain_rmse is not None]
    ood_rmse_values = [run.out_of_domain_rmse for run in runs if run.out_of_domain_rmse is not None]
    payload = {
        "protocol_version": ROBUSTNESS_PROTOCOL,
        "parent_protocol": PROTOCOL_VERSION_V2,
        "dataset_hash": dataset_hash(records),
        "seeds": [int(seed) for seed in seeds],
        "runs": [run.to_dict() for run in runs],
        "summary": {
            "test_mae": mae.to_dict(),
            "test_rmse": rmse.to_dict(),
            "test_r2": r2.to_dict(),
            "ad_threshold": threshold.to_dict(),
            "out_of_domain_count": ood_count.to_dict(),
            "in_domain_rmse": _summarize(id_rmse_values).to_dict() if id_rmse_values else None,
            "out_of_domain_rmse": _summarize(ood_rmse_values).to_dict() if ood_rmse_values else None,
        },
        "notes": [
            "The accepted v2 model specification is unchanged across seeds.",
            "Descriptor ablation is not repeated because this closure check targets split/domain robustness, not feature selection.",
            "OOD subset sizes may remain small; OOD RMSE dispersion is therefore descriptive rather than a stable population estimate.",
        ],
    }
    return {**payload, "report_hash": sha256_json(payload)}


def run_v2_dataset_sensitivity(records: Sequence[SolubilityRecord], *, seed: int = 42) -> dict[str, Any]:
    curated = unique_nonconflicting_view(records)
    original = run_frozen_v2_seed(records, seed=seed)
    sensitivity = run_frozen_v2_seed(curated.records, seed=seed)
    payload = {
        "protocol_version": SENSITIVITY_PROTOCOL,
        "parent_protocol": PROTOCOL_VERSION_V2,
        "seed": seed,
        "source_dataset_hash": dataset_hash(records),
        "curated_view": curated.metadata(),
        "original": original.to_dict(),
        "unique_nonconflicting": sensitivity.to_dict(),
        "delta_unique_minus_original": {
            "test_mae": sensitivity.test_mae - original.test_mae,
            "test_rmse": sensitivity.test_rmse - original.test_rmse,
            "test_r2": sensitivity.test_r2 - original.test_r2,
            "ad_threshold": sensitivity.ad_threshold - original.ad_threshold,
            "out_of_domain_count": sensitivity.out_of_domain_count - original.out_of_domain_count,
            "in_domain_rmse": None if original.in_domain_rmse is None or sensitivity.in_domain_rmse is None else sensitivity.in_domain_rmse - original.in_domain_rmse,
            "out_of_domain_rmse": None if original.out_of_domain_rmse is None or sensitivity.out_of_domain_rmse is None else sensitivity.out_of_domain_rmse - original.out_of_domain_rmse,
        },
        "notes": [
            "Conflicting duplicate structures are excluded as complete groups; their targets are never averaged.",
            "Same-target duplicate structures are collapsed deterministically to one source row.",
            "This is a sensitivity analysis, not a replacement of the accepted source-dataset v2 result.",
        ],
    }
    return {**payload, "report_hash": sha256_json(payload)}
