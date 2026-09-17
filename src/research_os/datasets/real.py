"""Pinned, license-aware ingestion for the v1.6 real-data milestone.

The module deliberately keeps the network boundary small: downloading is an
explicit operation, the downloaded bytes are hashed before use, and the
curated dataset is written with a manifest that retains source and condition
metadata.  The repository ships only a small CC0-derived sample for tests;
the full AqSolDB-G file is never fetched implicitly by the test suite.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile
from typing import Any, Iterable, Mapping
from urllib.request import Request, urlopen

from research_os.core.hashing import sha256_file, sha256_json
from research_os.core.provenance import SourceType
from research_os.core.types import EvidenceLevel, GateStatus
from research_os.datasets.registry import DatasetRegistry
from research_os.datasets.schema import DatasetManifest, DatasetSourceType


AQSOLDB_COMMIT = "8e02b548fd9a78778ff89a5aa9a460d1a289cc3a"
AQSOLDB_G_SHA256 = "e3b80a24edb5528fe3a7c4a808b26045804c73680183f43c21afbec905158071"
AQSOLDB_G_URL = f"https://raw.githubusercontent.com/mcsorkun/AqSolDB/{AQSOLDB_COMMIT}/data/dataset-G.csv"
AQSOLDB_LICENSE_URL = f"https://raw.githubusercontent.com/mcsorkun/AqSolDB/{AQSOLDB_COMMIT}/data/LICENSE"
AQSOLDB_PAPER_DOI = "10.1038/s41597-019-0151-1"


@dataclass(frozen=True)
class SourceRecord:
    """Attribution and redistribution record for an external dataset source."""

    source_id: str
    title: str
    url: str
    license: str
    source_commit: str | None = None
    source_sha256: str | None = None
    citation: str | None = None
    source_type: SourceType = SourceType.DATASET
    redistribution_status: str = "REQUIRES_SOURCE_LICENSE_REVIEW"
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "url": self.url,
            "license": self.license,
            "source_commit": self.source_commit,
            "source_sha256": self.source_sha256,
            "citation": self.citation,
            "source_type": self.source_type.value,
            "redistribution_status": self.redistribution_status,
            "retrieved_at": self.retrieved_at,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class RealDatasetSpec:
    dataset_id: str
    version: str
    schema_id: str
    target: str
    units: str
    conditions: dict[str, Any]
    measurement_method: str
    source_id: str
    source_url: str
    license: str
    license_url: str
    source_commit: str
    expected_sha256: str | None
    source_title: str
    citation: str
    notes: str

    def source_record(self, *, source_sha256: str | None = None) -> SourceRecord:
        return SourceRecord(
            source_id=self.source_id,
            title=self.source_title,
            url=self.source_url,
            license=self.license,
            source_commit=self.source_commit,
            source_sha256=source_sha256 or self.expected_sha256,
            citation=self.citation,
            redistribution_status="CC0_SOURCE_WITH_THIRD_PARTY_RIGHTS_DISCLAIMER",
            notes=f"License text: {self.license_url}. {self.notes}",
        )


AQSOLDB_G_SPEC = RealDatasetSpec(
    dataset_id="aqsoldb-g",
    version="2019-g-8e02b5",
    schema_id="AQSOLDB-G-EXPERIMENTAL-LOGS-V1",
    target="Solubility",
    units="log10(mol/L)",
    conditions={
        "medium": "aqueous",
        "temperature_celsius": 25.0,
        "temperature_tolerance_celsius": 0.0,
        "measurement_type": "experimental",
    },
    measurement_method="curated empirical aqueous solubility measurements; source methods retained upstream",
    source_id="AQSOLDB-G",
    source_url=AQSOLDB_G_URL,
    license="CC0-1.0",
    license_url=AQSOLDB_LICENSE_URL,
    source_commit=AQSOLDB_COMMIT,
    expected_sha256=AQSOLDB_G_SHA256,
    source_title="AqSolDB dataset-G.csv (Delaney aqueous solubility subset)",
    citation=f"Sorkun et al., AqSolDB, Scientific Data (2019), DOI:{AQSOLDB_PAPER_DOI}",
    notes="Official GitHub data file pinned by commit and SHA-256.",
)


AQSOLDB_G_SAMPLE_SPEC = RealDatasetSpec(
    dataset_id="aqsoldb-g-real-sample",
    version="1.0.0",
    schema_id="AQSOLDB-G-EXPERIMENTAL-LOGS-V1",
    target=AQSOLDB_G_SPEC.target,
    units=AQSOLDB_G_SPEC.units,
    conditions=dict(AQSOLDB_G_SPEC.conditions),
    measurement_method=AQSOLDB_G_SPEC.measurement_method,
    source_id=AQSOLDB_G_SPEC.source_id,
    source_url=AQSOLDB_G_SPEC.source_url,
    license=AQSOLDB_G_SPEC.license,
    license_url=AQSOLDB_G_SPEC.license_url,
    source_commit=AQSOLDB_G_SPEC.source_commit,
    expected_sha256=None,
    source_title=AQSOLDB_G_SPEC.source_title,
    citation=AQSOLDB_G_SPEC.citation,
    notes="Checked-in CI subset derived from the official CC0 data file; not the full AqSolDB-G release.",
)


@dataclass(frozen=True)
class RealDatasetValidation:
    status: GateStatus
    rule_id: str
    path: str
    row_count: int
    valid_count: int
    invalid_count: int
    required_columns: tuple[str, ...]
    errors: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status == GateStatus.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "rule_id": self.rule_id,
            "path": self.path,
            "row_count": self.row_count,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "required_columns": list(self.required_columns),
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class RealDatasetIngestResult:
    source: SourceRecord
    validation: RealDatasetValidation
    manifest: DatasetManifest
    raw_path: str
    curated_csv_path: str
    curated_parquet_path: str
    records: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "validation": self.validation.to_dict(),
            "manifest": self.manifest.to_dict(),
            "raw_path": self.raw_path,
            "curated_csv_path": self.curated_csv_path,
            "curated_parquet_path": self.curated_parquet_path,
            "record_count": len(self.records),
        }


def download_aqsoldb_g(destination: str | Path, *, timeout: float = 30.0, spec: RealDatasetSpec = AQSOLDB_G_SPEC) -> Path:
    """Download a pinned source file and reject bytes with the wrong digest."""

    if not spec.expected_sha256:
        raise ValueError("a download spec must declare an expected SHA-256")
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    request = Request(spec.source_url, headers={"User-Agent": "research-os-v1.6"})
    temporary: Path | None = None
    try:
        with urlopen(request, timeout=timeout) as response, NamedTemporaryFile("wb", delete=False, dir=target.parent, prefix=f".{target.name}.", suffix=".part") as handle:
            temporary = Path(handle.name)
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
        observed = sha256_file(temporary)
        if observed.lower() != spec.expected_sha256.lower():
            raise ValueError(f"{spec.dataset_id} SHA-256 mismatch: expected {spec.expected_sha256}, observed {observed}")
        os.replace(temporary, target)
        temporary = None
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _required_columns() -> tuple[str, ...]:
    return ("ID", "SMILES", "Solubility")


def validate_real_aqsoldb_g(path: str | Path, *, spec: RealDatasetSpec = AQSOLDB_G_SPEC) -> RealDatasetValidation:
    source = Path(path)
    required = _required_columns()
    if not source.is_file():
        return RealDatasetValidation(GateStatus.FAIL, "REAL-DATA-SOURCE-001", str(source), 0, 0, 0, required, ("source file does not exist",))
    errors: list[str] = []
    row_count = 0
    valid_count = 0
    identifiers: set[str] = set()
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = tuple(reader.fieldnames or ())
            missing = [column for column in required if column not in columns]
            if missing:
                return RealDatasetValidation(GateStatus.FAIL, "REAL-DATA-SCHEMA-001", str(source), 0, 0, 0, required, (f"missing required columns: {', '.join(missing)}",))
            for row in reader:
                row_count += 1
                identifier = str(row.get("ID") or "").strip()
                smiles = str(row.get("SMILES") or "").strip()
                try:
                    target = float(str(row.get("Solubility") or "").strip())
                except ValueError:
                    target = float("nan")
                valid = bool(identifier and smiles and identifier not in identifiers)
                if valid:
                    try:
                        import math
                        valid = math.isfinite(target)
                    except (TypeError, ValueError):
                        valid = False
                if valid:
                    try:
                        from rdkit import Chem
                        valid = Chem.MolFromSmiles(smiles) is not None
                    except ImportError as exc:
                        return RealDatasetValidation(GateStatus.INSUFFICIENT_EVIDENCE, "REAL-DATA-DEPENDENCY-001", str(source), row_count, valid_count, row_count - valid_count, required, (f"RDKit is required for molecular validation: {exc}",))
                if valid:
                    identifiers.add(identifier)
                    valid_count += 1
                elif len(errors) < 10:
                    errors.append(f"invalid row {row_count}: id={identifier!r}")
    except (OSError, UnicodeError, csv.Error) as exc:
        return RealDatasetValidation(GateStatus.FAIL, "REAL-DATA-IO-001", str(source), row_count, valid_count, row_count - valid_count, required, (f"could not read CSV: {exc}",))
    if row_count == 0:
        errors.append("dataset contains no rows")
    if valid_count != row_count:
        return RealDatasetValidation(GateStatus.FAIL, "REAL-DATA-VALIDATION-001", str(source), row_count, valid_count, row_count - valid_count, required, tuple(errors))
    return RealDatasetValidation(GateStatus.PASS, "REAL-DATA-VALIDATION-001", str(source), row_count, valid_count, 0, required)


def _normalized_records(path: str | Path, *, spec: RealDatasetSpec) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            records.append(
                {
                    "compound_id": str(row["ID"]).strip(),
                    "name": str(row.get("Name") or "").strip(),
                    "smiles": str(row["SMILES"]).strip(),
                    "target": float(row["Solubility"]),
                    "target_name": spec.target,
                    "target_units": spec.units,
                    "source_group": spec.source_id,
                    "experimental": True,
                }
            )
    return records


def _write_normalized_csv(records: Iterable[Mapping[str, Any]], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = ("compound_id", "name", "smiles", "target", "target_name", "target_units", "source_group", "experimental")
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    return target


def ingest_aqsoldb_g(
    source_path: str | Path,
    output_root: str | Path,
    *,
    spec: RealDatasetSpec = AQSOLDB_G_SPEC,
    registry: DatasetRegistry | None = None,
) -> RealDatasetIngestResult:
    """Validate, preserve raw bytes, normalize and register an AqSolDB-G file."""

    source_path = Path(source_path)
    validation = validate_real_aqsoldb_g(source_path, spec=spec)
    if not validation.passed:
        raise ValueError(f"real dataset validation failed: {validation.to_dict()}")
    observed_hash = sha256_file(source_path)
    if spec.expected_sha256 and observed_hash.lower() != spec.expected_sha256.lower():
        raise ValueError(f"{spec.dataset_id} SHA-256 mismatch: expected {spec.expected_sha256}, observed {observed_hash}")
    records = _normalized_records(source_path, spec=spec)
    root = Path(output_root)
    raw_path = root / "raw" / f"{spec.dataset_id}-{spec.version}.csv"
    curated_csv = root / "curated" / f"{spec.dataset_id}-{spec.version}.csv"
    curated_parquet = root / "curated" / f"{spec.dataset_id}-{spec.version}.parquet"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.resolve() != raw_path.resolve():
        shutil.copyfile(source_path, raw_path)
    _write_normalized_csv(records, curated_csv)
    source = spec.source_record(source_sha256=observed_hash)
    active_registry = registry or DatasetRegistry(root=root)
    try:
        manifest = active_registry.get(spec.dataset_id, spec.version)
        if not active_registry.verify_dataset(spec.dataset_id, spec.version):
            raise ValueError(f"existing dataset manifest does not verify: {spec.dataset_id}@{spec.version}")
    except KeyError:
        manifest = active_registry.register_dataset(
            dataset_id=spec.dataset_id,
            version=spec.version,
            schema_id=spec.schema_id,
            path=curated_csv,
            curated_path=curated_parquet,
            transformation_run_id=f"DATA-CURATION-{spec.dataset_id.upper()}-{spec.version}",
            sources=(spec.source_id,),
            licenses=(spec.license,),
            license=spec.license,
            source_types=(DatasetSourceType.CURATED_EXPERIMENTAL,),
            evidence_levels=(EvidenceLevel.E4_CURATED_EXPERIMENTAL,),
            synthetic_fraction=0.0,
            experimental_fraction=1.0,
            computational_fraction=0.0,
            target=spec.target,
            units=spec.units,
            conditions=spec.conditions,
            measurement_method=spec.measurement_method,
            uncertainty="upstream per-observation uncertainty is not included in dataset-G; model uncertainty is residual-calibrated",
            source_url=spec.source_url,
            redistribution_status=source.redistribution_status,
            provenance=(source.source_id,),
            source_file_hash=observed_hash,
            source_path=raw_path,
            notes=spec.notes,
        )
    return RealDatasetIngestResult(source, validation, manifest, str(raw_path), str(curated_csv), str(curated_parquet), tuple(records))


def source_record_digest(source: SourceRecord) -> str:
    return sha256_json(source.to_dict())
