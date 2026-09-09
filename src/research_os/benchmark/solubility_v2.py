"""ONLINE-EXP-001 v2: chemical audit, hybrid structural split and applicability domain."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
import random
import statistics
from typing import Any, Mapping, Sequence

from research_os.core.hashing import sha256_json
from research_os.ml.metrics import RegressionMetrics, compute_regression_metrics
from research_os.ml.schema import DataSplit, SplitStrategy
from research_os.ml.splitters import random_split
from research_os.benchmark.solubility import (
    DATASET_DOI,
    DATASET_ID,
    DATASET_URL,
    DESCRIPTOR_NAMES,
    SolubilityBenchmarkError,
    SolubilityRecord,
    dataset_hash,
    descriptor_vector,
)

EXPERIMENT_ID_V2 = "ONLINE-EXP-001-V2"
PROTOCOL_VERSION_V2 = "research-os.online-exp-001.v2"
MORGAN_RADIUS = 2
MORGAN_BITS = 2048
ACYCLIC_CLUSTER_SIMILARITY = 0.50
AD_TRAIN_QUANTILE = 0.05
SIMILARITY_BINS = ((0.0, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0000001))


@dataclass(frozen=True)
class ChemicalAudit:
    raw_records: int
    valid_records: int
    invalid_records: int
    unique_structures: int
    unique_inchikeys: int
    duplicate_structure_groups: int
    duplicate_records: int
    conflicting_target_groups: int
    multi_fragment_records: int
    charged_records: int
    audit_hash: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class TargetDistribution:
    n: int
    mean: float
    median: float
    stdev: float | None
    minimum: float
    q1: float
    q3: float
    maximum: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class DomainModelSummary:
    model: str
    in_domain_count: int
    out_of_domain_count: int
    in_domain_metrics: RegressionMetrics | None
    out_of_domain_metrics: RegressionMetrics | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "in_domain_count": self.in_domain_count,
            "out_of_domain_count": self.out_of_domain_count,
            "in_domain_metrics": None if self.in_domain_metrics is None else self.in_domain_metrics.to_dict(),
            "out_of_domain_metrics": None if self.out_of_domain_metrics is None else self.out_of_domain_metrics.to_dict(),
        }


@dataclass(frozen=True)
class SimilarityBinSummary:
    lower: float
    upper: float
    n: int
    mae: float | None
    rmse: float | None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class V2ModelEvaluation:
    model: str
    representation: str
    hyperparameters: Mapping[str, Any]
    validation_metrics: RegressionMetrics | None
    test_metrics: RegressionMetrics
    predictions: tuple[float, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "representation": self.representation,
            "hyperparameters": dict(self.hyperparameters),
            "validation_metrics": None if self.validation_metrics is None else self.validation_metrics.to_dict(),
            "test_metrics": self.test_metrics.to_dict(),
        }


@dataclass(frozen=True)
class V2SplitEvaluation:
    strategy: str
    train_count: int
    validation_count: int
    test_count: int
    structural_overlap_count: int | None
    target_distribution: Mapping[str, TargetDistribution]
    models: tuple[V2ModelEvaluation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "train_count": self.train_count,
            "validation_count": self.validation_count,
            "test_count": self.test_count,
            "structural_overlap_count": self.structural_overlap_count,
            "target_distribution": {key: value.to_dict() for key, value in self.target_distribution.items()},
            "models": [model.to_dict() for model in self.models],
        }


@dataclass(frozen=True)
class ApplicabilityDomainReport:
    similarity_metric: str
    threshold_source: str
    threshold: float
    train_leave_one_out_similarity: TargetDistribution
    model_summaries: tuple[DomainModelSummary, ...]
    combined_rf_similarity_bins: tuple[SimilarityBinSummary, ...]
    combined_rf_error_correlations: Mapping[str, float | None]

    def to_dict(self) -> dict[str, Any]:
        return {
            "similarity_metric": self.similarity_metric,
            "threshold_source": self.threshold_source,
            "threshold": self.threshold,
            "train_leave_one_out_similarity": self.train_leave_one_out_similarity.to_dict(),
            "model_summaries": [item.to_dict() for item in self.model_summaries],
            "combined_rf_similarity_bins": [item.to_dict() for item in self.combined_rf_similarity_bins],
            "combined_rf_error_correlations": dict(self.combined_rf_error_correlations),
        }


@dataclass(frozen=True)
class V2Report:
    experiment_id: str
    protocol_version: str
    dataset_id: str
    dataset_url: str
    dataset_doi: str
    dataset_hash: str
    seed: int
    chemical_audit: ChemicalAudit
    split_methodology: Mapping[str, Any]
    splits: tuple[V2SplitEvaluation, ...]
    applicability_domain: ApplicabilityDomainReport
    validation_ablation: Mapping[str, float]
    notes: tuple[str, ...]

    def _payload(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "protocol_version": self.protocol_version,
            "dataset_id": self.dataset_id,
            "dataset_url": self.dataset_url,
            "dataset_doi": self.dataset_doi,
            "dataset_hash": self.dataset_hash,
            "seed": self.seed,
            "chemical_audit": self.chemical_audit.to_dict(),
            "split_methodology": dict(self.split_methodology),
            "splits": [split.to_dict() for split in self.splits],
            "applicability_domain": self.applicability_domain.to_dict(),
            "validation_ablation": dict(self.validation_ablation),
            "notes": list(self.notes),
        }

    @property
    def report_hash(self) -> str:
        return sha256_json(self._payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "report_hash": self.report_hash}


def canonical_identity(smiles: str) -> tuple[str, str]:
    try:
        from rdkit import Chem
        from rdkit.Chem import inchi
    except ImportError as exc:
        raise SolubilityBenchmarkError("chemical identity audit requires RDKit") from exc
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise SolubilityBenchmarkError(f"invalid SMILES during chemical audit: {smiles!r}")
    return Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True), inchi.MolToInchiKey(molecule)


def audit_chemistry(records: Sequence[SolubilityRecord]) -> ChemicalAudit:
    try:
        from rdkit import Chem
    except ImportError as exc:
        raise SolubilityBenchmarkError("chemical audit requires RDKit") from exc
    identities: list[tuple[str, str, float]] = []
    invalid = multi_fragment = charged = 0
    for record in records:
        molecule = Chem.MolFromSmiles(record.smiles)
        if molecule is None:
            invalid += 1
            continue
        canonical, inchikey = canonical_identity(record.smiles)
        identities.append((canonical, inchikey, float(record.measured_log_s_mol_l)))
        multi_fragment += int(len(Chem.GetMolFrags(molecule)) > 1)
        charged += int(any(atom.GetFormalCharge() != 0 for atom in molecule.GetAtoms()))
    groups: dict[str, list[float]] = defaultdict(list)
    for canonical, _, target in identities:
        groups[canonical].append(target)
    duplicate_groups = [values for values in groups.values() if len(values) > 1]
    conflicts = sum(1 for values in duplicate_groups if len({round(value, 12) for value in values}) > 1)
    audit_payload = {
        "raw_records": len(records),
        "valid_records": len(identities),
        "invalid_records": invalid,
        "canonical_target_rows": sorted((canonical, round(target, 12)) for canonical, _, target in identities),
        "multi_fragment_records": multi_fragment,
        "charged_records": charged,
    }
    return ChemicalAudit(
        raw_records=len(records),
        valid_records=len(identities),
        invalid_records=invalid,
        unique_structures=len(groups),
        unique_inchikeys=len({inchikey for _, inchikey, _ in identities}),
        duplicate_structure_groups=len(duplicate_groups),
        duplicate_records=sum(len(values) - 1 for values in duplicate_groups),
        conflicting_target_groups=conflicts,
        multi_fragment_records=multi_fragment,
        charged_records=charged,
        audit_hash=sha256_json(audit_payload),
    )


def _fingerprint(smiles: str):
    try:
        from rdkit import Chem
        from rdkit.Chem import rdFingerprintGenerator
    except ImportError as exc:
        raise SolubilityBenchmarkError("Morgan fingerprint requires RDKit") from exc
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise SolubilityBenchmarkError(f"invalid SMILES during fingerprinting: {smiles!r}")
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=MORGAN_RADIUS, fpSize=MORGAN_BITS)
    return generator.GetFingerprint(molecule)


def morgan_vector(smiles: str) -> tuple[float, ...]:
    return tuple(float(value) for value in _fingerprint(smiles))


def _murcko_or_none(smiles: str) -> str | None:
    try:
        from rdkit import Chem
        from rdkit.Chem.Scaffolds import MurckoScaffold
    except ImportError as exc:
        raise SolubilityBenchmarkError("hybrid structural grouping requires RDKit") from exc
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise SolubilityBenchmarkError(f"invalid SMILES during grouping: {smiles!r}")
    scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=molecule)
    return scaffold or None


def hybrid_group_labels(records: Sequence[SolubilityRecord]) -> tuple[str, ...]:
    """Use Murcko groups for ring systems and Morgan/Butina clusters for acyclic compounds."""
    try:
        from rdkit import DataStructs
        from rdkit.ML.Cluster import Butina
    except ImportError as exc:
        raise SolubilityBenchmarkError("acyclic clustering requires RDKit") from exc
    labels: list[str | None] = [None] * len(records)
    acyclic: list[tuple[str, int, Any]] = []
    for index, record in enumerate(records):
        murcko = _murcko_or_none(record.smiles)
        if murcko is not None:
            labels[index] = f"RING:{murcko}"
        else:
            canonical, _ = canonical_identity(record.smiles)
            acyclic.append((canonical, index, _fingerprint(record.smiles)))
    acyclic.sort(key=lambda item: (item[0], item[1]))
    if acyclic:
        distances: list[float] = []
        fingerprints = [item[2] for item in acyclic]
        for index in range(1, len(fingerprints)):
            similarities = DataStructs.BulkTanimotoSimilarity(fingerprints[index], fingerprints[:index])
            distances.extend(1.0 - float(value) for value in similarities)
        clusters = Butina.ClusterData(
            distances,
            len(fingerprints),
            1.0 - ACYCLIC_CLUSTER_SIMILARITY,
            isDistData=True,
            reordering=True,
        )
        for cluster in clusters:
            members = sorted(acyclic[position][0] for position in cluster)
            label = "ACYCLIC:" + sha256_json(members)[:16]
            for position in cluster:
                labels[acyclic[position][1]] = label
    if any(label is None for label in labels):
        raise SolubilityBenchmarkError("hybrid structural grouping left an unlabeled molecule")
    return tuple(str(label) for label in labels)


def hybrid_structural_split(
    records: Sequence[SolubilityRecord],
    *,
    validation_size: float = 0.1,
    test_size: float = 0.1,
    seed: int = 42,
) -> DataSplit[SolubilityRecord]:
    if validation_size < 0 or test_size < 0 or validation_size + test_size >= 1:
        raise SolubilityBenchmarkError("validation/test fractions must be non-negative and sum below one")
    labels = hybrid_group_labels(records)
    grouped: dict[str, list[SolubilityRecord]] = defaultdict(list)
    for record, label in zip(records, labels):
        grouped[label].append(record)
    buckets = list(grouped.items())
    random.Random(seed).shuffle(buckets)
    buckets.sort(key=lambda pair: len(pair[1]), reverse=True)
    targets = {
        "train": (1.0 - validation_size - test_size) * len(records),
        "validation": validation_size * len(records),
        "test": test_size * len(records),
    }
    partitions: dict[str, list[SolubilityRecord]] = {"train": [], "validation": [], "test": []}
    for _, bucket in buckets:
        choices = sorted(
            partitions,
            key=lambda name: (len(partitions[name]) - targets[name]) / max(targets[name], 1.0),
        )
        partitions[choices[0]].extend(bucket)
    if not partitions["train"] or not partitions["test"]:
        raise SolubilityBenchmarkError("hybrid structural split produced an empty train or test partition")
    return DataSplit(
        SplitStrategy.SCAFFOLD,
        tuple(partitions["train"]),
        tuple(partitions["validation"]),
        tuple(partitions["test"]),
        seed=seed,
        metadata={
            "group_count": len(grouped),
            "grouping": "murcko_for_ring_systems_plus_butina_morgan_for_acyclic",
            "acyclic_cluster_similarity": ACYCLIC_CLUSTER_SIMILARITY,
        },
    )


def structural_overlap_count(split: DataSplit[SolubilityRecord]) -> int:
    values = tuple(split.train) + tuple(split.validation) + tuple(split.test)
    labels = hybrid_group_labels(values)
    train_end = len(split.train)
    validation_end = train_end + len(split.validation)
    groups = (
        set(labels[:train_end]),
        set(labels[train_end:validation_end]),
        set(labels[validation_end:]),
    )
    return len((groups[0] & groups[1]) | (groups[0] & groups[2]) | (groups[1] & groups[2]))


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise SolubilityBenchmarkError("percentile requires at least one value")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    fraction = position - low
    return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def describe(values: Sequence[float]) -> TargetDistribution:
    data = [float(value) for value in values]
    if not data:
        raise SolubilityBenchmarkError("distribution summary requires values")
    return TargetDistribution(
        n=len(data),
        mean=statistics.fmean(data),
        median=statistics.median(data),
        stdev=statistics.stdev(data) if len(data) > 1 else None,
        minimum=min(data),
        q1=_percentile(data, 0.25),
        q3=_percentile(data, 0.75),
        maximum=max(data),
    )


def _features(records: Sequence[SolubilityRecord], representation: str) -> list[tuple[float, ...]]:
    if representation == "descriptors":
        return [descriptor_vector(record.smiles) for record in records]
    if representation == "morgan":
        return [morgan_vector(record.smiles) for record in records]
    if representation == "descriptors+morgan":
        return [descriptor_vector(record.smiles) + morgan_vector(record.smiles) for record in records]
    raise SolubilityBenchmarkError(f"unsupported representation: {representation}")


def delaney_original_prediction(smiles: str) -> float:
    """Evaluate the fixed coefficients reported for the original Delaney ESOL model."""
    try:
        from rdkit import Chem
        from rdkit.Chem import Crippen, Descriptors, Lipinski
    except ImportError as exc:
        raise SolubilityBenchmarkError("Delaney baseline requires RDKit") from exc
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise SolubilityBenchmarkError(f"invalid SMILES for Delaney baseline: {smiles!r}")
    heavy_atoms = molecule.GetNumHeavyAtoms()
    aromatic_atoms = sum(1 for atom in molecule.GetAtoms() if atom.GetIsAromatic())
    aromatic_proportion = aromatic_atoms / heavy_atoms if heavy_atoms else 0.0
    return (
        0.16
        - 0.63 * Crippen.MolLogP(molecule)
        - 0.0062 * Descriptors.MolWt(molecule)
        + 0.066 * Lipinski.NumRotatableBonds(molecule)
        - 0.74 * aromatic_proportion
    )


def _fit_predict(
    split: DataSplit[SolubilityRecord], model_name: str, representation: str, seed: int
) -> V2ModelEvaluation:
    y_train = [record.measured_log_s_mol_l for record in split.train]
    y_validation = [record.measured_log_s_mol_l for record in split.validation]
    y_test = [record.measured_log_s_mol_l for record in split.test]
    if model_name == "delaney_original":
        validation_prediction = [delaney_original_prediction(record.smiles) for record in split.validation]
        test_prediction = [delaney_original_prediction(record.smiles) for record in split.test]
        return V2ModelEvaluation(
            model_name,
            "delaney_4_descriptor_formula",
            {"intercept": 0.16, "logp": -0.63, "mw": -0.0062, "rotors": 0.066, "aromatic_proportion": -0.74},
            compute_regression_metrics(y_validation, validation_prediction) if y_validation else None,
            compute_regression_metrics(y_test, test_prediction),
            tuple(float(value) for value in test_prediction),
        )
    if model_name == "mean_baseline":
        mean = statistics.fmean(y_train)
        validation_prediction = [mean] * len(y_validation)
        test_prediction = [mean] * len(y_test)
        return V2ModelEvaluation(
            model_name,
            "target_only",
            {"strategy": "training_target_mean"},
            compute_regression_metrics(y_validation, validation_prediction) if y_validation else None,
            compute_regression_metrics(y_test, test_prediction),
            tuple(test_prediction),
        )
    try:
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise SolubilityBenchmarkError("v2 learned models require scikit-learn") from exc
    x_train = _features(split.train, representation)
    x_validation = _features(split.validation, representation)
    x_test = _features(split.test, representation)
    if model_name == "ridge":
        model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
        parameters = {"alpha": 1.0, "standardize": True}
    elif model_name.startswith("random_forest"):
        parameters = {"n_estimators": 300, "min_samples_leaf": 2, "random_state": seed, "n_jobs": 1}
        model = RandomForestRegressor(**parameters)
    else:
        raise SolubilityBenchmarkError(f"unsupported v2 model: {model_name}")
    model.fit(x_train, y_train)
    validation_prediction = model.predict(x_validation) if x_validation else []
    test_prediction = model.predict(x_test)
    return V2ModelEvaluation(
        model_name,
        representation,
        parameters,
        compute_regression_metrics(y_validation, validation_prediction) if y_validation else None,
        compute_regression_metrics(y_test, test_prediction),
        tuple(float(value) for value in test_prediction),
    )


def _evaluate_split(strategy: str, split: DataSplit[SolubilityRecord], seed: int) -> V2SplitEvaluation:
    overlap = structural_overlap_count(split) if strategy == "hybrid_structural" else None
    if overlap:
        raise SolubilityBenchmarkError(f"structural group leakage detected: {overlap}")
    specifications = (
        ("mean_baseline", "target_only"),
        ("delaney_original", "delaney_4_descriptor_formula"),
        ("ridge", "descriptors"),
        ("random_forest_descriptors", "descriptors"),
        ("random_forest_morgan", "morgan"),
        ("random_forest_combined", "descriptors+morgan"),
    )
    models = tuple(_fit_predict(split, name, representation, seed) for name, representation in specifications)
    return V2SplitEvaluation(
        strategy=strategy,
        train_count=len(split.train),
        validation_count=len(split.validation),
        test_count=len(split.test),
        structural_overlap_count=overlap,
        target_distribution={
            "train": describe([record.measured_log_s_mol_l for record in split.train]),
            "validation": describe([record.measured_log_s_mol_l for record in split.validation]),
            "test": describe([record.measured_log_s_mol_l for record in split.test]),
        },
        models=models,
    )


def _max_train_similarity(train_fingerprints, query_fingerprint) -> float:
    try:
        from rdkit import DataStructs
    except ImportError as exc:
        raise SolubilityBenchmarkError("applicability domain requires RDKit") from exc
    if not train_fingerprints:
        raise SolubilityBenchmarkError("applicability domain requires training fingerprints")
    return max(float(value) for value in DataStructs.BulkTanimotoSimilarity(query_fingerprint, train_fingerprints))


def _training_loo_similarities(train: Sequence[SolubilityRecord]) -> tuple[float, ...]:
    try:
        from rdkit import DataStructs
    except ImportError as exc:
        raise SolubilityBenchmarkError("applicability domain requires RDKit") from exc
    fingerprints = [_fingerprint(record.smiles) for record in train]
    if len(fingerprints) < 2:
        raise SolubilityBenchmarkError("applicability domain requires at least two training structures")
    similarities = []
    for index, fingerprint in enumerate(fingerprints):
        peers = fingerprints[:index] + fingerprints[index + 1 :]
        similarities.append(max(float(value) for value in DataStructs.BulkTanimotoSimilarity(fingerprint, peers)))
    return tuple(similarities)


def _subset_metrics(
    truth: Sequence[float], predictions: Sequence[float], mask: Sequence[bool], wanted: bool
) -> RegressionMetrics | None:
    selected_truth = [value for value, flag in zip(truth, mask) if flag is wanted]
    selected_predictions = [value for value, flag in zip(predictions, mask) if flag is wanted]
    return compute_regression_metrics(selected_truth, selected_predictions) if selected_truth else None


def _pearson(x_values: Sequence[float], y_values: Sequence[float]) -> float | None:
    if len(x_values) != len(y_values) or len(x_values) < 2:
        return None
    x_mean = statistics.fmean(x_values)
    y_mean = statistics.fmean(y_values)
    x_delta = [value - x_mean for value in x_values]
    y_delta = [value - y_mean for value in y_values]
    denominator = math.sqrt(sum(value * value for value in x_delta) * sum(value * value for value in y_delta))
    if denominator == 0:
        return None
    return sum(x_value * y_value for x_value, y_value in zip(x_delta, y_delta)) / denominator


def _applicability(
    split: DataSplit[SolubilityRecord], evaluation: V2SplitEvaluation
) -> ApplicabilityDomainReport:
    train_fingerprints = [_fingerprint(record.smiles) for record in split.train]
    leave_one_out = _training_loo_similarities(split.train)
    threshold = _percentile(leave_one_out, AD_TRAIN_QUANTILE)
    test_similarity = tuple(
        _max_train_similarity(train_fingerprints, _fingerprint(record.smiles)) for record in split.test
    )
    in_domain = tuple(value >= threshold for value in test_similarity)
    truth = [record.measured_log_s_mol_l for record in split.test]
    summaries = tuple(
        DomainModelSummary(
            model=model.model,
            in_domain_count=sum(in_domain),
            out_of_domain_count=len(in_domain) - sum(in_domain),
            in_domain_metrics=_subset_metrics(truth, model.predictions, in_domain, True),
            out_of_domain_metrics=_subset_metrics(truth, model.predictions, in_domain, False),
        )
        for model in evaluation.models
    )
    combined = next(model for model in evaluation.models if model.model == "random_forest_combined")
    bins = []
    for lower, upper in SIMILARITY_BINS:
        indices = [index for index, value in enumerate(test_similarity) if lower <= value < upper]
        errors = [combined.predictions[index] - truth[index] for index in indices]
        bins.append(
            SimilarityBinSummary(
                lower=lower,
                upper=min(upper, 1.0),
                n=len(indices),
                mae=statistics.fmean(abs(error) for error in errors) if errors else None,
                rmse=math.sqrt(statistics.fmean(error * error for error in errors)) if errors else None,
            )
        )
    absolute_error = [abs(prediction - target) for prediction, target in zip(combined.predictions, truth)]
    descriptors = [descriptor_vector(record.smiles) for record in split.test]
    correlations = {
        "similarity": _pearson(list(test_similarity), absolute_error),
        "mol_wt": _pearson([values[0] for values in descriptors], absolute_error),
        "mol_log_p": _pearson([values[1] for values in descriptors], absolute_error),
        "tpsa": _pearson([values[2] for values in descriptors], absolute_error),
    }
    return ApplicabilityDomainReport(
        similarity_metric=f"Morgan radius={MORGAN_RADIUS} bits={MORGAN_BITS} Tanimoto",
        threshold_source=f"training leave-one-out nearest-neighbor similarity percentile {AD_TRAIN_QUANTILE}",
        threshold=threshold,
        train_leave_one_out_similarity=describe(leave_one_out),
        model_summaries=summaries,
        combined_rf_similarity_bins=tuple(bins),
        combined_rf_error_correlations=correlations,
    )


def _validation_ablation(split: DataSplit[SolubilityRecord], seed: int) -> dict[str, float]:
    """Leave-one-descriptor-out Random Forest analysis on validation only."""
    try:
        from sklearn.ensemble import RandomForestRegressor
    except ImportError as exc:
        raise SolubilityBenchmarkError("descriptor ablation requires scikit-learn") from exc
    x_train = [descriptor_vector(record.smiles) for record in split.train]
    y_train = [record.measured_log_s_mol_l for record in split.train]
    x_validation = [descriptor_vector(record.smiles) for record in split.validation]
    y_validation = [record.measured_log_s_mol_l for record in split.validation]
    if not x_validation:
        return {}
    parameters = {"n_estimators": 300, "min_samples_leaf": 2, "random_state": seed, "n_jobs": 1}
    baseline = RandomForestRegressor(**parameters).fit(x_train, y_train)
    result = {"all_descriptors": compute_regression_metrics(y_validation, baseline.predict(x_validation)).rmse}
    for index, name in enumerate(DESCRIPTOR_NAMES):
        train_reduced = [tuple(value for column, value in enumerate(row) if column != index) for row in x_train]
        validation_reduced = [tuple(value for column, value in enumerate(row) if column != index) for row in x_validation]
        model = RandomForestRegressor(**parameters).fit(train_reduced, y_train)
        result[f"without_{name}"] = compute_regression_metrics(y_validation, model.predict(validation_reduced)).rmse
    return result


def run_solubility_benchmark_v2(records: Sequence[SolubilityRecord], *, seed: int = 42) -> V2Report:
    """Execute the frozen v2 protocol without selecting models or features from test performance."""
    values = tuple(records)
    if len(values) < 20:
        raise SolubilityBenchmarkError("ONLINE-EXP-001 v2 requires at least 20 records")
    audit = audit_chemistry(values)
    if audit.invalid_records:
        raise SolubilityBenchmarkError(f"chemical audit found {audit.invalid_records} invalid structure(s)")
    random_partition = random_split(values, validation_size=0.1, test_size=0.1, seed=seed)
    structural_partition = hybrid_structural_split(values, validation_size=0.1, test_size=0.1, seed=seed)
    random_evaluation = _evaluate_split("random", random_partition, seed)
    structural_evaluation = _evaluate_split("hybrid_structural", structural_partition, seed)
    return V2Report(
        experiment_id=EXPERIMENT_ID_V2,
        protocol_version=PROTOCOL_VERSION_V2,
        dataset_id=DATASET_ID,
        dataset_url=DATASET_URL,
        dataset_doi=DATASET_DOI,
        dataset_hash=dataset_hash(values),
        seed=seed,
        chemical_audit=audit,
        split_methodology={
            "random": "80/10/10 seeded random",
            "hybrid_structural": "Murcko groups for ring systems; Morgan/Butina groups for acyclic compounds; whole-group allocation",
            "acyclic_cluster_similarity": ACYCLIC_CLUSTER_SIMILARITY,
        },
        splits=(random_evaluation, structural_evaluation),
        applicability_domain=_applicability(structural_partition, structural_evaluation),
        validation_ablation=_validation_ablation(structural_partition, seed),
        notes=(
            "The v1 report remains immutable; v2 is a new predeclared protocol.",
            "No hyperparameter is tuned against v2 test metrics.",
            "The Delaney original formula is evaluated as a fixed published baseline, not refitted.",
            "Applicability-domain threshold is derived from training structures only and uses no test targets.",
            "Descriptor ablation is reported on validation only and does not alter the tested model specification.",
            "Error correlations are descriptive associations and do not establish causality.",
        ),
    )
