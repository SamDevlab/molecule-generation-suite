"""ONLINE-EXP-002: frozen-model external validation on decontaminated AqSolDB."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import csv
import io
import math
import statistics
from typing import Any, Mapping, Sequence
from urllib.request import Request, urlopen

from research_os.core.hashing import sha256_json
from research_os.ml.metrics import RegressionMetrics, compute_regression_metrics
from research_os.benchmark.solubility import (
    DATASET_HASH if False else DATASET_ID,  # type: ignore[attr-defined]
    SolubilityBenchmarkError,
    SolubilityRecord,
    dataset_hash,
    descriptor_vector,
    download_delaney,
)
from research_os.benchmark.solubility_v2 import (
    AD_TRAIN_QUANTILE,
    MORGAN_BITS,
    MORGAN_RADIUS,
    SIMILARITY_BINS,
    _fingerprint,
    _max_train_similarity,
    _percentile,
    _training_loo_similarities,
    canonical_identity,
    hybrid_structural_split,
    morgan_vector,
)


EXPERIMENT_ID = "ONLINE-EXP-002"
PROTOCOL_VERSION = "research-os.online-exp-002.aqsoldb-external-v1"
PARENT_PROTOCOL = "research-os.online-exp-001.v2"
PARENT_SEED = 42
EXPECTED_PARENT_TRAIN_COUNT = 902
AQSOLDB_ID = "AqSolDB"
AQSOLDB_DOI = "10.1038/s41597-019-0151-1"
AQSOLDB_SOURCE_COMMIT = "98cdd10a372058743e4f3fb950a1c9974ec9603a"
AQSOLDB_SOURCE_BLOB_SHA = "67016e030cf0a741e250ba0267bd84461041db5f"
AQSOLDB_URL = (
    "https://raw.githubusercontent.com/mcsorkun/AqSolDB/"
    f"{AQSOLDB_SOURCE_COMMIT}/results/data_curated.csv"
)


@dataclass(frozen=True)
class AqSolDBRecord:
    source_id: str
    smiles: str
    measured_log_s_mol_l: float
    source_inchikey: str | None = None

    def source_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "smiles": self.smiles,
            "measured_log_s_mol_l": self.measured_log_s_mol_l,
            "source_inchikey": self.source_inchikey,
        }


@dataclass(frozen=True)
class AqSolDBParseAudit:
    source_row_count: int
    parsed_record_count: int
    missing_structure_rows: int
    invalid_target_rows: int
    parsed_source_hash: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class ExternalCurationAudit:
    parsed_record_count: int
    invalid_structure_records: int
    overlap_groups_excluded: int
    overlap_records_excluded: int
    conflicting_groups_excluded: int
    conflicting_records_excluded: int
    same_target_duplicate_groups_collapsed: int
    redundant_same_target_records_collapsed: int
    retained_record_count: int
    lineage_hash: str
    retained_dataset_hash: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class ExternalSimilarityBin:
    lower: float
    upper: float
    n: int
    mae: float | None
    rmse: float | None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class ExternalDomainReport:
    similarity_metric: str
    threshold_source: str
    threshold: float
    in_domain_count: int
    out_of_domain_count: int
    in_domain_metrics: RegressionMetrics | None
    out_of_domain_metrics: RegressionMetrics | None
    similarity_bins: tuple[ExternalSimilarityBin, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "similarity_metric": self.similarity_metric,
            "threshold_source": self.threshold_source,
            "threshold": self.threshold,
            "in_domain_count": self.in_domain_count,
            "out_of_domain_count": self.out_of_domain_count,
            "in_domain_metrics": None if self.in_domain_metrics is None else self.in_domain_metrics.to_dict(),
            "out_of_domain_metrics": None if self.out_of_domain_metrics is None else self.out_of_domain_metrics.to_dict(),
            "similarity_bins": [item.to_dict() for item in self.similarity_bins],
        }


@dataclass(frozen=True)
class ExternalValidationReport:
    experiment_id: str
    protocol_version: str
    parent_protocol: str
    parent_seed: int
    parent_esol_dataset_hash: str
    parent_training_count: int
    parent_training_hash: str
    external_dataset_id: str
    external_dataset_url: str
    external_dataset_doi: str
    external_source_commit: str
    external_source_blob_sha: str
    parse_audit: AqSolDBParseAudit
    curation_audit: ExternalCurationAudit
    model: str
    representation: str
    hyperparameters: Mapping[str, Any]
    metrics: RegressionMetrics
    applicability_domain: ExternalDomainReport
    notes: tuple[str, ...]

    def _payload(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "protocol_version": self.protocol_version,
            "parent_protocol": self.parent_protocol,
            "parent_seed": self.parent_seed,
            "parent_esol_dataset_hash": self.parent_esol_dataset_hash,
            "parent_training_count": self.parent_training_count,
            "parent_training_hash": self.parent_training_hash,
            "external_dataset_id": self.external_dataset_id,
            "external_dataset_url": self.external_dataset_url,
            "external_dataset_doi": self.external_dataset_doi,
            "external_source_commit": self.external_source_commit,
            "external_source_blob_sha": self.external_source_blob_sha,
            "parse_audit": self.parse_audit.to_dict(),
            "curation_audit": self.curation_audit.to_dict(),
            "model": self.model,
            "representation": self.representation,
            "hyperparameters": dict(self.hyperparameters),
            "metrics": self.metrics.to_dict(),
            "applicability_domain": self.applicability_domain.to_dict(),
            "notes": list(self.notes),
        }

    @property
    def report_hash(self) -> str:
        return sha256_json(self._payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "report_hash": self.report_hash}


def parse_aqsoldb_csv(text: str) -> tuple[tuple[AqSolDBRecord, ...], AqSolDBParseAudit]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise SolubilityBenchmarkError("AqSolDB dataset is missing a CSV header")
    required = {"ID", "SMILES", "Solubility"}
    missing = required.difference(reader.fieldnames)
    if missing:
        raise SolubilityBenchmarkError(f"AqSolDB is missing required column(s): {sorted(missing)}")

    records: list[AqSolDBRecord] = []
    source_rows = missing_structure = invalid_target = 0
    for row_index, row in enumerate(reader, start=2):
        source_rows += 1
        source_id = str(row.get("ID") or f"row-{row_index}").strip() or f"row-{row_index}"
        smiles = str(row.get("SMILES") or "").strip()
        if not smiles:
            missing_structure += 1
            continue
        raw_target = str(row.get("Solubility") or "").strip()
        try:
            target = float(raw_target)
        except ValueError:
            invalid_target += 1
            continue
        if not math.isfinite(target):
            invalid_target += 1
            continue
        source_inchikey = str(row.get("InChIKey") or "").strip() or None
        records.append(AqSolDBRecord(source_id, smiles, target, source_inchikey))

    if not records:
        raise SolubilityBenchmarkError("AqSolDB contains no usable records")
    parsed_hash = sha256_json([record.source_dict() for record in records])
    return (
        tuple(records),
        AqSolDBParseAudit(
            source_row_count=source_rows,
            parsed_record_count=len(records),
            missing_structure_rows=missing_structure,
            invalid_target_rows=invalid_target,
            parsed_source_hash=parsed_hash,
        ),
    )


def download_aqsoldb(*, url: str = AQSOLDB_URL, timeout: float = 60.0) -> tuple[tuple[AqSolDBRecord, ...], AqSolDBParseAudit]:
    request = Request(url, headers={"User-Agent": "Research-OS/5.0 ONLINE-EXP-002"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - immutable HTTPS source by default
            payload = response.read().decode("utf-8")
    except Exception as exc:
        raise SolubilityBenchmarkError(f"failed to retrieve AqSolDB from {url}") from exc
    return parse_aqsoldb_csv(payload)


def _external_as_solubility(record: AqSolDBRecord) -> SolubilityRecord:
    return SolubilityRecord(record.source_id, record.smiles, record.measured_log_s_mol_l)


def curate_external_records(
    esol_records: Sequence[SolubilityRecord],
    external_records: Sequence[AqSolDBRecord],
) -> tuple[tuple[SolubilityRecord, ...], ExternalCurationAudit]:
    esol_canonical: set[str] = set()
    esol_inchikeys: set[str] = set()
    for record in esol_records:
        canonical, inchikey = canonical_identity(record.smiles)
        esol_canonical.add(canonical)
        esol_inchikeys.add(inchikey)

    groups: dict[str, list[tuple[AqSolDBRecord, str]]] = defaultdict(list)
    invalid_structure = 0
    decisions: list[dict[str, Any]] = []
    for record in external_records:
        try:
            canonical, inchikey = canonical_identity(record.smiles)
        except SolubilityBenchmarkError:
            invalid_structure += 1
            decisions.append({"source_id": record.source_id, "decision": "exclude_invalid_structure"})
            continue
        groups[canonical].append((record, inchikey))

    retained: list[tuple[str, SolubilityRecord]] = []
    overlap_groups = overlap_records = 0
    conflicting_groups = conflicting_records = 0
    duplicate_groups = redundant_duplicates = 0

    for canonical in sorted(groups):
        members = sorted(groups[canonical], key=lambda pair: (pair[0].source_id, pair[0].smiles, pair[0].measured_log_s_mol_l))
        overlap = canonical in esol_canonical or any(inchikey in esol_inchikeys for _, inchikey in members)
        if overlap:
            overlap_groups += 1
            overlap_records += len(members)
            for record, _ in members:
                decisions.append({"canonical": canonical, "source_id": record.source_id, "decision": "exclude_esol_overlap"})
            continue

        target_values = {round(record.measured_log_s_mol_l, 12) for record, _ in members}
        if len(target_values) > 1:
            conflicting_groups += 1
            conflicting_records += len(members)
            for record, _ in members:
                decisions.append({"canonical": canonical, "source_id": record.source_id, "decision": "exclude_conflicting_target"})
            continue

        kept_record, _ = members[0]
        retained.append((canonical, _external_as_solubility(kept_record)))
        decisions.append({"canonical": canonical, "source_id": kept_record.source_id, "decision": "keep"})
        if len(members) > 1:
            duplicate_groups += 1
            redundant_duplicates += len(members) - 1
            for record, _ in members[1:]:
                decisions.append({"canonical": canonical, "source_id": record.source_id, "decision": "collapse_same_target_duplicate"})

    retained.sort(key=lambda pair: (pair[0], pair[1].compound_id))
    retained_records = tuple(record for _, record in retained)
    if not retained_records:
        raise SolubilityBenchmarkError("AqSolDB decontamination removed every usable external record")

    lineage_hash = sha256_json(sorted(decisions, key=lambda item: (str(item.get("canonical", "")), str(item.get("source_id", "")), str(item["decision"]))))
    audit = ExternalCurationAudit(
        parsed_record_count=len(external_records),
        invalid_structure_records=invalid_structure,
        overlap_groups_excluded=overlap_groups,
        overlap_records_excluded=overlap_records,
        conflicting_groups_excluded=conflicting_groups,
        conflicting_records_excluded=conflicting_records,
        same_target_duplicate_groups_collapsed=duplicate_groups,
        redundant_same_target_records_collapsed=redundant_duplicates,
        retained_record_count=len(retained_records),
        lineage_hash=lineage_hash,
        retained_dataset_hash=dataset_hash(retained_records),
    )
    return retained_records, audit


def _combined_features(records: Sequence[SolubilityRecord]):
    try:
        import numpy as np
    except ImportError as exc:
        raise SolubilityBenchmarkError("ONLINE-EXP-002 requires NumPy") from exc
    width = len(descriptor_vector(records[0].smiles)) + MORGAN_BITS
    matrix = np.empty((len(records), width), dtype=float)
    for index, record in enumerate(records):
        row = descriptor_vector(record.smiles) + morgan_vector(record.smiles)
        matrix[index, :] = row
    return matrix


def _subset_metrics(truth: Sequence[float], prediction: Sequence[float], mask: Sequence[bool], wanted: bool) -> RegressionMetrics | None:
    selected_truth = [value for value, flag in zip(truth, mask) if flag is wanted]
    selected_prediction = [value for value, flag in zip(prediction, mask) if flag is wanted]
    return compute_regression_metrics(selected_truth, selected_prediction) if selected_truth else None


def _external_domain(
    train: Sequence[SolubilityRecord],
    external: Sequence[SolubilityRecord],
    truth: Sequence[float],
    prediction: Sequence[float],
) -> ExternalDomainReport:
    train_fingerprints = [_fingerprint(record.smiles) for record in train]
    threshold = _percentile(_training_loo_similarities(train), AD_TRAIN_QUANTILE)
    similarities = tuple(_max_train_similarity(train_fingerprints, _fingerprint(record.smiles)) for record in external)
    in_domain = tuple(value >= threshold for value in similarities)

    bins: list[ExternalSimilarityBin] = []
    for lower, upper in SIMILARITY_BINS:
        indices = [index for index, value in enumerate(similarities) if lower <= value < upper]
        errors = [float(prediction[index]) - float(truth[index]) for index in indices]
        bins.append(
            ExternalSimilarityBin(
                lower=lower,
                upper=min(upper, 1.0),
                n=len(indices),
                mae=statistics.fmean(abs(error) for error in errors) if errors else None,
                rmse=math.sqrt(statistics.fmean(error * error for error in errors)) if errors else None,
            )
        )

    return ExternalDomainReport(
        similarity_metric=f"Morgan radius={MORGAN_RADIUS} bits={MORGAN_BITS} Tanimoto",
        threshold_source=f"parent ESOL training leave-one-out nearest-neighbor similarity percentile {AD_TRAIN_QUANTILE}",
        threshold=threshold,
        in_domain_count=sum(in_domain),
        out_of_domain_count=len(in_domain) - sum(in_domain),
        in_domain_metrics=_subset_metrics(truth, prediction, in_domain, True),
        out_of_domain_metrics=_subset_metrics(truth, prediction, in_domain, False),
        similarity_bins=tuple(bins),
    )


def run_aqsoldb_external_validation(
    esol_records: Sequence[SolubilityRecord],
    external_records: Sequence[AqSolDBRecord],
    parse_audit: AqSolDBParseAudit,
    *,
    expected_parent_train_count: int | None = EXPECTED_PARENT_TRAIN_COUNT,
) -> ExternalValidationReport:
    esol = tuple(esol_records)
    if len(esol) < 20:
        raise SolubilityBenchmarkError("ONLINE-EXP-002 requires the recorded ESOL parent dataset")
    external, curation = curate_external_records(esol, external_records)

    parent_split = hybrid_structural_split(esol, seed=PARENT_SEED)
    train = tuple(parent_split.train)
    if expected_parent_train_count is not None and len(train) != expected_parent_train_count:
        raise SolubilityBenchmarkError(
            f"parent v2 training partition drifted: expected {expected_parent_train_count}, got {len(train)}"
        )

    try:
        from sklearn.ensemble import RandomForestRegressor
    except ImportError as exc:
        raise SolubilityBenchmarkError("ONLINE-EXP-002 requires scikit-learn; install the 'ml' extra") from exc

    hyperparameters = {
        "n_estimators": 300,
        "min_samples_leaf": 2,
        "random_state": PARENT_SEED,
        "n_jobs": 1,
    }
    model = RandomForestRegressor(**hyperparameters)
    x_train = _combined_features(train)
    y_train = [record.measured_log_s_mol_l for record in train]
    model.fit(x_train, y_train)

    x_external = _combined_features(external)
    truth = [record.measured_log_s_mol_l for record in external]
    prediction = [float(value) for value in model.predict(x_external)]
    metrics = compute_regression_metrics(truth, prediction)
    domain = _external_domain(train, external, truth, prediction)

    return ExternalValidationReport(
        experiment_id=EXPERIMENT_ID,
        protocol_version=PROTOCOL_VERSION,
        parent_protocol=PARENT_PROTOCOL,
        parent_seed=PARENT_SEED,
        parent_esol_dataset_hash=dataset_hash(esol),
        parent_training_count=len(train),
        parent_training_hash=dataset_hash(train),
        external_dataset_id=AQSOLDB_ID,
        external_dataset_url=AQSOLDB_URL,
        external_dataset_doi=AQSOLDB_DOI,
        external_source_commit=AQSOLDB_SOURCE_COMMIT,
        external_source_blob_sha=AQSOLDB_SOURCE_BLOB_SHA,
        parse_audit=parse_audit,
        curation_audit=curation,
        model="random_forest_combined",
        representation="descriptors+morgan",
        hyperparameters=hyperparameters,
        metrics=metrics,
        applicability_domain=domain,
        notes=(
            "The external model specification is inherited unchanged from ONLINE-EXP-001 v2.",
            "Only the parent seed-42 hybrid structural training partition is used for fitting; parent validation/test targets are excluded.",
            "Every AqSolDB structure matching any ESOL canonical structure or InChIKey is excluded before inference metrics are computed.",
            "Conflicting external duplicate targets are excluded as complete canonical-structure groups and are never averaged.",
            "AqSolDB targets do not participate in model selection, fitting, decontamination matching, or applicability-domain threshold construction.",
            "AqSolDB aggregates measurements from heterogeneous public sources; this report does not erase source-level experimental differences.",
            "R2 is a regression score, not a confidence or reliability percentage.",
        ),
    )


def run_online_exp_002_from_public_sources() -> ExternalValidationReport:
    esol = download_delaney()
    external, parse_audit = download_aqsoldb()
    return run_aqsoldb_external_validation(esol, external, parse_audit)
