"""AqSolDB structural coverage for Molecular Discovery candidate neighborhoods.

This capability asks a narrower question than prediction: does a candidate have
experimentally measured structural neighbors in the immutable AqSolDB source?
It does not train or tune a new model.
"""

from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import asdict, dataclass
import io
import math
import statistics
from typing import Any, Sequence
from urllib.request import Request, urlopen

from research_os.core.hashing import sha256_json


CAPABILITY_ID = "research-os.molecular-discovery.aqsoldb-coverage.v1"
AQSOLDB_ID = "AqSolDB"
AQSOLDB_DOI = "10.1038/s41597-019-0151-1"
AQSOLDB_SOURCE_COMMIT = "98cdd10a372058743e4f3fb950a1c9974ec9603a"
AQSOLDB_SOURCE_BLOB_SHA = "67016e030cf0a741e250ba0267bd84461041db5f"
AQSOLDB_URL = (
    "https://raw.githubusercontent.com/mcsorkun/AqSolDB/"
    f"{AQSOLDB_SOURCE_COMMIT}/results/data_curated.csv"
)
EXPECTED_SOURCE_ROW_COUNT = 9982
EXPECTED_PARSED_SOURCE_HASH = "2c6e56f56389f0fd99fa2a3c843446f98b6b068a3f93aaab71a08822caa085f4"
MORGAN_RADIUS = 2
MORGAN_BITS = 2048
TOP_K = 5
SIMILARITY_BINS = (
    (0.0, 0.4, "[0.0,0.4)"),
    (0.4, 0.6, "[0.4,0.6)"),
    (0.6, 0.8, "[0.6,0.8)"),
    (0.8, 1.0000000001, "[0.8,1.0]"),
)


class AqSolDBCoverageError(RuntimeError):
    """Fail-closed error for source or chemistry identity problems."""


@dataclass(frozen=True)
class AqSolDBSourceRecord:
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
class AqSolDBStructureGroup:
    canonical_smiles: str
    inchikey: str
    observation_count: int
    source_ids: tuple[str, ...]
    measured_log_s_values: tuple[float, ...]
    median_measured_log_s_mol_l: float
    minimum_measured_log_s_mol_l: float
    maximum_measured_log_s_mol_l: float

    @property
    def measurement_span(self) -> float:
        return self.maximum_measured_log_s_mol_l - self.minimum_measured_log_s_mol_l

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "source_ids": list(self.source_ids),
            "measured_log_s_values": list(self.measured_log_s_values),
            "measurement_span": self.measurement_span,
        }


@dataclass(frozen=True)
class AqSolDBNeighbor:
    similarity: float
    canonical_smiles: str
    inchikey: str
    observation_count: int
    median_measured_log_s_mol_l: float
    minimum_measured_log_s_mol_l: float
    maximum_measured_log_s_mol_l: float
    source_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "source_ids": list(self.source_ids),
        }


@dataclass(frozen=True)
class CandidateCoverage:
    candidate_id: str
    smiles: str
    canonical_smiles: str
    inchikey: str
    nearest_similarity: float
    similarity_bin: str
    neighbors_ge_0_4: int
    neighbors_ge_0_6: int
    neighbors_ge_0_8: int
    top_neighbors: tuple[AqSolDBNeighbor, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "top_neighbors": [item.to_dict() for item in self.top_neighbors],
        }


@dataclass(frozen=True)
class AqSolDBCoverageReport:
    capability_id: str
    source_url: str
    source_doi: str
    source_commit: str
    source_blob_sha: str
    source_row_count: int
    parsed_source_hash: str
    invalid_structure_count: int
    unique_structure_count: int
    candidate_count: int
    candidates: tuple[CandidateCoverage, ...]
    limitations: tuple[str, ...]

    @property
    def scientific_hash(self) -> str:
        return sha256_json(
            {
                "capability_id": self.capability_id,
                "source_url": self.source_url,
                "source_doi": self.source_doi,
                "source_commit": self.source_commit,
                "source_blob_sha": self.source_blob_sha,
                "source_row_count": self.source_row_count,
                "parsed_source_hash": self.parsed_source_hash,
                "invalid_structure_count": self.invalid_structure_count,
                "unique_structure_count": self.unique_structure_count,
                "candidate_count": self.candidate_count,
                "candidates": [item.to_dict() for item in self.candidates],
                "limitations": list(self.limitations),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "source_url": self.source_url,
            "source_doi": self.source_doi,
            "source_commit": self.source_commit,
            "source_blob_sha": self.source_blob_sha,
            "source_row_count": self.source_row_count,
            "parsed_source_hash": self.parsed_source_hash,
            "invalid_structure_count": self.invalid_structure_count,
            "unique_structure_count": self.unique_structure_count,
            "candidate_count": self.candidate_count,
            "candidates": [item.to_dict() for item in self.candidates],
            "limitations": list(self.limitations),
            "scientific_hash": self.scientific_hash,
        }


def parse_aqsoldb_csv(text: str) -> tuple[tuple[AqSolDBSourceRecord, ...], int, str]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise AqSolDBCoverageError("AqSolDB dataset is missing a CSV header")
    required = {"ID", "SMILES", "Solubility"}
    missing = required.difference(reader.fieldnames)
    if missing:
        raise AqSolDBCoverageError(f"AqSolDB is missing required columns: {sorted(missing)}")

    records: list[AqSolDBSourceRecord] = []
    row_count = 0
    for row_index, row in enumerate(reader, start=2):
        row_count += 1
        source_id = str(row.get("ID") or f"row-{row_index}").strip() or f"row-{row_index}"
        smiles = str(row.get("SMILES") or "").strip()
        if not smiles:
            continue
        raw_target = str(row.get("Solubility") or "").strip()
        try:
            target = float(raw_target)
        except ValueError:
            continue
        if not math.isfinite(target):
            continue
        source_inchikey = str(row.get("InChIKey") or "").strip() or None
        records.append(AqSolDBSourceRecord(source_id, smiles, target, source_inchikey))
    if not records:
        raise AqSolDBCoverageError("AqSolDB contains no usable records")
    parsed_hash = sha256_json([record.source_dict() for record in records])
    return tuple(records), row_count, parsed_hash


def download_aqsoldb(*, timeout: float = 60.0) -> tuple[tuple[AqSolDBSourceRecord, ...], int, str]:
    request = Request(AQSOLDB_URL, headers={"User-Agent": "Research-OS/5.1 MOLDISC-002"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - immutable recorded HTTPS source
            payload = response.read().decode("utf-8")
    except Exception as exc:
        raise AqSolDBCoverageError(f"failed to retrieve AqSolDB from {AQSOLDB_URL}") from exc
    records, row_count, parsed_hash = parse_aqsoldb_csv(payload)
    if row_count != EXPECTED_SOURCE_ROW_COUNT:
        raise AqSolDBCoverageError(
            f"AqSolDB row-count identity drift: expected {EXPECTED_SOURCE_ROW_COUNT}, got {row_count}"
        )
    if parsed_hash != EXPECTED_PARSED_SOURCE_HASH:
        raise AqSolDBCoverageError("AqSolDB parsed source identity drift")
    return records, row_count, parsed_hash


def _rdkit():
    try:
        from rdkit import Chem, DataStructs
        from rdkit.Chem import inchi, rdFingerprintGenerator
    except ImportError as exc:
        raise AqSolDBCoverageError(
            "AqSolDB coverage requires RDKit; install the 'discovery' extra"
        ) from exc
    return Chem, DataStructs, inchi, rdFingerprintGenerator


def _identity(smiles: str) -> tuple[str, str, Any]:
    Chem, _, inchi, rdFingerprintGenerator = _rdkit()
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise AqSolDBCoverageError(f"invalid or unsanitizable SMILES: {smiles!r}")
    canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    inchikey = inchi.MolToInchiKey(molecule)
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=MORGAN_RADIUS, fpSize=MORGAN_BITS)
    return canonical, inchikey, generator.GetFingerprint(molecule)


def curate_structure_groups(
    records: Sequence[AqSolDBSourceRecord],
) -> tuple[tuple[AqSolDBStructureGroup, ...], int]:
    grouped: dict[str, list[tuple[AqSolDBSourceRecord, str]]] = defaultdict(list)
    invalid = 0
    for record in records:
        try:
            canonical, inchikey, _ = _identity(record.smiles)
        except AqSolDBCoverageError:
            invalid += 1
            continue
        grouped[canonical].append((record, inchikey))

    groups: list[AqSolDBStructureGroup] = []
    for canonical in sorted(grouped):
        members = sorted(
            grouped[canonical],
            key=lambda item: (
                item[0].source_id,
                item[0].measured_log_s_mol_l,
                item[0].smiles,
            ),
        )
        values = tuple(float(item[0].measured_log_s_mol_l) for item in members)
        inchikeys = {item[1] for item in members}
        if len(inchikeys) != 1:
            raise AqSolDBCoverageError(
                f"canonical structure {canonical!r} maps to multiple active-runtime InChIKeys"
            )
        groups.append(
            AqSolDBStructureGroup(
                canonical_smiles=canonical,
                inchikey=next(iter(inchikeys)),
                observation_count=len(members),
                source_ids=tuple(item[0].source_id for item in members),
                measured_log_s_values=values,
                median_measured_log_s_mol_l=float(statistics.median(values)),
                minimum_measured_log_s_mol_l=min(values),
                maximum_measured_log_s_mol_l=max(values),
            )
        )
    if not groups:
        raise AqSolDBCoverageError("AqSolDB curation left no valid structures")
    return tuple(groups), invalid


def _similarity_bin(value: float) -> str:
    for lower, upper, label in SIMILARITY_BINS:
        if lower <= value < upper:
            return label
    raise AqSolDBCoverageError(f"similarity {value!r} is outside [0,1]")


def assess_aqsoldb_coverage(
    candidates: Sequence[dict[str, Any]],
    *,
    records: Sequence[AqSolDBSourceRecord],
    source_row_count: int,
    parsed_source_hash: str,
) -> AqSolDBCoverageReport:
    _, DataStructs, _, _ = _rdkit()
    groups, invalid_structure_count = curate_structure_groups(records)

    indexed: list[tuple[AqSolDBStructureGroup, Any]] = []
    for group in groups:
        _, _, fingerprint = _identity(group.canonical_smiles)
        indexed.append((group, fingerprint))
    fingerprints = [item[1] for item in indexed]

    results: list[CandidateCoverage] = []
    for raw in candidates:
        candidate_id = str(raw.get("id") or raw.get("candidate_id") or "").strip()
        smiles = str(raw.get("smiles") or raw.get("SMILES") or "").strip()
        if not candidate_id or not smiles:
            raise AqSolDBCoverageError("coverage candidates require id and smiles")
        canonical, inchikey, query_fp = _identity(smiles)
        similarities = [float(value) for value in DataStructs.BulkTanimotoSimilarity(query_fp, fingerprints)]
        ranked_indices = sorted(
            range(len(indexed)),
            key=lambda index: (
                -similarities[index],
                indexed[index][0].canonical_smiles,
                indexed[index][0].inchikey,
            ),
        )
        top: list[AqSolDBNeighbor] = []
        for index in ranked_indices[:TOP_K]:
            group = indexed[index][0]
            top.append(
                AqSolDBNeighbor(
                    similarity=similarities[index],
                    canonical_smiles=group.canonical_smiles,
                    inchikey=group.inchikey,
                    observation_count=group.observation_count,
                    median_measured_log_s_mol_l=group.median_measured_log_s_mol_l,
                    minimum_measured_log_s_mol_l=group.minimum_measured_log_s_mol_l,
                    maximum_measured_log_s_mol_l=group.maximum_measured_log_s_mol_l,
                    source_ids=group.source_ids,
                )
            )
        nearest = similarities[ranked_indices[0]]
        results.append(
            CandidateCoverage(
                candidate_id=candidate_id,
                smiles=smiles,
                canonical_smiles=canonical,
                inchikey=inchikey,
                nearest_similarity=nearest,
                similarity_bin=_similarity_bin(nearest),
                neighbors_ge_0_4=sum(value >= 0.4 for value in similarities),
                neighbors_ge_0_6=sum(value >= 0.6 for value in similarities),
                neighbors_ge_0_8=sum(value >= 0.8 for value in similarities),
                top_neighbors=tuple(top),
            )
        )

    results.sort(key=lambda item: item.candidate_id)
    limitations = (
        "AqSolDB coverage is descriptive source evidence; it is not a trained predictor.",
        "Tanimoto similarity is a structural-neighborhood measure and does not establish shared mechanism or biological activity.",
        "AqSolDB aggregates heterogeneous measurements and source protocols.",
        "Repeated measurements are preserved within canonical structure groups rather than averaged into a new training target.",
        "The historical 0.4/0.6/0.8 similarity boundaries are reused only as descriptive bins from ONLINE-EXP-002.",
        "Coverage does not establish affinity, potency, efficacy, safety, synthesizability or clinical value.",
    )
    return AqSolDBCoverageReport(
        capability_id=CAPABILITY_ID,
        source_url=AQSOLDB_URL,
        source_doi=AQSOLDB_DOI,
        source_commit=AQSOLDB_SOURCE_COMMIT,
        source_blob_sha=AQSOLDB_SOURCE_BLOB_SHA,
        source_row_count=source_row_count,
        parsed_source_hash=parsed_source_hash,
        invalid_structure_count=invalid_structure_count,
        unique_structure_count=len(groups),
        candidate_count=len(results),
        candidates=tuple(results),
        limitations=limitations,
    )


def run_public_aqsoldb_coverage(
    candidates: Sequence[dict[str, Any]],
    *,
    timeout: float = 60.0,
) -> AqSolDBCoverageReport:
    records, row_count, parsed_hash = download_aqsoldb(timeout=timeout)
    return assess_aqsoldb_coverage(
        candidates,
        records=records,
        source_row_count=row_count,
        parsed_source_hash=parsed_hash,
    )


__all__ = [
    "AQSOLDB_DOI",
    "AQSOLDB_SOURCE_BLOB_SHA",
    "AQSOLDB_SOURCE_COMMIT",
    "AQSOLDB_URL",
    "CAPABILITY_ID",
    "AqSolDBCoverageError",
    "AqSolDBCoverageReport",
    "CandidateCoverage",
    "assess_aqsoldb_coverage",
    "curate_structure_groups",
    "download_aqsoldb",
    "parse_aqsoldb_csv",
    "run_public_aqsoldb_coverage",
]
