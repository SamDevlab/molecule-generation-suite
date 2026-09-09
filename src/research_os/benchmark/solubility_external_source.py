"""ONLINE-EXP-005: source-aware control of AqSolDB reliability-stratum error."""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
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
from research_os.benchmark.solubility_external_controlled import (
    EXPECTED_RELIABILITY_METADATA_HASH,
    _assign_cohort,
    _cell_metrics,
    _similarity_bin,
    _target_bin,
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


EXPERIMENT_ID = "ONLINE-EXP-005"
PROTOCOL_VERSION = "research-os.online-exp-005.source-protocol-stratification-v1"
PARENT_CONTROLLED_PROTOCOL = "research-os.online-exp-004.controlled-confounders-v1"
PARENT_CONTROLLED_REPORT_HASH = "f5f0bc3267dfe207e04cea6709c47dc90ac9794b51abe4aaddc0aabeb73cc709"
PARENT_CONTROLLED_SCIENTIFIC_HASH = "2427a72653d0adee34e30fa241c1dd416925159ad7b84bdc495f698913e95143"
SOURCE_PATTERN = re.compile(r"^([A-I])-")
MIN_MATCHING_SUPPORT = 50
MIN_SHARED_FRACTION = 0.50
MIN_CONTRIBUTING_SOURCES = 2


@dataclass(frozen=True)
class SourceAwareObservation:
    source_id: str
    source_dataset: str
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
    def cell_key(self) -> tuple[str, str, str, str]:
        return (
            self.source_dataset,
            self.ad_status,
            self.similarity_bin,
            self.target_bin,
        )


@dataclass(frozen=True)
class SourceAwareCellSummary:
    source_dataset: str
    ad_status: str
    similarity_bin: str
    target_bin: str
    higher: Any
    lower: Any
    matching_support: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_dataset": self.source_dataset,
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
class SourceContribution:
    source_dataset: str
    higher_total: int
    lower_total: int
    higher_shared: int
    lower_shared: int
    matching_support: int
    shared_cell_count: int

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class SourceAwareCoverage:
    total_higher_dispersion: int
    total_lower_dispersion: int
    shared_cell_higher_dispersion: int
    shared_cell_lower_dispersion: int
    shared_cell_fraction_higher_dispersion: float
    shared_cell_fraction_lower_dispersion: float
    shared_cell_count: int
    matching_support: int
    contributing_sources: tuple[str, ...]
    interpretation_status: str
    support_requirements: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_higher_dispersion": self.total_higher_dispersion,
            "total_lower_dispersion": self.total_lower_dispersion,
            "shared_cell_higher_dispersion": self.shared_cell_higher_dispersion,
            "shared_cell_lower_dispersion": self.shared_cell_lower_dispersion,
            "shared_cell_fraction_higher_dispersion": self.shared_cell_fraction_higher_dispersion,
            "shared_cell_fraction_lower_dispersion": self.shared_cell_fraction_lower_dispersion,
            "shared_cell_count": self.shared_cell_count,
            "matching_support": self.matching_support,
            "contributing_sources": list(self.contributing_sources),
            "interpretation_status": self.interpretation_status,
            "support_requirements": dict(self.support_requirements),
        }


@dataclass(frozen=True)
class SourceAwareMetrics:
    higher_dispersion_mae: float
    lower_dispersion_mae: float
    higher_dispersion_rmse: float
    lower_dispersion_rmse: float
    mae_delta_higher_minus_lower: float
    rmse_delta_higher_minus_lower: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class SourceAwareStandardization:
    coverage: SourceAwareCoverage
    metrics: SourceAwareMetrics
    source_contributions: tuple[SourceContribution, ...]
    shared_cells: tuple[SourceAwareCellSummary, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage": self.coverage.to_dict(),
            "metrics": self.metrics.to_dict(),
            "source_contributions": [item.to_dict() for item in self.source_contributions],
            "shared_cells": [item.to_dict() for item in self.shared_cells],
        }


@dataclass(frozen=True)
class TargetDistribution:
    n: int
    mean: float
    median: float
    stdev: float | None
    minimum: float
    maximum: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class SourceCohortDiagnostic:
    cohort: str
    n: int
    mae: float
    rmse: float
    median_max_train_similarity: float
    in_domain_count: int
    out_of_domain_count: int
    target_distribution: TargetDistribution

    def to_dict(self) -> dict[str, Any]:
        return {
            "cohort": self.cohort,
            "n": self.n,
            "mae": self.mae,
            "rmse": self.rmse,
            "median_max_train_similarity": self.median_max_train_similarity,
            "in_domain_count": self.in_domain_count,
            "out_of_domain_count": self.out_of_domain_count,
            "target_distribution": self.target_distribution.to_dict(),
        }


@dataclass(frozen=True)
class SourceDiagnostic:
    source_dataset: str
    higher_dispersion: SourceCohortDiagnostic | None
    lower_dispersion: SourceCohortDiagnostic | None
    raw_mae_delta_higher_minus_lower: float | None
    raw_rmse_delta_higher_minus_lower: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_dataset": self.source_dataset,
            "higher_dispersion": None if self.higher_dispersion is None else self.higher_dispersion.to_dict(),
            "lower_dispersion": None if self.lower_dispersion is None else self.lower_dispersion.to_dict(),
            "raw_mae_delta_higher_minus_lower": self.raw_mae_delta_higher_minus_lower,
            "raw_rmse_delta_higher_minus_lower": self.raw_rmse_delta_higher_minus_lower,
        }


@dataclass(frozen=True)
class SourceProtocolReport:
    experiment_id: str
    protocol_version: str
    parent_controlled_protocol: str
    parent_controlled_report_hash: str
    parent_controlled_scientific_hash: str
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
    source_schema: Mapping[str, Any]
    controlled_source: SourceAwareStandardization
    source_diagnostics: tuple[SourceDiagnostic, ...]
    notes: tuple[str, ...]

    def _payload(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "protocol_version": self.protocol_version,
            "parent_controlled_protocol": self.parent_controlled_protocol,
            "parent_controlled_report_hash": self.parent_controlled_report_hash,
            "parent_controlled_scientific_hash": self.parent_controlled_scientific_hash,
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
            "source_schema": dict(self.source_schema),
            "controlled_source": self.controlled_source.to_dict(),
            "source_diagnostics": [item.to_dict() for item in self.source_diagnostics],
            "notes": list(self.notes),
        }

    @property
    def report_hash(self) -> str:
        return sha256_json(self._payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "report_hash": self.report_hash}


def source_dataset_from_id(source_id: str) -> str:
    match = SOURCE_PATTERN.match(source_id)
    if match is None:
        raise SolubilityBenchmarkError(
            f"EXP-005 requires immutable AqSolDB source prefix A-I: {source_id!r}"
        )
    return match.group(1)


def _target_distribution(records: Sequence[SourceAwareObservation]) -> TargetDistribution:
    if not records:
        raise SolubilityBenchmarkError("source diagnostic target distribution requires records")
    values = [record.truth for record in records]
    return TargetDistribution(
        n=len(values),
        mean=statistics.fmean(values),
        median=statistics.median(values),
        stdev=statistics.stdev(values) if len(values) > 1 else None,
        minimum=min(values),
        maximum=max(values),
    )


def _cohort_diagnostic(
    cohort: str, records: Sequence[SourceAwareObservation]
) -> SourceCohortDiagnostic:
    if not records:
        raise SolubilityBenchmarkError("source cohort diagnostic requires records")
    metrics = _cell_metrics(records)
    similarities = [record.max_train_similarity for record in records]
    in_domain = sum(record.ad_status == "ID" for record in records)
    return SourceCohortDiagnostic(
        cohort=cohort,
        n=len(records),
        mae=metrics.mae,
        rmse=metrics.rmse,
        median_max_train_similarity=statistics.median(similarities),
        in_domain_count=in_domain,
        out_of_domain_count=len(records) - in_domain,
        target_distribution=_target_distribution(records),
    )


def summarize_sources(
    records: Sequence[SourceAwareObservation],
) -> tuple[SourceDiagnostic, ...]:
    by_source: dict[str, dict[str, list[SourceAwareObservation]]] = {}
    for record in records:
        bucket = by_source.setdefault(
            record.source_dataset,
            {"higher_dispersion": [], "lower_dispersion": []},
        )
        bucket[record.cohort].append(record)

    summaries: list[SourceDiagnostic] = []
    for source_dataset in sorted(by_source):
        high_records = by_source[source_dataset]["higher_dispersion"]
        low_records = by_source[source_dataset]["lower_dispersion"]
        high = _cohort_diagnostic("higher_dispersion", high_records) if high_records else None
        low = _cohort_diagnostic("lower_dispersion", low_records) if low_records else None
        summaries.append(
            SourceDiagnostic(
                source_dataset=source_dataset,
                higher_dispersion=high,
                lower_dispersion=low,
                raw_mae_delta_higher_minus_lower=None
                if high is None or low is None
                else high.mae - low.mae,
                raw_rmse_delta_higher_minus_lower=None
                if high is None or low is None
                else high.rmse - low.rmse,
            )
        )
    return tuple(summaries)


def standardize_source_aware_error(
    records: Sequence[SourceAwareObservation],
) -> SourceAwareStandardization:
    eligible = tuple(records)
    high_all = [record for record in eligible if record.cohort == "higher_dispersion"]
    low_all = [record for record in eligible if record.cohort == "lower_dispersion"]
    if not high_all or not low_all:
        raise SolubilityBenchmarkError("EXP-005 requires both repeated-observation dispersion cohorts")

    cells: dict[
        tuple[str, str, str, str],
        dict[str, list[SourceAwareObservation]],
    ] = {}
    for record in eligible:
        if record.cohort not in {"higher_dispersion", "lower_dispersion"}:
            raise SolubilityBenchmarkError(f"unexpected source-aware cohort: {record.cohort!r}")
        bucket = cells.setdefault(
            record.cell_key,
            {"higher_dispersion": [], "lower_dispersion": []},
        )
        bucket[record.cohort].append(record)

    shared: list[SourceAwareCellSummary] = []
    for key in sorted(cells):
        high = cells[key]["higher_dispersion"]
        low = cells[key]["lower_dispersion"]
        if not high or not low:
            continue
        shared.append(
            SourceAwareCellSummary(
                source_dataset=key[0],
                ad_status=key[1],
                similarity_bin=key[2],
                target_bin=key[3],
                higher=_cell_metrics(high),
                lower=_cell_metrics(low),
                matching_support=min(len(high), len(low)),
            )
        )

    if not shared:
        raise SolubilityBenchmarkError("EXP-005 has no shared source-aware cells")

    total_weight = sum(cell.matching_support for cell in shared)
    if total_weight <= 0:
        raise SolubilityBenchmarkError("EXP-005 matching support is empty")

    high_mae = sum(cell.matching_support * cell.higher.mae for cell in shared) / total_weight
    low_mae = sum(cell.matching_support * cell.lower.mae for cell in shared) / total_weight
    high_mse = sum(cell.matching_support * cell.higher.mse for cell in shared) / total_weight
    low_mse = sum(cell.matching_support * cell.lower.mse for cell in shared) / total_weight
    high_rmse = math.sqrt(high_mse)
    low_rmse = math.sqrt(low_mse)

    shared_high = sum(cell.higher.n for cell in shared)
    shared_low = sum(cell.lower.n for cell in shared)
    contributing_sources = tuple(sorted({cell.source_dataset for cell in shared}))
    high_fraction = shared_high / len(high_all)
    low_fraction = shared_low / len(low_all)
    interpretation_status = (
        "SUPPORTED"
        if (
            total_weight >= MIN_MATCHING_SUPPORT
            and high_fraction >= MIN_SHARED_FRACTION
            and low_fraction >= MIN_SHARED_FRACTION
            and len(contributing_sources) >= MIN_CONTRIBUTING_SOURCES
        )
        else "INSUFFICIENT_OVERLAP"
    )

    source_totals: dict[str, dict[str, int]] = {}
    for record in eligible:
        source_totals.setdefault(
            record.source_dataset,
            {"higher_dispersion": 0, "lower_dispersion": 0},
        )[record.cohort] += 1
    source_shared: dict[str, dict[str, int]] = {}
    source_weight: dict[str, int] = {}
    source_cells: dict[str, int] = {}
    for cell in shared:
        source_shared.setdefault(
            cell.source_dataset,
            {"higher_dispersion": 0, "lower_dispersion": 0},
        )["higher_dispersion"] += cell.higher.n
        source_shared[cell.source_dataset]["lower_dispersion"] += cell.lower.n
        source_weight[cell.source_dataset] = source_weight.get(cell.source_dataset, 0) + cell.matching_support
        source_cells[cell.source_dataset] = source_cells.get(cell.source_dataset, 0) + 1

    contributions = tuple(
        SourceContribution(
            source_dataset=source_dataset,
            higher_total=source_totals[source_dataset]["higher_dispersion"],
            lower_total=source_totals[source_dataset]["lower_dispersion"],
            higher_shared=source_shared.get(
                source_dataset,
                {"higher_dispersion": 0, "lower_dispersion": 0},
            )["higher_dispersion"],
            lower_shared=source_shared.get(
                source_dataset,
                {"higher_dispersion": 0, "lower_dispersion": 0},
            )["lower_dispersion"],
            matching_support=source_weight.get(source_dataset, 0),
            shared_cell_count=source_cells.get(source_dataset, 0),
        )
        for source_dataset in sorted(source_totals)
    )

    coverage = SourceAwareCoverage(
        total_higher_dispersion=len(high_all),
        total_lower_dispersion=len(low_all),
        shared_cell_higher_dispersion=shared_high,
        shared_cell_lower_dispersion=shared_low,
        shared_cell_fraction_higher_dispersion=high_fraction,
        shared_cell_fraction_lower_dispersion=low_fraction,
        shared_cell_count=len(shared),
        matching_support=total_weight,
        contributing_sources=contributing_sources,
        interpretation_status=interpretation_status,
        support_requirements={
            "minimum_matching_support": MIN_MATCHING_SUPPORT,
            "minimum_shared_fraction_per_cohort": MIN_SHARED_FRACTION,
            "minimum_contributing_sources": MIN_CONTRIBUTING_SOURCES,
        },
    )
    metrics = SourceAwareMetrics(
        higher_dispersion_mae=high_mae,
        lower_dispersion_mae=low_mae,
        higher_dispersion_rmse=high_rmse,
        lower_dispersion_rmse=low_rmse,
        mae_delta_higher_minus_lower=high_mae - low_mae,
        rmse_delta_higher_minus_lower=high_rmse - low_rmse,
    )
    return SourceAwareStandardization(
        coverage=coverage,
        metrics=metrics,
        source_contributions=contributions,
        shared_cells=tuple(shared),
    )


def run_source_protocol_stratification(
    esol_records: Sequence[SolubilityRecord],
    external_records: Sequence[AqSolDBRecord],
    base_parse_audit: AqSolDBParseAudit,
    reliability_records: Sequence[AqSolDBReliabilityRecord],
    reliability_metadata_hash: str,
) -> SourceProtocolReport:
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
            raise SolubilityBenchmarkError(
                f"missing reliability metadata for retained record: {record.compound_id}"
            )
        source_dataset_from_id(record.compound_id)
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
        raise SolubilityBenchmarkError(
            "ONLINE-EXP-005 requires scikit-learn; install the 'ml' extra"
        ) from exc

    hyperparameters = {
        "n_estimators": 300,
        "min_samples_leaf": 2,
        "random_state": PARENT_SEED,
        "n_jobs": 1,
    }
    model = RandomForestRegressor(**hyperparameters)
    model.fit(
        _combined_features(train),
        [record.measured_log_s_mol_l for record in train],
    )
    predictions = [
        float(value)
        for value in model.predict(_combined_features(external))
    ]

    train_fingerprints = [_fingerprint(record.smiles) for record in train]
    similarities = [
        _max_train_similarity(train_fingerprints, _fingerprint(record.smiles))
        for record in external
    ]
    ad_threshold = _percentile(
        _training_loo_similarities(train),
        AD_TRAIN_QUANTILE,
    )
    if not math.isclose(
        ad_threshold,
        EXPECTED_AD_THRESHOLD,
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise SolubilityBenchmarkError("EXP-002 applicability-domain threshold drifted")

    observations: list[SourceAwareObservation] = []
    for record, metadata, predicted, similarity in zip(
        external,
        retained_metadata,
        predictions,
        similarities,
        strict=True,
    ):
        cohort = _assign_cohort(metadata.group)
        if cohort is None:
            continue
        truth = float(record.measured_log_s_mol_l)
        observations.append(
            SourceAwareObservation(
                source_id=record.compound_id,
                source_dataset=source_dataset_from_id(record.compound_id),
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

    controlled = standardize_source_aware_error(observations)
    diagnostics = summarize_sources(observations)
    source_schema = {
        "source_parser": "leading AqSolDB ID prefix matching ^([A-I])-",
        "source_datasets": list("ABCDEFGHI"),
        "cell_dimensions": [
            "source_dataset",
            "ad_status",
            "maximum_train_similarity_bin",
            "measured_logS_bin",
        ],
        "shared_cell_rule": "both cohorts have at least one record",
        "cell_weight": "min(n_higher_dispersion, n_lower_dispersion)",
        "support_status": {
            "minimum_matching_support": MIN_MATCHING_SUPPORT,
            "minimum_shared_fraction_per_cohort": MIN_SHARED_FRACTION,
            "minimum_contributing_sources": MIN_CONTRIBUTING_SOURCES,
        },
        "g1_policy": "excluded: single observation has no replicate-agreement information",
    }
    notes = (
        "The frozen EXP-001 v2 model, EXP-002 external set, EXP-003 reliability metadata, and EXP-004 cell boundaries are unchanged.",
        "AqSolDB source identity is parsed only from the immutable A-I record prefix and is treated as a coarse dataset/protocol-origin proxy.",
        "Primary source-aware MAE and RMSE use identical shared-cell support weights for both cohorts.",
        "The source-aware support thresholds were frozen before EXP-005 metrics were inspected.",
        "Secondary per-source summaries are descriptive diagnostics and do not remove or reweight sources.",
        "The analysis is observational and does not establish that measurement dispersion or source protocol causes prediction error.",
        "No p-value, post-hoc source grouping, model tuning, threshold relaxation, or error-based record removal is performed.",
    )
    return SourceProtocolReport(
        experiment_id=EXPERIMENT_ID,
        protocol_version=PROTOCOL_VERSION,
        parent_controlled_protocol=PARENT_CONTROLLED_PROTOCOL,
        parent_controlled_report_hash=PARENT_CONTROLLED_REPORT_HASH,
        parent_controlled_scientific_hash=PARENT_CONTROLLED_SCIENTIFIC_HASH,
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
        source_schema=source_schema,
        controlled_source=controlled,
        source_diagnostics=diagnostics,
        notes=notes,
    )


def run_online_exp_005_from_public_sources() -> SourceProtocolReport:
    esol = download_delaney()
    external, base_audit, reliability, metadata_hash = download_aqsoldb_with_reliability()
    return run_source_protocol_stratification(
        esol,
        external,
        base_audit,
        reliability,
        metadata_hash,
    )
