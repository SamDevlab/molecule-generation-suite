"""ONLINE-EXP-003: reliability-stratified diagnostics on frozen AqSolDB validation."""
from __future__ import annotations

from dataclasses import dataclass
import csv
import io
import math
import statistics
from typing import Any, Mapping, Sequence
from urllib.request import Request, urlopen

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
    parse_aqsoldb_csv,
)
from research_os.benchmark.solubility_v2 import (
    AD_TRAIN_QUANTILE,
    MORGAN_BITS,
    MORGAN_RADIUS,
    _fingerprint,
    _max_train_similarity,
    _percentile,
    _training_loo_similarities,
    hybrid_structural_split,
)
from research_os.core.hashing import sha256_json
from research_os.ml.metrics import RegressionMetrics, compute_regression_metrics


EXPERIMENT_ID = "ONLINE-EXP-003"
PROTOCOL_VERSION = "research-os.online-exp-003.aqsoldb-reliability-v1"
PARENT_EXTERNAL_PROTOCOL = "research-os.online-exp-002.aqsoldb-external-v1"
EXPECTED_EXTERNAL_COUNT = 8863
EXPECTED_EXTERNAL_HASH = "0c3179ccdeb47b96b0afb3c38f61f6e9b95ab09c3071b18a433e3fb147d9c002"
EXPECTED_PARENT_TRAIN_HASH = "300ddc4981e1a9c2fb3735e598bcca89fb98a1cd4722cd58454e5d923781f00b"
EXPECTED_AD_THRESHOLD = 0.26684684684684684
RELIABILITY_GROUPS = ("G1", "G2", "G3", "G4", "G5")
CONSENSUS_STRATA: Mapping[str, tuple[str, ...]] = {
    "single_observation": ("G1",),
    "repeated_higher_dispersion": ("G2", "G4"),
    "repeated_lower_dispersion": ("G3", "G5"),
}


@dataclass(frozen=True)
class AqSolDBReliabilityRecord:
    source_id: str
    group: str
    occurrences: int
    sd: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "group": self.group,
            "occurrences": self.occurrences,
            "sd": self.sd,
        }


@dataclass(frozen=True)
class NumericDistribution:
    n: int
    mean: float
    median: float
    stdev: float | None
    minimum: float
    maximum: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class ReliabilityStratumSummary:
    name: str
    groups: tuple[str, ...]
    n: int
    metrics: RegressionMetrics
    target_distribution: NumericDistribution
    median_max_train_similarity: float
    median_curated_sd: float
    median_occurrences: float
    in_domain_count: int
    out_of_domain_count: int
    out_of_domain_fraction: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "groups": list(self.groups),
            "n": self.n,
            "metrics": self.metrics.to_dict(),
            "target_distribution": self.target_distribution.to_dict(),
            "median_max_train_similarity": self.median_max_train_similarity,
            "median_curated_sd": self.median_curated_sd,
            "median_occurrences": self.median_occurrences,
            "in_domain_count": self.in_domain_count,
            "out_of_domain_count": self.out_of_domain_count,
            "out_of_domain_fraction": self.out_of_domain_fraction,
        }


@dataclass(frozen=True)
class ReliabilityStratificationReport:
    experiment_id: str
    protocol_version: str
    parent_external_protocol: str
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
    per_group: tuple[ReliabilityStratumSummary, ...]
    consensus_strata: tuple[ReliabilityStratumSummary, ...]
    descriptive_deltas: Mapping[str, float]
    notes: tuple[str, ...]

    def _payload(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "protocol_version": self.protocol_version,
            "parent_external_protocol": self.parent_external_protocol,
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
            "per_group": [item.to_dict() for item in self.per_group],
            "consensus_strata": [item.to_dict() for item in self.consensus_strata],
            "descriptive_deltas": dict(self.descriptive_deltas),
            "notes": list(self.notes),
        }

    @property
    def report_hash(self) -> str:
        return sha256_json(self._payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "report_hash": self.report_hash}


def parse_reliability_metadata(text: str) -> tuple[tuple[AqSolDBReliabilityRecord, ...], str]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise SolubilityBenchmarkError("AqSolDB reliability analysis requires a CSV header")
    required = {"ID", "Group", "Occurrences", "SD"}
    missing = required.difference(reader.fieldnames)
    if missing:
        raise SolubilityBenchmarkError(f"AqSolDB reliability metadata is missing column(s): {sorted(missing)}")

    records: list[AqSolDBReliabilityRecord] = []
    seen_ids: set[str] = set()
    for row_index, row in enumerate(reader, start=2):
        source_id = str(row.get("ID") or "").strip()
        group = str(row.get("Group") or "").strip()
        if not source_id:
            raise SolubilityBenchmarkError(f"missing AqSolDB ID at row {row_index}")
        if source_id in seen_ids:
            raise SolubilityBenchmarkError(f"duplicate AqSolDB ID in reliability metadata: {source_id}")
        if group not in RELIABILITY_GROUPS:
            raise SolubilityBenchmarkError(f"unexpected AqSolDB reliability group at row {row_index}: {group!r}")
        try:
            occurrences = int(float(str(row.get("Occurrences") or "").strip()))
            sd = float(str(row.get("SD") or "").strip())
        except ValueError as exc:
            raise SolubilityBenchmarkError(f"invalid reliability metadata at row {row_index}") from exc
        if occurrences < 1 or not math.isfinite(sd) or sd < 0:
            raise SolubilityBenchmarkError(f"invalid reliability metadata at row {row_index}")
        records.append(AqSolDBReliabilityRecord(source_id, group, occurrences, sd))
        seen_ids.add(source_id)

    if not records:
        raise SolubilityBenchmarkError("AqSolDB reliability metadata contains no records")
    metadata_hash = sha256_json([record.to_dict() for record in records])
    return tuple(records), metadata_hash


def download_aqsoldb_with_reliability(
    *, url: str = AQSOLDB_URL, timeout: float = 60.0
) -> tuple[tuple[AqSolDBRecord, ...], AqSolDBParseAudit, tuple[AqSolDBReliabilityRecord, ...], str]:
    request = Request(url, headers={"User-Agent": "Research-OS/5.0 ONLINE-EXP-003"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - immutable HTTPS source by default
            payload = response.read().decode("utf-8")
    except Exception as exc:
        raise SolubilityBenchmarkError(f"failed to retrieve AqSolDB from {url}") from exc
    base_records, base_audit = parse_aqsoldb_csv(payload)
    reliability_records, metadata_hash = parse_reliability_metadata(payload)
    if len(base_records) != len(reliability_records):
        raise SolubilityBenchmarkError("AqSolDB base/reliability parse counts disagree")
    return base_records, base_audit, reliability_records, metadata_hash


def _distribution(values: Sequence[float]) -> NumericDistribution:
    data = [float(value) for value in values]
    if not data:
        raise SolubilityBenchmarkError("stratum distribution requires at least one value")
    return NumericDistribution(
        n=len(data),
        mean=statistics.fmean(data),
        median=statistics.median(data),
        stdev=statistics.stdev(data) if len(data) > 1 else None,
        minimum=min(data),
        maximum=max(data),
    )


def _summarize_stratum(
    name: str,
    groups: tuple[str, ...],
    selected_indices: Sequence[int],
    truth: Sequence[float],
    prediction: Sequence[float],
    similarities: Sequence[float],
    metadata: Sequence[AqSolDBReliabilityRecord],
    ad_threshold: float,
) -> ReliabilityStratumSummary:
    if not selected_indices:
        raise SolubilityBenchmarkError(f"reliability stratum is empty: {name}")
    selected_truth = [truth[index] for index in selected_indices]
    selected_prediction = [prediction[index] for index in selected_indices]
    selected_similarity = [similarities[index] for index in selected_indices]
    selected_metadata = [metadata[index] for index in selected_indices]
    in_domain = sum(value >= ad_threshold for value in selected_similarity)
    out_of_domain = len(selected_similarity) - in_domain
    return ReliabilityStratumSummary(
        name=name,
        groups=groups,
        n=len(selected_indices),
        metrics=compute_regression_metrics(selected_truth, selected_prediction),
        target_distribution=_distribution(selected_truth),
        median_max_train_similarity=statistics.median(selected_similarity),
        median_curated_sd=statistics.median(item.sd for item in selected_metadata),
        median_occurrences=statistics.median(item.occurrences for item in selected_metadata),
        in_domain_count=in_domain,
        out_of_domain_count=out_of_domain,
        out_of_domain_fraction=out_of_domain / len(selected_indices),
    )


def run_reliability_stratification(
    esol_records: Sequence[SolubilityRecord],
    external_records: Sequence[AqSolDBRecord],
    base_parse_audit: AqSolDBParseAudit,
    reliability_records: Sequence[AqSolDBReliabilityRecord],
    reliability_metadata_hash: str,
) -> ReliabilityStratificationReport:
    esol = tuple(esol_records)
    external, curation = curate_external_records(esol, external_records)
    if curation.retained_record_count != EXPECTED_EXTERNAL_COUNT:
        raise SolubilityBenchmarkError(
            f"EXP-002 retained count drifted: expected {EXPECTED_EXTERNAL_COUNT}, got {curation.retained_record_count}"
        )
    if curation.retained_dataset_hash != EXPECTED_EXTERNAL_HASH:
        raise SolubilityBenchmarkError("EXP-002 retained external dataset hash drifted")

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
        raise SolubilityBenchmarkError("ONLINE-EXP-003 requires scikit-learn; install the 'ml' extra") from exc

    hyperparameters = {
        "n_estimators": 300,
        "min_samples_leaf": 2,
        "random_state": PARENT_SEED,
        "n_jobs": 1,
    }
    model = RandomForestRegressor(**hyperparameters)
    model.fit(_combined_features(train), [record.measured_log_s_mol_l for record in train])
    truth = [record.measured_log_s_mol_l for record in external]
    prediction = [float(value) for value in model.predict(_combined_features(external))]

    train_fingerprints = [_fingerprint(record.smiles) for record in train]
    similarities = [
        _max_train_similarity(train_fingerprints, _fingerprint(record.smiles)) for record in external
    ]
    ad_threshold = _percentile(_training_loo_similarities(train), AD_TRAIN_QUANTILE)
    if not math.isclose(ad_threshold, EXPECTED_AD_THRESHOLD, rel_tol=0.0, abs_tol=1e-15):
        raise SolubilityBenchmarkError("EXP-002 applicability-domain threshold drifted")

    per_group = tuple(
        _summarize_stratum(
            group,
            (group,),
            [index for index, item in enumerate(retained_metadata) if item.group == group],
            truth,
            prediction,
            similarities,
            retained_metadata,
            ad_threshold,
        )
        for group in RELIABILITY_GROUPS
    )
    consensus = tuple(
        _summarize_stratum(
            name,
            groups,
            [index for index, item in enumerate(retained_metadata) if item.group in groups],
            truth,
            prediction,
            similarities,
            retained_metadata,
            ad_threshold,
        )
        for name, groups in CONSENSUS_STRATA.items()
    )
    by_name = {item.name: item for item in consensus}
    high = by_name["repeated_higher_dispersion"]
    low = by_name["repeated_lower_dispersion"]
    deltas = {
        "rmse_higher_minus_lower_dispersion": high.metrics.rmse - low.metrics.rmse,
        "mae_higher_minus_lower_dispersion": high.metrics.mae - low.metrics.mae,
        "ood_fraction_higher_minus_lower_dispersion": high.out_of_domain_fraction - low.out_of_domain_fraction,
        "median_similarity_higher_minus_lower_dispersion": (
            high.median_max_train_similarity - low.median_max_train_similarity
        ),
    }

    return ReliabilityStratificationReport(
        experiment_id=EXPERIMENT_ID,
        protocol_version=PROTOCOL_VERSION,
        parent_external_protocol=PARENT_EXTERNAL_PROTOCOL,
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
        representation=f"8 RDKit descriptors + Morgan radius={MORGAN_RADIUS} bits={MORGAN_BITS}",
        hyperparameters=hyperparameters,
        per_group=per_group,
        consensus_strata=consensus,
        descriptive_deltas=deltas,
        notes=(
            "Reliability strata come from AqSolDB's published curation metadata and do not alter model fitting or decontamination.",
            "G1 is a single-observation stratum and does not provide replicate agreement information.",
            "G2/G4 are predeclared as repeated higher-dispersion strata; G3/G5 as repeated lower-dispersion strata.",
            "Observed error differences are descriptive associations and may be confounded by chemical-space, target-range, source, and protocol differences.",
            "No p-value, causal claim, reliability calibration, model tuning, or post-hoc threshold selection is performed.",
            "R2 is a regression score, not a confidence or reliability percentage.",
        ),
    )


def run_online_exp_003_from_public_sources() -> ReliabilityStratificationReport:
    esol = download_delaney()
    external, base_audit, reliability, metadata_hash = download_aqsoldb_with_reliability()
    return run_reliability_stratification(esol, external, base_audit, reliability, metadata_hash)
