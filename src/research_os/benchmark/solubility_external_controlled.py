"""ONLINE-EXP-004: controlled AqSolDB reliability-stratum error diagnostics."""
from __future__ import annotations

from dataclasses import dataclass
import math
import statistics
from typing import Any, Mapping, Sequence

from research_os.benchmark.solubility import (
    SolubilityBenchmarkError,
    SolubilityRecord,
    dataset_hash,
    download_delaney,
)
from research_os.benchmark.solubility_external import (
    AQSOLDB_DOI,
    AQSOLDB_SOURCE_BLOB_SHA,
    AQSOLDB_SOURCE_COMMIT,
    AQSOLDB_URL,
    EXPECTED_PARENT_TRAIN_COUNT,
    PARENT_SEED,
    AqSolDBParseAudit,
    AqSolDBRecord,
    _combined_features,
    curate_external_records,
)
from research_os.benchmark.solubility_external_reliability import (
    EXPECTED_AD_THRESHOLD,
    EXPECTED_EXTERNAL_COUNT,
    EXPECTED_EXTERNAL_HASH,
    EXPECTED_PARENT_TRAIN_HASH,
    AqSolDBReliabilityRecord,
    download_aqsoldb_with_reliability,
)
from research_os.benchmark.solubility_v2 import (
    AD_TRAIN_QUANTILE,
    _fingerprint,
    _max_train_similarity,
    _percentile,
    _training_loo_similarities,
    hybrid_structural_split,
)
from research_os.core.hashing import sha256_json


EXPERIMENT_ID = "ONLINE-EXP-004"
PROTOCOL_VERSION = "research-os.online-exp-004.controlled-confounders-v1"
PARENT_RELIABILITY_PROTOCOL = "research-os.online-exp-003.aqsoldb-reliability-v1"
EXPECTED_RELIABILITY_METADATA_HASH = "6cfeceee8f06b8e388fb86b172e0d2bb9c2e701002a530761502c543ad87c0a5"
HIGHER_DISPERSION_GROUPS = ("G2", "G4")
LOWER_DISPERSION_GROUPS = ("G3", "G5")
SIMILARITY_BINS = (
    (0.0, 0.4, "[0.0,0.4)"),
    (0.4, 0.6, "[0.4,0.6)"),
    (0.6, 0.8, "[0.6,0.8)"),
    (0.8, 1.0, "[0.8,1.0]"),
)
TARGET_BINS = (
    (None, -6.0, "(-inf,-6)"),
    (-6.0, -4.0, "[-6,-4)"),
    (-4.0, -2.0, "[-4,-2)"),
    (-2.0, 0.0, "[-2,0)"),
    (0.0, None, "[0,+inf)"),
)


@dataclass(frozen=True)
class ControlledObservation:
    source_id: str
    group: str
    cohort: str
    truth: float
    prediction: float
    max_train_similarity: float
    ad_status: str
    similarity_bin: str
    target_bin: str

    @property
    def signed_error(self) -> float:
        return self.prediction - self.truth

    @property
    def absolute_error(self) -> float:
        return abs(self.signed_error)

    @property
    def squared_error(self) -> float:
        return self.signed_error**2

    @property
    def cell_key(self) -> tuple[str, str, str]:
        return (self.ad_status, self.similarity_bin, self.target_bin)


@dataclass(frozen=True)
class CellMetrics:
    n: int
    mae: float
    mse: float
    rmse: float
    mean_signed_error: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class SharedCellSummary:
    ad_status: str
    similarity_bin: str
    target_bin: str
    higher: CellMetrics
    lower: CellMetrics
    matching_support: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "ad_status": self.ad_status,
            "similarity_bin": self.similarity_bin,
            "target_bin": self.target_bin,
            "higher_dispersion": self.higher.to_dict(),
            "lower_dispersion": self.lower.to_dict(),
            "matching_support": self.matching_support,
            "mae_delta_higher_minus_lower": self.higher.mae - self.lower.mae,
            "rmse_delta_higher_minus_lower": self.higher.rmse - self.lower.rmse,
        }


@dataclass(frozen=True)
class ControlledCoverage:
    total_higher_dispersion: int
    total_lower_dispersion: int
    shared_cell_higher_dispersion: int
    shared_cell_lower_dispersion: int
    shared_cell_fraction_higher_dispersion: float
    shared_cell_fraction_lower_dispersion: float
    shared_cell_count: int
    matching_support: int

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class ControlledMetrics:
    higher_dispersion_mae: float
    lower_dispersion_mae: float
    higher_dispersion_rmse: float
    lower_dispersion_rmse: float
    mae_delta_higher_minus_lower: float
    rmse_delta_higher_minus_lower: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class ControlledStandardization:
    coverage: ControlledCoverage
    metrics: ControlledMetrics
    shared_cells: tuple[SharedCellSummary, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage": self.coverage.to_dict(),
            "metrics": self.metrics.to_dict(),
            "shared_cells": [cell.to_dict() for cell in self.shared_cells],
        }


@dataclass(frozen=True)
class ControlledConfounderReport:
    experiment_id: str
    protocol_version: str
    parent_reliability_protocol: str
    external_source_url: str
    external_source_doi: str
    external_source_commit: str
    external_source_blob_sha: str
    base_parse_audit: AqSolDBParseAudit
    reliability_metadata_hash: str
    retained_external_count: int
    retained_external_hash: str
    parent_training_count: int
    parent_training_hash: str
    applicability_domain_threshold: float
    model: str
    representation: str
    hyperparameters: Mapping[str, Any]
    confounder_schema: Mapping[str, Any]
    controlled: ControlledStandardization
    notes: tuple[str, ...]

    def _payload(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "protocol_version": self.protocol_version,
            "parent_reliability_protocol": self.parent_reliability_protocol,
            "external_source_url": self.external_source_url,
            "external_source_doi": self.external_source_doi,
            "external_source_commit": self.external_source_commit,
            "external_source_blob_sha": self.external_source_blob_sha,
            "base_parse_audit": self.base_parse_audit.to_dict(),
            "reliability_metadata_hash": self.reliability_metadata_hash,
            "retained_external_count": self.retained_external_count,
            "retained_external_hash": self.retained_external_hash,
            "parent_training_count": self.parent_training_count,
            "parent_training_hash": self.parent_training_hash,
            "applicability_domain_threshold": self.applicability_domain_threshold,
            "model": self.model,
            "representation": self.representation,
            "hyperparameters": dict(self.hyperparameters),
            "confounder_schema": dict(self.confounder_schema),
            "controlled": self.controlled.to_dict(),
            "notes": list(self.notes),
        }

    @property
    def report_hash(self) -> str:
        return sha256_json(self._payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "report_hash": self.report_hash}


def _assign_cohort(group: str) -> str | None:
    if group in HIGHER_DISPERSION_GROUPS:
        return "higher_dispersion"
    if group in LOWER_DISPERSION_GROUPS:
        return "lower_dispersion"
    if group == "G1":
        return None
    raise SolubilityBenchmarkError(f"unexpected reliability group: {group!r}")


def _similarity_bin(value: float) -> str:
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        raise SolubilityBenchmarkError(f"invalid maximum-train similarity: {value!r}")
    for lower, upper, label in SIMILARITY_BINS:
        if lower <= value < upper or (upper == 1.0 and value == 1.0):
            return label
    raise SolubilityBenchmarkError(f"similarity did not map to a frozen bin: {value!r}")


def _target_bin(value: float) -> str:
    if not math.isfinite(value):
        raise SolubilityBenchmarkError(f"invalid measured logS: {value!r}")
    for lower, upper, label in TARGET_BINS:
        lower_ok = lower is None or value >= lower
        upper_ok = upper is None or value < upper
        if lower_ok and upper_ok:
            return label
    raise SolubilityBenchmarkError(f"target did not map to a frozen bin: {value!r}")


def _cell_metrics(records: Sequence[ControlledObservation]) -> CellMetrics:
    if not records:
        raise SolubilityBenchmarkError("controlled cell metrics require at least one record")
    absolute_errors = [record.absolute_error for record in records]
    squared_errors = [record.squared_error for record in records]
    signed_errors = [record.signed_error for record in records]
    mse = statistics.fmean(squared_errors)
    return CellMetrics(
        n=len(records),
        mae=statistics.fmean(absolute_errors),
        mse=mse,
        rmse=math.sqrt(mse),
        mean_signed_error=statistics.fmean(signed_errors),
    )


def standardize_controlled_error(records: Sequence[ControlledObservation]) -> ControlledStandardization:
    eligible = tuple(records)
    high_all = [record for record in eligible if record.cohort == "higher_dispersion"]
    low_all = [record for record in eligible if record.cohort == "lower_dispersion"]
    if not high_all or not low_all:
        raise SolubilityBenchmarkError("EXP-004 requires both repeated-observation dispersion cohorts")

    cells: dict[tuple[str, str, str], dict[str, list[ControlledObservation]]] = {}
    for record in eligible:
        if record.cohort not in {"higher_dispersion", "lower_dispersion"}:
            raise SolubilityBenchmarkError(f"unexpected controlled cohort: {record.cohort!r}")
        cohort_map = cells.setdefault(record.cell_key, {"higher_dispersion": [], "lower_dispersion": []})
        cohort_map[record.cohort].append(record)

    shared: list[SharedCellSummary] = []
    for key in sorted(cells):
        high = cells[key]["higher_dispersion"]
        low = cells[key]["lower_dispersion"]
        if not high or not low:
            continue
        high_metrics = _cell_metrics(high)
        low_metrics = _cell_metrics(low)
        shared.append(
            SharedCellSummary(
                ad_status=key[0],
                similarity_bin=key[1],
                target_bin=key[2],
                higher=high_metrics,
                lower=low_metrics,
                matching_support=min(len(high), len(low)),
            )
        )

    if not shared:
        raise SolubilityBenchmarkError("EXP-004 has no shared confounder cells")

    total_weight = sum(cell.matching_support for cell in shared)
    if total_weight <= 0:
        raise SolubilityBenchmarkError("EXP-004 matching support is empty")

    high_mae = sum(cell.matching_support * cell.higher.mae for cell in shared) / total_weight
    low_mae = sum(cell.matching_support * cell.lower.mae for cell in shared) / total_weight
    high_mse = sum(cell.matching_support * cell.higher.mse for cell in shared) / total_weight
    low_mse = sum(cell.matching_support * cell.lower.mse for cell in shared) / total_weight
    high_rmse = math.sqrt(high_mse)
    low_rmse = math.sqrt(low_mse)

    shared_high = sum(cell.higher.n for cell in shared)
    shared_low = sum(cell.lower.n for cell in shared)
    coverage = ControlledCoverage(
        total_higher_dispersion=len(high_all),
        total_lower_dispersion=len(low_all),
        shared_cell_higher_dispersion=shared_high,
        shared_cell_lower_dispersion=shared_low,
        shared_cell_fraction_higher_dispersion=shared_high / len(high_all),
        shared_cell_fraction_lower_dispersion=shared_low / len(low_all),
        shared_cell_count=len(shared),
        matching_support=total_weight,
    )
    metrics = ControlledMetrics(
        higher_dispersion_mae=high_mae,
        lower_dispersion_mae=low_mae,
        higher_dispersion_rmse=high_rmse,
        lower_dispersion_rmse=low_rmse,
        mae_delta_higher_minus_lower=high_mae - low_mae,
        rmse_delta_higher_minus_lower=high_rmse - low_rmse,
    )
    return ControlledStandardization(coverage=coverage, metrics=metrics, shared_cells=tuple(shared))


def run_controlled_confounder_analysis(
    esol_records: Sequence[SolubilityRecord],
    external_records: Sequence[AqSolDBRecord],
    base_parse_audit: AqSolDBParseAudit,
    reliability_records: Sequence[AqSolDBReliabilityRecord],
    reliability_metadata_hash: str,
) -> ControlledConfounderReport:
    esol = tuple(esol_records)
    external, curation = curate_external_records(esol, external_records)
    if curation.retained_record_count != EXPECTED_EXTERNAL_COUNT:
        raise SolubilityBenchmarkError(
            f"EXP-002 retained count drifted: expected {EXPECTED_EXTERNAL_COUNT}, got {curation.retained_record_count}"
        )
    if curation.retained_dataset_hash != EXPECTED_EXTERNAL_HASH:
        raise SolubilityBenchmarkError("EXP-002 retained external dataset hash drifted")
    if reliability_metadata_hash != EXPECTED_RELIABILITY_METADATA_HASH:
        raise SolubilityBenchmarkError("EXP-003 reliability metadata hash drifted")

    metadata_by_id = {record.source_id: record for record in reliability_records}
    retained_metadata: list[AqSolDBReliabilityRecord] = []
    for record in external:
        metadata = metadata_by_id.get(record.compound_id)
        if metadata is None:
            raise SolubilityBenchmarkError(f"missing reliability metadata for retained record: {record.compound_id}")
        retained_metadata.append(metadata)

    parent_split = hybrid_structural_split(esol, seed=PARENT_SEED)
    train = tuple(parent_split.train)
    if len(train) != EXPECTED_PARENT_TRAIN_COUNT:
        raise SolubilityBenchmarkError("parent v2 training count drifted")
    parent_training_hash = dataset_hash(train)
    if parent_training_hash != EXPECTED_PARENT_TRAIN_HASH:
        raise SolubilityBenchmarkError("parent v2 training hash drifted")

    try:
        from sklearn.ensemble import RandomForestRegressor
    except ImportError as exc:
        raise SolubilityBenchmarkError("ONLINE-EXP-004 requires scikit-learn; install the 'ml' extra") from exc

    hyperparameters = {
        "n_estimators": 300,
        "min_samples_leaf": 2,
        "random_state": PARENT_SEED,
        "n_jobs": 1,
    }
    model = RandomForestRegressor(**hyperparameters)
    model.fit(_combined_features(train), [record.measured_log_s_mol_l for record in train])
    prediction = [float(value) for value in model.predict(_combined_features(external))]

    train_fingerprints = [_fingerprint(record.smiles) for record in train]
    similarities = [
        _max_train_similarity(train_fingerprints, _fingerprint(record.smiles)) for record in external
    ]
    ad_threshold = _percentile(_training_loo_similarities(train), AD_TRAIN_QUANTILE)
    if not math.isclose(ad_threshold, EXPECTED_AD_THRESHOLD, rel_tol=0.0, abs_tol=1e-15):
        raise SolubilityBenchmarkError("EXP-002 applicability-domain threshold drifted")

    observations: list[ControlledObservation] = []
    for record, metadata, predicted, similarity in zip(
        external, retained_metadata, prediction, similarities, strict=True
    ):
        cohort = _assign_cohort(metadata.group)
        if cohort is None:
            continue
        truth = float(record.measured_log_s_mol_l)
        observations.append(
            ControlledObservation(
                source_id=record.compound_id,
                group=metadata.group,
                cohort=cohort,
                truth=truth,
                prediction=predicted,
                max_train_similarity=similarity,
                ad_status="ID" if similarity >= ad_threshold else "OOD",
                similarity_bin=_similarity_bin(similarity),
                target_bin=_target_bin(truth),
            )
        )

    controlled = standardize_controlled_error(observations)
    confounder_schema = {
        "ad_threshold": ad_threshold,
        "similarity_bins": [label for _, _, label in SIMILARITY_BINS],
        "target_bins": [label for _, _, label in TARGET_BINS],
        "shared_cell_rule": "both cohorts have at least one record",
        "cell_weight": "min(n_higher_dispersion, n_lower_dispersion)",
        "g1_policy": "excluded: single observation has no replicate-agreement information",
    }
    notes = (
        "The frozen EXP-001 v2 model, EXP-002 external set, and EXP-003 reliability metadata are unchanged.",
        "Only G2/G4 versus G3/G5 repeated-observation cohorts enter the controlled comparison; G1 is excluded by protocol.",
        "Controlled MAE and RMSE use identical shared-cell support weights for both cohorts.",
        "Applicability-domain status, similarity bins, and measured-logS bins were frozen before EXP-004 metrics were inspected.",
        "The analysis is descriptive and does not establish that measurement dispersion causes prediction error.",
        "No p-value, significance threshold, post-hoc binning, model tuning, or error-based record removal is performed.",
    )
    return ControlledConfounderReport(
        experiment_id=EXPERIMENT_ID,
        protocol_version=PROTOCOL_VERSION,
        parent_reliability_protocol=PARENT_RELIABILITY_PROTOCOL,
        external_source_url=AQSOLDB_URL,
        external_source_doi=AQSOLDB_DOI,
        external_source_commit=AQSOLDB_SOURCE_COMMIT,
        external_source_blob_sha=AQSOLDB_SOURCE_BLOB_SHA,
        base_parse_audit=base_parse_audit,
        reliability_metadata_hash=reliability_metadata_hash,
        retained_external_count=len(external),
        retained_external_hash=curation.retained_dataset_hash,
        parent_training_count=len(train),
        parent_training_hash=parent_training_hash,
        applicability_domain_threshold=ad_threshold,
        model="random_forest_combined",
        representation="8 RDKit descriptors + Morgan radius=2 bits=2048",
        hyperparameters=hyperparameters,
        confounder_schema=confounder_schema,
        controlled=controlled,
        notes=notes,
    )


def run_online_exp_004_from_public_sources() -> ControlledConfounderReport:
    esol = download_delaney()
    external, base_audit, reliability, metadata_hash = download_aqsoldb_with_reliability()
    return run_controlled_confounder_analysis(esol, external, base_audit, reliability, metadata_hash)
