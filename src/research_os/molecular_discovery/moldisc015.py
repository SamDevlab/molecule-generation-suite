"""MOLDISC-015: C-2545 source provenance and stereochemistry resolution.

This module is deliberately an identity/provenance program.  It does not
generate molecules, run docking or ESOL, select candidates, or modify AqSolDB.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import csv
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from research_os.core.hashing import sha256_file, sha256_json


PROGRAM_ID = "MOLDISC-015"
PROGRAM_VERSION = "1.0"
PARENT_MOLDISC014_HASH = "f940d95189616131829a22f9e68a53a960eddf8fd05f5fd7ebac43ece85481ed"
AQSOLDB_SOURCE_ID = "AqSolDB"
AQSOLDB_RECORD_ID = "C-2545"
AQSOLDB_NAME = "phenyl-kni-727"
AQSOLDB_RAW_SMILES = "CC(C)(C)NC(=O)C1N(CSC1(C)C)C(=O)C(O)C(CC2=CC=CC=C2)NC(=O)C3=CC=CC=C3"
AQSOLDB_CANONICAL_SMILES = "CC(C)(C)NC(=O)C1N(C(=O)C(O)C(Cc2ccccc2)NC(=O)c2ccccc2)CSC1(C)C"
AQSOLDB_INCHI = "InChI=1S/C27H35N3O4S/c1-26(2,3)29-24(33)22-27(4,5)35-17-30(22)25(34)21(31)20(16-18-12-8-6-9-13-18)28-23(32)19-14-10-7-11-15-19/h6-15,20-22,31H,16-17H2,1-5H3,(H,28,32)(H,29,33)"
AQSOLDB_INCHIKEY = "URHJIBSBOJFXDI-UHFFFAOYSA-N"
AQSOLDB_FORMULA = "C27H35N3O4S"
AQSOLDB_CONNECTIVITY_BLOCK = "URHJIBSBOJFXDI"
AQSOLDB_MEASURED_LOG_S = -3.62
AQSOLDB_OBSERVATION_COUNT = 1
AQSOLDB_SOURCE_COMMIT = "98cdd10a372058743e4f3fb950a1c9974ec9603a"
AQSOLDB_SOURCE_BLOB_SHA = "67016e030cf0a741e250ba0267bd84461041db5f"
AQSOLDB_PARSED_SOURCE_HASH = "2c6e56f56389f0fd99fa2a3c843446f98b6b068a3f93aaab71a08822caa085f4"
DATASET_C_REFERENCE_DOI = "10.1021/ci400692n"
SOURCE_DELTA_BOTH_INCHIKEY = "URHJIBSBOJFXDI-FDFHNCONSA-N"
SOURCE_DELTA_BOTH_CONNECTIVITY_BLOCK = "URHJIBSBOJFXDI"

RESOLVED_EXACT_STEREOCHEMICAL_IDENTITY = "RESOLVED_EXACT_STEREOCHEMICAL_IDENTITY"
UNRESOLVED_SOURCE_STEREOCHEMISTRY = "UNRESOLVED_SOURCE_STEREOCHEMISTRY"
CONFLICTING_SOURCE_IDENTITIES = "CONFLICTING_SOURCE_IDENTITIES"
SOURCE_RECORD_NOT_RECOVERABLE = "SOURCE_RECORD_NOT_RECOVERABLE"
RESOLUTION_STATUSES = (
    RESOLVED_EXACT_STEREOCHEMICAL_IDENTITY,
    UNRESOLVED_SOURCE_STEREOCHEMISTRY,
    CONFLICTING_SOURCE_IDENTITIES,
    SOURCE_RECORD_NOT_RECOVERABLE,
)


class MOLDISC015Error(RuntimeError):
    """Fail-closed error for MOLDISC-015 protocol or identity drift."""


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def derive_formula_from_inchi(inchi: str) -> str:
    """Return the formula layer from an InChI, without changing the raw value."""
    if not inchi.startswith("InChI="):
        raise MOLDISC015Error("identity record does not contain an InChI")
    parts = inchi.split("/")
    if len(parts) < 2 or not parts[1]:
        raise MOLDISC015Error("InChI has no formula layer")
    return parts[1]


def inchi_stereochemistry_specified(inchi: str) -> bool:
    """Detect InChI stereo layers, excluding the InChI version token itself."""
    layers = inchi.split("/")[2:]
    return any(layer.startswith(prefix) for layer in layers for prefix in ("t", "m", "s"))


def inchikey_connectivity_block(inchikey: str) -> str:
    if not inchikey or "-" not in inchikey:
        raise MOLDISC015Error("invalid InChIKey")
    return inchikey.split("-", 1)[0]


def _field(row: Mapping[str, Any], *names: str) -> str:
    normalized = {_normalized_key(str(key)): value for key, value in row.items()}
    for name in names:
        value = normalized.get(_normalized_key(name))
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    raise MOLDISC015Error(f"CSV row is missing one of fields: {names}")


@dataclass(frozen=True)
class AqSolDBRecord:
    record_id: str
    name: str
    raw_smiles: str
    inchi: str
    inchikey: str
    measured_log_s_mol_l: float
    raw_fields: dict[str, str] = field(default_factory=dict)

    @property
    def formula(self) -> str:
        return derive_formula_from_inchi(self.inchi)

    @property
    def connectivity_block(self) -> str:
        return inchikey_connectivity_block(self.inchikey)

    @property
    def stereochemistry_specified(self) -> bool:
        return inchi_stereochemistry_specified(self.inchi)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "name": self.name,
            "raw_smiles": self.raw_smiles,
            "inchi": self.inchi,
            "inchikey": self.inchikey,
            "formula": self.formula,
            "connectivity_block": self.connectivity_block,
            "measured_log_s_mol_l": self.measured_log_s_mol_l,
            "observation_count": 1,
            "stereochemistry_specified": self.stereochemistry_specified,
            "raw_fields": dict(self.raw_fields),
        }


def parse_aqsoldb_csv(path: str | Path, *, record_id: str = AQSOLDB_RECORD_ID) -> AqSolDBRecord:
    """Parse one exact AqSolDB dataset-C record while retaining all raw fields."""
    source_path = Path(path)
    try:
        with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = [dict(row) for row in reader if row]
    except OSError as exc:
        raise MOLDISC015Error(f"could not read AqSolDB CSV: {source_path}") from exc
    matches = []
    for row in rows:
        try:
            row_id = _field(row, "ID", "record_id", "source_id")
        except MOLDISC015Error:
            continue
        if row_id == record_id:
            matches.append(row)
    if len(matches) != 1:
        raise MOLDISC015Error(f"expected exactly one AqSolDB row {record_id}, found {len(matches)}")
    row = matches[0]
    try:
        return AqSolDBRecord(
            record_id=_field(row, "ID", "record_id", "source_id"),
            name=_field(row, "Name", "name"),
            raw_smiles=_field(row, "SMILES", "smiles"),
            inchi=_field(row, "InChI", "inchi"),
            inchikey=_field(row, "InChIKey", "inchikey"),
            measured_log_s_mol_l=float(_field(row, "Solubility", "logS", "measured_log_s_mol_l")),
            raw_fields={str(key): "" if value is None else str(value) for key, value in row.items()},
        )
    except (TypeError, ValueError) as exc:
        raise MOLDISC015Error("AqSolDB C-2545 numeric identity is invalid") from exc


def validate_aqsoldb_record(record: AqSolDBRecord) -> None:
    expected = {
        "record_id": AQSOLDB_RECORD_ID,
        "name": AQSOLDB_NAME,
        "raw_smiles": AQSOLDB_RAW_SMILES,
        "inchi": AQSOLDB_INCHI,
        "inchikey": AQSOLDB_INCHIKEY,
        "formula": AQSOLDB_FORMULA,
        "connectivity_block": AQSOLDB_CONNECTIVITY_BLOCK,
        "measured_log_s_mol_l": AQSOLDB_MEASURED_LOG_S,
    }
    actual = {key: getattr(record, key) for key in expected if key != "formula" and key != "connectivity_block"}
    actual.update({"formula": record.formula, "connectivity_block": record.connectivity_block})
    if actual != expected or record.stereochemistry_specified:
        raise MOLDISC015Error("AqSolDB C-2545 identity drifted from the frozen source record")


def alias_identity_compatible(*, name: str, formula: str, connectivity_block: str) -> bool:
    """Require structure identity; names and substring aliases are never enough."""
    return formula == AQSOLDB_FORMULA and connectivity_block == AQSOLDB_CONNECTIVITY_BLOCK


def measurement_transfer_decision(
    *,
    resolved_source_inchikey: str | None,
    resolved_source_canonical_isomeric_smiles: str | None,
    source_delta_both_inchikey: str = SOURCE_DELTA_BOTH_INCHIKEY,
    source_delta_both_canonical_isomeric_smiles: str | None = None,
    measured_record_attribution: bool = False,
) -> dict[str, bool]:
    full_match = resolved_source_inchikey == source_delta_both_inchikey
    canonical_match = (
        source_delta_both_canonical_isomeric_smiles is not None
        and resolved_source_canonical_isomeric_smiles == source_delta_both_canonical_isomeric_smiles
    )
    allowed = bool(full_match and canonical_match and measured_record_attribution)
    return {
        "same_connectivity": inchikey_connectivity_block(resolved_source_inchikey) == SOURCE_DELTA_BOTH_CONNECTIVITY_BLOCK
        if resolved_source_inchikey and "-" in resolved_source_inchikey else False,
        "exact_stereo_identity": bool(full_match and canonical_match),
        "full_inchikey_match": full_match,
        "measurement_transfer_allowed": allowed,
    }


def classify_resolution(
    *,
    record_recoverable: bool,
    connectivity_traceable: bool,
    measurement_traceable: bool,
    attributable_stereochemical_candidates: tuple[Mapping[str, Any], ...] = (),
) -> str:
    if not record_recoverable:
        return SOURCE_RECORD_NOT_RECOVERABLE
    if len(attributable_stereochemical_candidates) > 1:
        return CONFLICTING_SOURCE_IDENTITIES
    if attributable_stereochemical_candidates and attributable_stereochemical_candidates[0].get("exact_identity") is True:
        return RESOLVED_EXACT_STEREOCHEMICAL_IDENTITY
    if connectivity_traceable and measurement_traceable:
        return UNRESOLVED_SOURCE_STEREOCHEMISTRY
    return SOURCE_RECORD_NOT_RECOVERABLE


@dataclass(frozen=True)
class SupportingInformationArtifact:
    recovered: bool
    source_url: str | None
    publisher: str | None
    filename: str | None
    transport_sha256: str | None
    file_size_bytes: int | None
    retrieval_date: str | None
    publication_doi: str
    transport_url: str | None = None
    matched_record: dict[str, Any] | None = None
    upstream_original_source: dict[str, Any] | None = None
    rejected_identity_candidates: tuple[dict[str, Any], ...] = ()
    temporary_path: str | None = None

    @classmethod
    def from_json(cls, path: str | Path) -> "SupportingInformationArtifact":
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MOLDISC015Error(f"could not load supporting-information manifest: {path}") from exc
        allowed = set(cls.__dataclass_fields__)
        data = {key: value for key, value in payload.items() if key in allowed}
        data["rejected_identity_candidates"] = tuple(data.get("rejected_identity_candidates") or ())
        return cls(**data)

    def verify_artifact(self) -> None:
        if not self.recovered:
            return
        if not self.source_url or not self.publisher or not self.filename or not self.transport_sha256 or self.file_size_bytes is None:
            raise MOLDISC015Error("recovered supporting information lacks immutable transport metadata")
        if len(self.transport_sha256) != 64:
            raise MOLDISC015Error("supporting-information SHA256 is invalid")
        if self.publication_doi != DATASET_C_REFERENCE_DOI:
            raise MOLDISC015Error("supporting information is not attributable to the frozen publication")
        if self.temporary_path:
            path = Path(self.temporary_path)
            if (
                not path.is_file()
                or path.stat().st_size != self.file_size_bytes
                or sha256_file(path).casefold() != self.transport_sha256.casefold()
            ):
                raise MOLDISC015Error("supporting-information transport artifact hash or size drifted")

    def scientific_payload(self) -> dict[str, Any]:
        return {
            "recovered": self.recovered,
            "source_url": self.source_url,
            "transport_url": self.transport_url,
            "publisher": self.publisher,
            "filename": self.filename,
            "transport_sha256": self.transport_sha256,
            "file_size_bytes": self.file_size_bytes,
            "publication_doi": self.publication_doi,
            "matched_record": self.matched_record,
            "upstream_original_source": self.upstream_original_source,
            "rejected_identity_candidates": list(self.rejected_identity_candidates),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.scientific_payload(), "retrieval_date": self.retrieval_date, "temporary_path": self.temporary_path}


@dataclass(frozen=True)
class SourceTrace:
    aqsoldb_record: AqSolDBRecord
    dataset_c_identity: dict[str, Any]
    raevsky_publication: dict[str, Any]
    supporting_information: SupportingInformationArtifact
    provenance_chain: tuple[dict[str, Any], ...]

    def scientific_payload(self) -> dict[str, Any]:
        return {
            "aqsoldb_record": self.aqsoldb_record.to_dict(),
            "dataset_c_identity": self.dataset_c_identity,
            "raevsky_publication": self.raevsky_publication,
            "supporting_information": self.supporting_information.scientific_payload(),
            "provenance_chain": list(self.provenance_chain),
        }

    @property
    def scientific_hash(self) -> str:
        return sha256_json(self.scientific_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.scientific_payload(), "supporting_information": self.supporting_information.to_dict(), "scientific_hash": self.scientific_hash}


@dataclass(frozen=True)
class IdentityResolution:
    status: str
    formula: str
    connectivity_block: str
    source_stereochemistry_specified: bool
    source_record_recoverable: bool
    measurement_traceable: bool
    matched_supporting_record: dict[str, Any] | None
    measurement_transfer: dict[str, bool]
    rejected_identity_candidates: tuple[dict[str, Any], ...] = ()

    def scientific_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "formula": self.formula,
            "connectivity_block": self.connectivity_block,
            "source_stereochemistry_specified": self.source_stereochemistry_specified,
            "source_record_recoverable": self.source_record_recoverable,
            "measurement_traceable": self.measurement_traceable,
            "matched_supporting_record": self.matched_supporting_record,
            "measurement_transfer": self.measurement_transfer,
            "rejected_identity_candidates": list(self.rejected_identity_candidates),
        }

    @property
    def scientific_hash(self) -> str:
        return sha256_json(self.scientific_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.scientific_payload(), "scientific_hash": self.scientific_hash}


def _publication() -> dict[str, Any]:
    return {
        "authors": ["Raevsky OA", "Grigor'ev VY", "Polianczyk DE", "Raevskaja OE", "Dearden JC"],
        "title": "Calculation of aqueous solubility of crystalline un-ionized organic chemicals and drugs based on structural similarity and physicochemical descriptors",
        "journal": "J Chem Inf Model",
        "year": 2014,
        "volume": "54",
        "pages": "683-691",
        "doi": DATASET_C_REFERENCE_DOI,
    }


def load_program_config_v15(path: str | Path) -> dict[str, Any]:
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MOLDISC015Error(f"could not load MOLDISC-015 config: {path}") from exc
    if config.get("program_id") != PROGRAM_ID or config.get("program_version") != PROGRAM_VERSION:
        raise MOLDISC015Error("MOLDISC-015 program identity drifted")
    upstream = config.get("upstream") or {}
    if upstream.get("moldisc014_program_scientific_hash") != PARENT_MOLDISC014_HASH:
        raise MOLDISC015Error("MOLDISC-014 parent hash drifted")
    if upstream.get("source_record_id") != AQSOLDB_RECORD_ID or upstream.get("source_inchikey") != AQSOLDB_INCHIKEY:
        raise MOLDISC015Error("AqSolDB source identity drifted")
    lineage = config.get("immutable_aqsoldb_lineage") or {}
    if (
        lineage.get("source_commit") != AQSOLDB_SOURCE_COMMIT
        or lineage.get("source_blob_sha") != AQSOLDB_SOURCE_BLOB_SHA
        or lineage.get("parsed_source_hash") != AQSOLDB_PARSED_SOURCE_HASH
        or lineage.get("source_path") != "data/dataset-C.csv"
    ):
        raise MOLDISC015Error("immutable AqSolDB lineage drifted")
    if (config.get("dataset_c_reference") or {}).get("doi") != DATASET_C_REFERENCE_DOI:
        raise MOLDISC015Error("dataset-C reference drifted")
    if tuple(config.get("resolution_statuses") or ()) != RESOLUTION_STATUSES:
        raise MOLDISC015Error("resolution statuses drifted")
    boundaries = config.get("boundaries") or {}
    for key in ("generation_executed", "docking_executed", "esol_executed", "candidate_selection_executed", "vina_used", "aqsoldb_modified", "retrospective_stereo_borrowing_allowed", "biological_properties_imported", "measurement_transfer_initial"):
        if boundaries.get(key) is not False:
            raise MOLDISC015Error(f"MOLDISC-015 boundary drifted: {key}")
    if boundaries.get("measurement_transfer_requires_exact_full_identity") is not True:
        raise MOLDISC015Error("measurement-transfer boundary drifted")
    return config


def build_source_trace(
    *,
    aqsoldb_record: AqSolDBRecord,
    dataset_c_identity: Mapping[str, Any],
    supporting_information: SupportingInformationArtifact,
) -> SourceTrace:
    validate_aqsoldb_record(aqsoldb_record)
    supporting_information.verify_artifact()
    if dataset_c_identity.get("readme_mapping") != "3. dataset-C.csv [3]":
        raise MOLDISC015Error("dataset-C README mapping is not preserved")
    rejected = tuple(supporting_information.rejected_identity_candidates)
    chain = (
        {"source_type": "AQSOLDB_RECORD", "locator": "data/dataset-C.csv", "identifier": "C-2545", "claim_supported": "measured logS and raw identity record", "identity_evidence": "exact record ID plus formula/connectivity fields"},
        {"source_type": "DATASET_C_REFERENCE", "locator": "AqSolDB README line 56: 3. dataset-C.csv [3]", "identifier": "reference [3]", "claim_supported": "dataset-C provenance", "identity_evidence": "frozen README mapping"},
        {"source_type": "PUBLICATION", "locator": "doi:10.1021/ci400692n", "identifier": "10.1021/ci400692n", "claim_supported": "dataset-C publication", "identity_evidence": "frozen citation metadata"},
    )
    return SourceTrace(
        aqsoldb_record=aqsoldb_record,
        dataset_c_identity=dict(dataset_c_identity),
        raevsky_publication=_publication(),
        supporting_information=supporting_information,
        provenance_chain=chain,
    )


def resolve_identity(source_trace: SourceTrace) -> IdentityResolution:
    record = source_trace.aqsoldb_record
    matched = source_trace.supporting_information.matched_record
    candidates = tuple(source_trace.supporting_information.rejected_identity_candidates)
    attributable: tuple[Mapping[str, Any], ...] = ()
    if matched:
        matched_formula = matched.get("formula")
        matched_key = matched.get("inchikey")
        exact = matched_formula == AQSOLDB_FORMULA and matched_key == AQSOLDB_INCHIKEY and bool(matched.get("stereochemistry_specified"))
        attributable = ({"exact_identity": exact},)
    status = classify_resolution(
        record_recoverable=True,
        connectivity_traceable=record.formula == AQSOLDB_FORMULA and record.connectivity_block == AQSOLDB_CONNECTIVITY_BLOCK,
        measurement_traceable=record.measured_log_s_mol_l == AQSOLDB_MEASURED_LOG_S,
        attributable_stereochemical_candidates=attributable,
    )
    transfer = measurement_transfer_decision(
        resolved_source_inchikey=matched.get("inchikey") if matched else None,
        resolved_source_canonical_isomeric_smiles=matched.get("canonical_isomeric_smiles") if matched else None,
        source_delta_both_canonical_isomeric_smiles=matched.get("canonical_isomeric_smiles") if matched and matched.get("inchikey") == SOURCE_DELTA_BOTH_INCHIKEY else None,
        measured_record_attribution=status == RESOLVED_EXACT_STEREOCHEMICAL_IDENTITY,
    )
    return IdentityResolution(
        status=status,
        formula=record.formula,
        connectivity_block=record.connectivity_block,
        source_stereochemistry_specified=record.stereochemistry_specified,
        source_record_recoverable=True,
        measurement_traceable=record.measured_log_s_mol_l == AQSOLDB_MEASURED_LOG_S,
        matched_supporting_record=matched,
        measurement_transfer=transfer,
        rejected_identity_candidates=candidates,
    )


def _scientific_config(config: Mapping[str, Any]) -> dict[str, Any]:
    return dict(config)


@dataclass(frozen=True)
class MOLDISC015Result:
    config_hash: str
    source_trace: SourceTrace
    identity_resolution: IdentityResolution
    program_scientific_hash: str

    @property
    def source_trace_hash(self) -> str:
        return self.source_trace.scientific_hash

    @property
    def identity_resolution_hash(self) -> str:
        return self.identity_resolution.scientific_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": PROGRAM_ID,
            "program_version": PROGRAM_VERSION,
            "config_hash": self.config_hash,
            "source_trace_hash": self.source_trace_hash,
            "identity_resolution_hash": self.identity_resolution_hash,
            "program_scientific_hash": self.program_scientific_hash,
            "source_trace": self.source_trace.to_dict(),
            "identity_resolution": self.identity_resolution.to_dict(),
            "generation_executed": False,
            "docking_executed": False,
            "esol_executed": False,
            "candidate_selection_executed": False,
            "vina_used": False,
            "aqsoldb_modified": False,
        }


def run_moldisc_015(
    *,
    config_path: str | Path,
    aqsoldb_csv_path: str | Path,
    dataset_c_readme_path: str | Path,
    output_root: str | Path,
    supporting_information_manifest_path: str | Path | None = None,
) -> MOLDISC015Result:
    config = load_program_config_v15(config_path)
    record = parse_aqsoldb_csv(aqsoldb_csv_path)
    readme_bytes = Path(dataset_c_readme_path).read_bytes()
    readme_text = readme_bytes.decode("utf-8", errors="replace")
    mapping = "3. dataset-C.csv [3]"
    if mapping not in readme_text:
        raise MOLDISC015Error("AqSolDB README does not map dataset-C.csv to reference [3]")
    if supporting_information_manifest_path:
        supporting = SupportingInformationArtifact.from_json(supporting_information_manifest_path)
    else:
        supporting = SupportingInformationArtifact(
            recovered=False,
            source_url=None,
            publisher=None,
            filename=None,
            transport_sha256=None,
            file_size_bytes=None,
            retrieval_date=None,
            publication_doi=DATASET_C_REFERENCE_DOI,
        )
    trace = build_source_trace(
        aqsoldb_record=record,
        dataset_c_identity={
            "source_path": "data/dataset-C.csv",
            "readme_mapping": mapping,
            "readme_sha256": hashlib.sha256(readme_bytes).hexdigest(),
            "readme_size_bytes": len(readme_bytes),
        },
        supporting_information=supporting,
    )
    resolution = resolve_identity(trace)
    config_hash = sha256_json(_scientific_config(config))
    program_hash = sha256_json({
        "program_id": PROGRAM_ID,
        "program_version": PROGRAM_VERSION,
        "config_hash": config_hash,
        "source_trace_hash": trace.scientific_hash,
        "identity_resolution_hash": resolution.scientific_hash,
        "generation_executed": False,
        "docking_executed": False,
        "esol_executed": False,
        "candidate_selection_executed": False,
        "vina_used": False,
        "aqsoldb_modified": False,
    })
    result = MOLDISC015Result(config_hash, trace, resolution, program_hash)
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=False)
    (root / "source_trace.json").write_text(json.dumps(trace.to_dict(), indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (root / "identity_resolution.json").write_text(json.dumps(resolution.to_dict(), indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (root / "program_manifest.json").write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (root / "program_report.md").write_text(_markdown(result), encoding="utf-8")
    return result


def _markdown(result: MOLDISC015Result) -> str:
    resolution = result.identity_resolution
    return "\n".join([
        "# MOLDISC-015 — C-2545 source-provenance and stereochemistry resolution",
        "",
        f"- status: `{resolution.status}`",
        f"- source trace hash: `{result.source_trace_hash}`",
        f"- identity-resolution hash: `{result.identity_resolution_hash}`",
        f"- program hash: `{result.program_scientific_hash}`",
        "- generation/docking/ESOL/selection: `NO/NO/NO/NO`",
        "",
        "The AqSolDB measurement remains attached to the source record. Connectivity identity alone does not establish stereochemical identity or authorize measurement transfer.",
        "",
    ])


__all__ = [
    "AQSOLDB_CANONICAL_SMILES",
    "AQSOLDB_CONNECTIVITY_BLOCK",
    "AQSOLDB_FORMULA",
    "AQSOLDB_INCHI",
    "AQSOLDB_INCHIKEY",
    "AQSOLDB_MEASURED_LOG_S",
    "AQSOLDB_NAME",
    "AQSOLDB_RAW_SMILES",
    "AQSOLDB_RECORD_ID",
    "CONFLICTING_SOURCE_IDENTITIES",
    "DATASET_C_REFERENCE_DOI",
    "IdentityResolution",
    "MOLDISC015Error",
    "MOLDISC015Result",
    "PARENT_MOLDISC014_HASH",
    "RESOLVED_EXACT_STEREOCHEMICAL_IDENTITY",
    "SOURCE_DELTA_BOTH_INCHIKEY",
    "SOURCE_RECORD_NOT_RECOVERABLE",
    "SourceTrace",
    "SupportingInformationArtifact",
    "UNRESOLVED_SOURCE_STEREOCHEMISTRY",
    "alias_identity_compatible",
    "build_source_trace",
    "classify_resolution",
    "derive_formula_from_inchi",
    "inchikey_connectivity_block",
    "inchi_stereochemistry_specified",
    "load_program_config_v15",
    "measurement_transfer_decision",
    "parse_aqsoldb_csv",
    "resolve_identity",
    "run_moldisc_015",
    "validate_aqsoldb_record",
]
