"""ONLINE-EXP-001: auditable aqueous-solubility benchmark.

The benchmark deliberately separates easy random-split performance from
scaffold-held-out performance. It does not claim experimental validation,
chemical equivalence, or reliability percentages from regression scores.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import csv
import io
import json
import math
from pathlib import Path
import random
from typing import Any, Iterable, Mapping, Sequence
from urllib.request import Request, urlopen

from research_os.core.hashing import sha256_json
from research_os.ml.metrics import RegressionMetrics, compute_regression_metrics
from research_os.ml.schema import DataSplit, SplitStrategy
from research_os.ml.splitters import random_split


EXPERIMENT_ID = "ONLINE-EXP-001"
DATASET_ID = "Delaney-ESOL"
DATASET_URL = "https://deepchemdata.s3-us-west-1.amazonaws.com/datasets/delaney-processed.csv"
DATASET_DOI = "10.1021/ci034243x"
PROTOCOL_VERSION = "research-os.online-exp-001.v1"
DESCRIPTOR_NAMES = (
    "mol_wt",
    "mol_log_p",
    "tpsa",
    "h_bond_donors",
    "h_bond_acceptors",
    "rotatable_bonds",
    "fraction_csp3",
    "aromatic_heavy_atom_fraction",
)


class SolubilityBenchmarkError(RuntimeError):
    """Fail-closed error for invalid benchmark inputs or unavailable capabilities."""


@dataclass(frozen=True)
class SolubilityRecord:
    compound_id: str
    smiles: str
    measured_log_s_mol_l: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "compound_id": self.compound_id,
            "smiles": self.smiles,
            "measured_log_s_mol_l": self.measured_log_s_mol_l,
        }


@dataclass(frozen=True)
class ModelEvaluation:
    model: str
    hyperparameters: Mapping[str, Any]
    train_count: int
    validation_count: int
    test_count: int
    validation_metrics: RegressionMetrics | None
    test_metrics: RegressionMetrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "hyperparameters": dict(self.hyperparameters),
            "train_count": self.train_count,
            "validation_count": self.validation_count,
            "test_count": self.test_count,
            "validation_metrics": None if self.validation_metrics is None else self.validation_metrics.to_dict(),
            "test_metrics": self.test_metrics.to_dict(),
        }


@dataclass(frozen=True)
class SplitEvaluation:
    strategy: str
    scaffold_overlap_count: int | None
    models: tuple[ModelEvaluation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "scaffold_overlap_count": self.scaffold_overlap_count,
            "models": [model.to_dict() for model in self.models],
        }


@dataclass(frozen=True)
class SolubilityBenchmarkReport:
    experiment_id: str
    protocol_version: str
    dataset_id: str
    dataset_url: str
    dataset_doi: str
    dataset_hash: str
    record_count: int
    descriptor_names: tuple[str, ...]
    seed: int
    splits: tuple[SplitEvaluation, ...]
    generalization_gap_rmse: Mapping[str, float]
    notes: tuple[str, ...]

    @property
    def report_hash(self) -> str:
        return sha256_json(self._payload())

    def _payload(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "protocol_version": self.protocol_version,
            "dataset_id": self.dataset_id,
            "dataset_url": self.dataset_url,
            "dataset_doi": self.dataset_doi,
            "dataset_hash": self.dataset_hash,
            "record_count": self.record_count,
            "descriptor_names": list(self.descriptor_names),
            "seed": self.seed,
            "splits": [split.to_dict() for split in self.splits],
            "generalization_gap_rmse": dict(self.generalization_gap_rmse),
            "notes": list(self.notes),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "report_hash": self.report_hash}

    def write(self, path: str | Path) -> str:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return str(target)


def _first(row: Mapping[str, str], names: Sequence[str]) -> str | None:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return None


def parse_delaney_csv(text: str) -> tuple[SolubilityRecord, ...]:
    """Parse the Delaney/ESOL CSV without depending on pandas or DeepChem."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise SolubilityBenchmarkError("Delaney dataset is missing a CSV header")
    records: list[SolubilityRecord] = []
    for index, row in enumerate(reader, start=2):
        compound_id = _first(row, ("Compound ID", "compound_id", "name")) or f"row-{index}"
        smiles = _first(row, ("smiles", "SMILES"))
        target = _first(
            row,
            (
                "measured log solubility in mols per litre",
                "measured log(solubility:mol/L)",
                "measured log solubility in mol/L",
            ),
        )
        if smiles is None or target is None:
            raise SolubilityBenchmarkError(f"Delaney row {index} is missing SMILES or measured logS")
        try:
            measured = float(target)
        except ValueError as exc:
            raise SolubilityBenchmarkError(f"Delaney row {index} has non-numeric measured logS") from exc
        if not math.isfinite(measured):
            raise SolubilityBenchmarkError(f"Delaney row {index} has non-finite measured logS")
        records.append(SolubilityRecord(compound_id, smiles, measured))
    if not records:
        raise SolubilityBenchmarkError("Delaney dataset contains no records")
    return tuple(records)


def download_delaney(*, url: str = DATASET_URL, timeout: float = 30.0) -> tuple[SolubilityRecord, ...]:
    request = Request(url, headers={"User-Agent": "Research-OS/5.0 ONLINE-EXP-001"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS source by default
            payload = response.read().decode("utf-8")
    except Exception as exc:  # network failures are evidence failures, not silent fallbacks
        raise SolubilityBenchmarkError(f"failed to retrieve Delaney dataset from {url}") from exc
    return parse_delaney_csv(payload)


def dataset_hash(records: Sequence[SolubilityRecord]) -> str:
    return sha256_json([record.to_dict() for record in records])


def descriptor_vector(smiles: str) -> tuple[float, ...]:
    try:
        from rdkit import Chem
        from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors
    except ImportError as exc:
        raise SolubilityBenchmarkError("ONLINE-EXP-001 requires RDKit") from exc

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise SolubilityBenchmarkError(f"invalid SMILES in solubility dataset: {smiles!r}")
    heavy_atoms = molecule.GetNumHeavyAtoms()
    aromatic_atoms = sum(1 for atom in molecule.GetAtoms() if atom.GetIsAromatic())
    aromatic_fraction = aromatic_atoms / heavy_atoms if heavy_atoms else 0.0
    values = (
        Descriptors.MolWt(molecule),
        Crippen.MolLogP(molecule),
        rdMolDescriptors.CalcTPSA(molecule),
        float(Lipinski.NumHDonors(molecule)),
        float(Lipinski.NumHAcceptors(molecule)),
        float(Lipinski.NumRotatableBonds(molecule)),
        rdMolDescriptors.CalcFractionCSP3(molecule),
        aromatic_fraction,
    )
    if any(not math.isfinite(float(value)) for value in values):
        raise SolubilityBenchmarkError(f"non-finite descriptor produced for SMILES: {smiles!r}")
    return tuple(float(value) for value in values)


def _xy(records: Iterable[SolubilityRecord]) -> tuple[list[tuple[float, ...]], list[float]]:
    values = list(records)
    return (
        [descriptor_vector(record.smiles) for record in values],
        [record.measured_log_s_mol_l for record in values],
    )


class _MeanRegressor:
    def __init__(self) -> None:
        self.mean_: float | None = None

    def fit(self, _x: Sequence[Sequence[float]], y: Sequence[float]) -> "_MeanRegressor":
        if not y:
            raise SolubilityBenchmarkError("mean baseline requires training targets")
        self.mean_ = sum(float(value) for value in y) / len(y)
        return self

    def predict(self, x: Sequence[Sequence[float]]) -> list[float]:
        if self.mean_ is None:
            raise SolubilityBenchmarkError("mean baseline was not fitted")
        return [self.mean_] * len(x)


def _model(name: str, *, seed: int) -> tuple[Any, dict[str, Any]]:
    if name == "mean_baseline":
        return _MeanRegressor(), {"strategy": "training_target_mean"}
    try:
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise SolubilityBenchmarkError("Ridge and Random Forest require scikit-learn; install the 'ml' extra") from exc

    if name == "ridge":
        params = {"alpha": 1.0, "standardize": True}
        return make_pipeline(StandardScaler(), Ridge(alpha=1.0)), params
    if name == "random_forest":
        params = {"n_estimators": 300, "min_samples_leaf": 2, "random_state": seed, "n_jobs": 1}
        return RandomForestRegressor(**params), params
    raise SolubilityBenchmarkError(f"unsupported solubility benchmark model: {name}")


def _evaluate(split: DataSplit[SolubilityRecord], *, model_name: str, seed: int) -> ModelEvaluation:
    if not split.train or not split.test:
        raise SolubilityBenchmarkError(f"{split.strategy.value} produced an empty train or test partition")
    x_train, y_train = _xy(split.train)
    x_validation, y_validation = _xy(split.validation)
    x_test, y_test = _xy(split.test)
    model, hyperparameters = _model(model_name, seed=seed)
    model.fit(x_train, y_train)
    validation_metrics = None
    if x_validation:
        validation_metrics = compute_regression_metrics(y_validation, model.predict(x_validation))
    test_metrics = compute_regression_metrics(y_test, model.predict(x_test))
    return ModelEvaluation(
        model=model_name,
        hyperparameters=hyperparameters,
        train_count=len(split.train),
        validation_count=len(split.validation),
        test_count=len(split.test),
        validation_metrics=validation_metrics,
        test_metrics=test_metrics,
    )


def _murcko(smiles: str) -> str:
    try:
        from rdkit import Chem
        from rdkit.Chem.Scaffolds import MurckoScaffold
    except ImportError as exc:
        raise SolubilityBenchmarkError("scaffold audit requires RDKit") from exc
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise SolubilityBenchmarkError(f"invalid SMILES during scaffold audit: {smiles!r}")
    return MurckoScaffold.MurckoScaffoldSmiles(mol=molecule) or "ACYCLIC"


def balanced_scaffold_split(
    records: Sequence[SolubilityRecord],
    *,
    validation_size: float = 0.1,
    test_size: float = 0.1,
    seed: int = 42,
) -> DataSplit[SolubilityRecord]:
    """Greedy size-balanced Murcko split with strict scaffold isolation.

    Large scaffold groups are assigned first. This avoids allowing a single
    large group (notably the acyclic bucket) to consume the test partition and
    makes random/scaffold comparisons use materially comparable sample counts.
    """
    if not 0 <= validation_size < 1 or not 0 <= test_size < 1 or validation_size + test_size >= 1:
        raise SolubilityBenchmarkError("validation_size and test_size must be non-negative and sum below one")
    values = tuple(records)
    groups: dict[str, list[SolubilityRecord]] = defaultdict(list)
    for record in values:
        groups[_murcko(record.smiles)].append(record)

    buckets = list(groups.values())
    random.Random(seed).shuffle(buckets)
    buckets.sort(key=len, reverse=True)  # stable sort preserves seeded tie order

    train_cutoff = (1.0 - validation_size - test_size) * len(values)
    validation_cutoff = (1.0 - test_size) * len(values)
    train: list[SolubilityRecord] = []
    validation: list[SolubilityRecord] = []
    test: list[SolubilityRecord] = []
    for bucket in buckets:
        if len(train) + len(bucket) <= train_cutoff:
            train.extend(bucket)
        elif len(train) + len(validation) + len(bucket) <= validation_cutoff:
            validation.extend(bucket)
        else:
            test.extend(bucket)

    if not train or not test:
        raise SolubilityBenchmarkError("balanced scaffold split produced an empty train or test partition")
    return DataSplit(
        SplitStrategy.SCAFFOLD,
        tuple(train),
        tuple(validation),
        tuple(test),
        seed=seed,
        metadata={
            "group_count": len(groups),
            "allocation": "descending_group_size_greedy",
            "target_fractions": {
                "train": 1.0 - validation_size - test_size,
                "validation": validation_size,
                "test": test_size,
            },
        },
    )


def scaffold_overlap_count(split: DataSplit[SolubilityRecord]) -> int:
    groups = [
        {_murcko(record.smiles) for record in split.train},
        {_murcko(record.smiles) for record in split.validation},
        {_murcko(record.smiles) for record in split.test},
    ]
    return len((groups[0] & groups[1]) | (groups[0] & groups[2]) | (groups[1] & groups[2]))


def run_solubility_benchmark(
    records: Sequence[SolubilityRecord],
    *,
    seed: int = 42,
    validation_size: float = 0.1,
    test_size: float = 0.1,
) -> SolubilityBenchmarkReport:
    """Run fixed, non-tuned baselines on comparable random/scaffold splits."""
    values = tuple(records)
    if len(values) < 20:
        raise SolubilityBenchmarkError("ONLINE-EXP-001 requires at least 20 records")

    split_pairs = (
        ("random", random_split(values, validation_size=validation_size, test_size=test_size, seed=seed)),
        ("scaffold", balanced_scaffold_split(values, validation_size=validation_size, test_size=test_size, seed=seed)),
    )
    evaluations: list[SplitEvaluation] = []
    for strategy, split in split_pairs:
        overlap = scaffold_overlap_count(split) if strategy == "scaffold" else None
        if overlap:
            raise SolubilityBenchmarkError(f"scaffold leakage detected across partitions: {overlap} scaffold(s)")
        models = tuple(
            _evaluate(split, model_name=name, seed=seed)
            for name in ("mean_baseline", "ridge", "random_forest")
        )
        evaluations.append(SplitEvaluation(strategy, overlap, models))

    by_split = {item.strategy: {model.model: model for model in item.models} for item in evaluations}
    gaps = {
        model: by_split["scaffold"][model].test_metrics.rmse - by_split["random"][model].test_metrics.rmse
        for model in ("mean_baseline", "ridge", "random_forest")
    }
    return SolubilityBenchmarkReport(
        experiment_id=EXPERIMENT_ID,
        protocol_version=PROTOCOL_VERSION,
        dataset_id=DATASET_ID,
        dataset_url=DATASET_URL,
        dataset_doi=DATASET_DOI,
        dataset_hash=dataset_hash(values),
        record_count=len(values),
        descriptor_names=DESCRIPTOR_NAMES,
        seed=seed,
        splits=tuple(evaluations),
        generalization_gap_rmse=gaps,
        notes=(
            "Measured logS is the target; no ESOL-predicted target column is used.",
            "Hyperparameters are fixed before evaluation; validation is reported but not used for tuning.",
            "Random and scaffold protocols target the same 80/10/10 train/validation/test fractions.",
            "Scaffold groups are allocated largest-first and never split across partitions.",
            "R2 is a regression score, not a reliability or confidence percentage.",
            "A larger scaffold-vs-random RMSE gap is evidence of weaker cross-scaffold generalization, not proof of causality.",
        ),
    )
