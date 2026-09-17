"""Frozen ESOL solubility capability reused by Molecular Discovery.

This module is a product-facing extraction of the accepted ONLINE-EXP-001/002
science. It intentionally does not expose the historical benchmark campaign as
new Research OS infrastructure.

The default predictor reconstructs the frozen seed-42 model from the recorded
Delaney/ESOL source, verifies the accepted dataset/training identities, and
reports the inherited applicability-domain result for each prediction.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import csv
import io
import math
from pathlib import Path
import random
from typing import Any, Sequence
from urllib.request import Request, urlopen

from research_os.core.hashing import sha256_json


PROTOCOL_ID = "research-os.molecular-discovery.solubility.esol-v2.v1"
PARENT_PROTOCOL_ID = "research-os.online-exp-001.v2"
MODEL_NAME = "random_forest_combined"
DATASET_ID = "Delaney-ESOL"
DATASET_DOI = "10.1021/ci034243x"
DATASET_URL = "https://deepchemdata.s3-us-west-1.amazonaws.com/datasets/delaney-processed.csv"
EXPECTED_DATASET_HASH = "6de39771743dc4f15b191cffc27e1e02eb474457cc841afda565f31aff198e85"
EXPECTED_TRAINING_HASH = "300ddc4981e1a9c2fb3735e598bcca89fb98a1cd4722cd58454e5d923781f00b"
EXPECTED_TRAINING_COUNT = 902
PARENT_SEED = 42
MORGAN_RADIUS = 2
MORGAN_BITS = 2048
ACYCLIC_CLUSTER_SIMILARITY = 0.50
AD_TRAIN_QUANTILE = 0.05
HYPERPARAMETERS = {
    "n_estimators": 300,
    "min_samples_leaf": 2,
    "random_state": PARENT_SEED,
    "n_jobs": 1,
}
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


class SolubilityCapabilityError(RuntimeError):
    """Raised when the frozen solubility capability cannot be reconstructed safely."""


@dataclass(frozen=True)
class SolubilityRecord:
    compound_id: str
    smiles: str
    measured_log_s_mol_l: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SolubilityPrediction:
    smiles: str
    predicted_log_s_mol_l: float
    max_training_tanimoto: float
    applicability_threshold: float
    in_domain: bool
    evidence_level: str = "E1_ML"
    model_name: str = MODEL_NAME
    protocol_id: str = PROTOCOL_ID

    @property
    def domain_status(self) -> str:
        return "IN_DOMAIN" if self.in_domain else "OUT_OF_DOMAIN"

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "domain_status": self.domain_status,
        }


def _first(row: dict[str, str], names: Sequence[str]) -> str | None:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def parse_esol_csv(text: str) -> tuple[SolubilityRecord, ...]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise SolubilityCapabilityError("Delaney/ESOL CSV is missing a header")
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
            raise SolubilityCapabilityError(f"Delaney row {index} is missing SMILES or measured logS")
        try:
            measured = float(target)
        except ValueError as exc:
            raise SolubilityCapabilityError(f"Delaney row {index} has non-numeric measured logS") from exc
        if not math.isfinite(measured):
            raise SolubilityCapabilityError(f"Delaney row {index} has non-finite measured logS")
        records.append(SolubilityRecord(compound_id, smiles, measured))
    if not records:
        raise SolubilityCapabilityError("Delaney/ESOL contains no records")
    return tuple(records)


def dataset_hash(records: Sequence[SolubilityRecord]) -> str:
    return sha256_json([record.to_dict() for record in records])


def _rdkit():
    try:
        from rdkit import Chem, DataStructs
        from rdkit.Chem import Crippen, Descriptors, Lipinski, rdFingerprintGenerator, rdMolDescriptors
        from rdkit.Chem.Scaffolds import MurckoScaffold
        from rdkit.ML.Cluster import Butina
    except ImportError as exc:
        raise SolubilityCapabilityError("solubility prediction requires RDKit; install the 'discovery' extra") from exc
    return Chem, DataStructs, Crippen, Descriptors, Lipinski, rdFingerprintGenerator, rdMolDescriptors, MurckoScaffold, Butina


def _molecule(smiles: str):
    Chem, *_ = _rdkit()
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise SolubilityCapabilityError(f"invalid or unsanitizable SMILES: {smiles!r}")
    return molecule


def descriptor_vector(smiles: str) -> tuple[float, ...]:
    Chem, _, Crippen, Descriptors, Lipinski, _, rdMolDescriptors, _, _ = _rdkit()
    molecule = _molecule(smiles)
    heavy_atoms = molecule.GetNumHeavyAtoms()
    aromatic_atoms = sum(1 for atom in molecule.GetAtoms() if atom.GetIsAromatic())
    values = (
        Descriptors.MolWt(molecule),
        Crippen.MolLogP(molecule),
        rdMolDescriptors.CalcTPSA(molecule),
        float(Lipinski.NumHDonors(molecule)),
        float(Lipinski.NumHAcceptors(molecule)),
        float(Lipinski.NumRotatableBonds(molecule)),
        rdMolDescriptors.CalcFractionCSP3(molecule),
        aromatic_atoms / heavy_atoms if heavy_atoms else 0.0,
    )
    if any(not math.isfinite(float(value)) for value in values):
        raise SolubilityCapabilityError(f"non-finite descriptor produced for SMILES: {smiles!r}")
    return tuple(float(value) for value in values)


def _fingerprint(smiles: str):
    _, _, _, _, _, rdFingerprintGenerator, _, _, _ = _rdkit()
    molecule = _molecule(smiles)
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=MORGAN_RADIUS, fpSize=MORGAN_BITS)
    return generator.GetFingerprint(molecule)


def morgan_vector(smiles: str) -> tuple[float, ...]:
    return tuple(float(value) for value in _fingerprint(smiles))


def _canonical_smiles(smiles: str) -> str:
    Chem, *_ = _rdkit()
    molecule = _molecule(smiles)
    return Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)


def _murcko_or_none(smiles: str) -> str | None:
    *_, MurckoScaffold, _ = _rdkit()
    molecule = _molecule(smiles)
    scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=molecule)
    return scaffold or None


def _hybrid_group_labels(records: Sequence[SolubilityRecord]) -> tuple[str, ...]:
    _, DataStructs, *rest = _rdkit()
    Butina = rest[-1]
    labels: list[str | None] = [None] * len(records)
    acyclic: list[tuple[str, int, Any]] = []
    for index, record in enumerate(records):
        murcko = _murcko_or_none(record.smiles)
        if murcko is not None:
            labels[index] = f"RING:{murcko}"
        else:
            acyclic.append((_canonical_smiles(record.smiles), index, _fingerprint(record.smiles)))
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
        raise SolubilityCapabilityError("hybrid structural grouping left an unlabeled molecule")
    return tuple(str(label) for label in labels)


def _hybrid_training_partition(records: Sequence[SolubilityRecord]) -> tuple[SolubilityRecord, ...]:
    labels = _hybrid_group_labels(records)
    grouped: dict[str, list[SolubilityRecord]] = defaultdict(list)
    for record, label in zip(records, labels):
        grouped[label].append(record)
    buckets = list(grouped.items())
    random.Random(PARENT_SEED).shuffle(buckets)
    buckets.sort(key=lambda pair: len(pair[1]), reverse=True)
    targets = {
        "train": 0.8 * len(records),
        "validation": 0.1 * len(records),
        "test": 0.1 * len(records),
    }
    partitions: dict[str, list[SolubilityRecord]] = {"train": [], "validation": [], "test": []}
    for _, bucket in buckets:
        choices = sorted(
            partitions,
            key=lambda name: (len(partitions[name]) - targets[name]) / max(targets[name], 1.0),
        )
        partitions[choices[0]].extend(bucket)
    if not partitions["train"]:
        raise SolubilityCapabilityError("hybrid structural split produced an empty training partition")
    return tuple(partitions["train"])


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise SolubilityCapabilityError("applicability-domain percentile requires values")
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


def _training_loo_similarities(fingerprints: Sequence[Any]) -> tuple[float, ...]:
    _, DataStructs, *_ = _rdkit()
    if len(fingerprints) < 2:
        raise SolubilityCapabilityError("applicability domain requires at least two training structures")
    result: list[float] = []
    values = list(fingerprints)
    for index, fingerprint in enumerate(values):
        peers = values[:index] + values[index + 1 :]
        result.append(max(float(value) for value in DataStructs.BulkTanimotoSimilarity(fingerprint, peers)))
    return tuple(result)


def _max_similarity(train_fingerprints: Sequence[Any], query_fingerprint: Any) -> float:
    _, DataStructs, *_ = _rdkit()
    if not train_fingerprints:
        raise SolubilityCapabilityError("applicability domain has no training fingerprints")
    return max(float(value) for value in DataStructs.BulkTanimotoSimilarity(query_fingerprint, train_fingerprints))


def _feature_vector(smiles: str) -> tuple[float, ...]:
    return descriptor_vector(smiles) + morgan_vector(smiles)


class FrozenESOLSolubilityPredictor:
    """Reconstruct the frozen seed-42 ESOL model and expose bounded inference."""

    def __init__(self, model: Any, train_fingerprints: Sequence[Any], applicability_threshold: float, *, training_hash: str, dataset_hash_value: str):
        self.model = model
        self.train_fingerprints = tuple(train_fingerprints)
        self.applicability_threshold = float(applicability_threshold)
        self.training_hash = training_hash
        self.dataset_hash = dataset_hash_value

    @classmethod
    def fit(
        cls,
        records: Sequence[SolubilityRecord],
        *,
        enforce_frozen_identity: bool = True,
    ) -> "FrozenESOLSolubilityPredictor":
        values = tuple(records)
        observed_dataset_hash = dataset_hash(values)
        if enforce_frozen_identity and observed_dataset_hash != EXPECTED_DATASET_HASH:
            raise SolubilityCapabilityError(
                "ESOL dataset identity mismatch; refusing to call a different dataset the frozen v2 model"
            )
        train = _hybrid_training_partition(values)
        observed_training_hash = dataset_hash(train)
        if enforce_frozen_identity:
            if len(train) != EXPECTED_TRAINING_COUNT:
                raise SolubilityCapabilityError(
                    f"frozen ESOL training count drifted: expected {EXPECTED_TRAINING_COUNT}, got {len(train)}"
                )
            if observed_training_hash != EXPECTED_TRAINING_HASH:
                raise SolubilityCapabilityError(
                    "frozen ESOL training partition identity mismatch"
                )
        try:
            import sklearn
            from sklearn.ensemble import RandomForestRegressor
        except ImportError as exc:
            raise SolubilityCapabilityError(
                "frozen ESOL predictor requires scikit-learn; install the 'discovery' extra"
            ) from exc
        model = RandomForestRegressor(**HYPERPARAMETERS)
        x_train = [_feature_vector(record.smiles) for record in train]
        y_train = [record.measured_log_s_mol_l for record in train]
        model.fit(x_train, y_train)
        fingerprints = tuple(_fingerprint(record.smiles) for record in train)
        threshold = _percentile(_training_loo_similarities(fingerprints), AD_TRAIN_QUANTILE)
        predictor = cls(
            model,
            fingerprints,
            threshold,
            training_hash=observed_training_hash,
            dataset_hash_value=observed_dataset_hash,
        )
        predictor.sklearn_version = getattr(sklearn, "__version__", "unknown")
        return predictor

    @classmethod
    def from_esol_csv(
        cls,
        path: str | Path,
        *,
        enforce_frozen_identity: bool = True,
    ) -> "FrozenESOLSolubilityPredictor":
        records = parse_esol_csv(Path(path).read_text(encoding="utf-8"))
        return cls.fit(records, enforce_frozen_identity=enforce_frozen_identity)

    @classmethod
    def from_public_source(
        cls,
        *,
        timeout: float = 30.0,
    ) -> "FrozenESOLSolubilityPredictor":
        request = Request(DATASET_URL, headers={"User-Agent": "Research-OS/5.1 Molecular-Discovery"})
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed recorded HTTPS source
                text = response.read().decode("utf-8")
        except Exception as exc:
            raise SolubilityCapabilityError(f"failed to retrieve frozen ESOL source from {DATASET_URL}") from exc
        return cls.fit(parse_esol_csv(text), enforce_frozen_identity=True)

    @property
    def model_identity(self) -> str:
        return sha256_json(
            {
                "protocol_id": PROTOCOL_ID,
                "parent_protocol_id": PARENT_PROTOCOL_ID,
                "dataset_hash": self.dataset_hash,
                "training_hash": self.training_hash,
                "hyperparameters": HYPERPARAMETERS,
                "representation": {
                    "descriptors": list(DESCRIPTOR_NAMES),
                    "morgan_radius": MORGAN_RADIUS,
                    "morgan_bits": MORGAN_BITS,
                },
                "applicability_threshold": self.applicability_threshold,
                "sklearn_version": getattr(self, "sklearn_version", "unknown"),
            }
        )

    def predict(self, smiles: str) -> SolubilityPrediction:
        feature = _feature_vector(smiles)
        prediction = float(self.model.predict([feature])[0])
        similarity = _max_similarity(self.train_fingerprints, _fingerprint(smiles))
        return SolubilityPrediction(
            smiles=smiles,
            predicted_log_s_mol_l=prediction,
            max_training_tanimoto=similarity,
            applicability_threshold=self.applicability_threshold,
            in_domain=similarity >= self.applicability_threshold,
        )

    def evidence_manifest(self) -> dict[str, Any]:
        return {
            "protocol_id": PROTOCOL_ID,
            "parent_protocol_id": PARENT_PROTOCOL_ID,
            "model_identity": self.model_identity,
            "model_name": MODEL_NAME,
            "evidence_level": "E1_ML",
            "training": {
                "dataset_id": DATASET_ID,
                "dataset_doi": DATASET_DOI,
                "dataset_url": DATASET_URL,
                "dataset_hash": self.dataset_hash,
                "training_count": EXPECTED_TRAINING_COUNT,
                "training_hash": self.training_hash,
                "seed": PARENT_SEED,
                "representation": "8 RDKit descriptors + Morgan radius 2 / 2048 bits",
                "hyperparameters": dict(HYPERPARAMETERS),
            },
            "applicability_domain": {
                "metric": "Morgan radius 2 / 2048-bit Tanimoto",
                "rule": "5th percentile of leave-one-out nearest-neighbor similarity in the frozen ESOL training partition",
                "threshold": self.applicability_threshold,
            },
            "validation": {
                "internal_multi_seed": {
                    "seeds": [7, 21, 42, 84, 101],
                    "rmse_mean": 0.803,
                    "rmse_sd": 0.113,
                    "r2_mean": 0.859,
                    "r2_sd": 0.031,
                },
                "external_aqsoldb_decontaminated": {
                    "retained_records": 8863,
                    "mae": 1.0202,
                    "rmse": 1.4359,
                    "r2": 0.6421,
                    "in_domain_count": 6677,
                    "in_domain_rmse": 1.2349,
                    "out_of_domain_count": 2186,
                    "out_of_domain_rmse": 1.9239,
                    "scientific_result_hash": "2bcd795284143f73c1207f9c0a20fdd2272b5fb05cccbb3ac5da7d25e5e44057",
                },
                "diagnostic_followups": {
                    "reliability_strata": {
                        "raw_higher_minus_lower_rmse": 0.8541281588526171,
                        "scientific_result_hash": "eeca8e4f2c7006791913745204d7e7129e25d0f6a1a56dd67487ae4456b4347a",
                    },
                    "controlled_structural_target_confounders": {
                        "higher_minus_lower_rmse": 0.4663940071863022,
                        "scientific_result_hash": "2427a72653d0adee34e30fa241c1dd416925159ad7b84bdc495f698913e95143",
                    },
                    "source_aware_control": {
                        "higher_minus_lower_rmse": 0.37427753546114495,
                        "support": 312,
                        "shared_cells": 68,
                        "contributing_sources": ["A", "B", "C", "D", "E", "F", "I"],
                        "scientific_result_hash": "3516c82f572e119c11b0033738d408dda5c11fdda6717656de83c76f222a003e",
                    },
                },
            },
            "limitations": [
                "Prediction is an ML estimate of aqueous logS, not an experimental measurement.",
                "External AqSolDB error is materially larger than internal ESOL structural-holdout error.",
                "OUT_OF_DOMAIN predictions must not be treated as having the same support as in-domain predictions.",
                "AqSolDB aggregates heterogeneous measurement sources and protocols.",
                "Prediction error is associated with AqSolDB repeated-measurement dispersion strata, but structural, target-range and source effects materially confound that association.",
                "The source-aware residual association is heterogeneous across source datasets and is not evidence that measurement dispersion causes model error.",
                "This capability establishes neither safety, efficacy, synthesizability nor clinical validity.",
            ],
        }


__all__ = [
    "DATASET_DOI",
    "DATASET_ID",
    "DATASET_URL",
    "EXPECTED_DATASET_HASH",
    "EXPECTED_TRAINING_HASH",
    "FrozenESOLSolubilityPredictor",
    "PROTOCOL_ID",
    "SolubilityCapabilityError",
    "SolubilityPrediction",
    "SolubilityRecord",
    "dataset_hash",
    "descriptor_vector",
    "morgan_vector",
    "parse_esol_csv",
]
