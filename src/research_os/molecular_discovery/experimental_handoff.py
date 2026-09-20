"""Deterministic human/laboratory handoff for the frozen BIOEXP-001 panel.

This module produces an experiment request, identity artifacts and a future
result boundary.  It does not execute an experiment, create evidence, rank
the panel, or open molecular generation.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from research_os.core.hashing import sha256_file, sha256_json


HANDOFF_VERSION = "0.2"
SCHEMA_VERSION = "research-os.biolab.experimental-handoff.v0.2"
EXPERIMENT_ID = "BIOEXP-001-SOLUBILITY-2X2"
EXPERIMENT_FAMILY = "SOLUBILITY"
MEASUREMENT_NAME = "aqueous solubility"
PANEL_KEYS = ("A0B0", "A1B0", "A0B1", "A1B1")
PROTOCOL_STATUSES = (
    "AWAITING_EXTERNAL_PROTOCOL_OR_QUOTE",
    "PROPOSED",
    "FROZEN",
)
RESULT_QUALIFIERS = (
    "EXACT",
    "LESS_THAN",
    "GREATER_THAN",
    "NOT_QUANTIFIABLE",
    "FAILED",
)
UNKNOWN_PROTOCOL_FIELDS = (
    "measurement_method",
    "equilibrium_or_kinetic",
    "temperature",
    "pH",
    "medium",
    "buffer",
    "ionic_strength_if_applicable",
    "compound_form",
    "target_concentration_range_if_applicable",
    "units",
    "replicate_policy",
    "sample_purity_requirement",
)
REQUESTED_FROM_LAB = (
    *UNKNOWN_PROTOCOL_FIELDS,
    "required_sample_amount",
    "analytical_quantification_method",
    "lod_loq_if_applicable",
    "raw_data_format",
    "protocol_identifier_and_hash_after_freeze",
    "batch_identity_and_chain_of_custody",
)
COMPOUND_COLUMNS = (
    "panel_key",
    "compound_id",
    "variant_id",
    "factor_a",
    "factor_b",
    "isomeric_smiles",
    "inchikey",
    "formula",
    "heavy_atom_count",
    "source_measurement_transfer_allowed",
)
HANDOFF_ARTIFACTS = (
    "README.md",
    "experiment_request.json",
    "compound_identity_table.csv",
    "panel.sdf",
    "laboratory_result_template.csv",
    "laboratory_result_schema.json",
    "manifest.json",
)


class ExperimentalHandoffError(RuntimeError):
    """Fail-closed handoff generation or validation error."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExperimentalHandoffError(f"could not load JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ExperimentalHandoffError(f"JSON object required: {path}")
    return value


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def _write_json(path: Path, value: Any) -> None:
    _write_text(path, json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def _rdkit() -> tuple[Any, Any, Any]:
    try:
        from rdkit import Chem
        from rdkit.Chem import rdDepictor, rdMolDescriptors
    except ImportError as exc:  # pragma: no cover - exercised in minimal installs
        raise ExperimentalHandoffError(
            "RDKit is required to generate SDF, MOL and SVG identity artifacts"
        ) from exc
    return Chem, rdDepictor, rdMolDescriptors


def _safe_relative_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    resolved_root = root.resolve()
    if resolved_root not in candidate.parents:
        raise ExperimentalHandoffError(f"compound path escapes source package: {relative}")
    return candidate


def _validate_identity(record: Mapping[str, Any]) -> Any:
    Chem, _, rdMolDescriptors = _rdkit()
    compound_id = str(record.get("candidate_id", ""))
    panel_key = str(record.get("panel_key", ""))
    smiles = record.get("canonical_isomeric_smiles")
    if not isinstance(smiles, str) or not smiles:
        raise ExperimentalHandoffError(f"{compound_id}: canonical isomeric SMILES is required")
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise ExperimentalHandoffError(f"{compound_id}: isomeric SMILES could not be parsed")
    derived_inchikey = Chem.MolToInchiKey(molecule)
    expected_inchikey = str(record.get("inchikey", ""))
    if derived_inchikey != expected_inchikey:
        raise ExperimentalHandoffError(
            f"{compound_id} ({panel_key}): expected InChIKey {expected_inchikey}; "
            f"derived {derived_inchikey}"
        )
    derived_formula = rdMolDescriptors.CalcMolFormula(molecule)
    expected_formula = str(record.get("formula", ""))
    if derived_formula != expected_formula:
        raise ExperimentalHandoffError(
            f"{compound_id} ({panel_key}): expected formula {expected_formula}; "
            f"derived {derived_formula}"
        )
    derived_heavy_atoms = int(molecule.GetNumHeavyAtoms())
    expected_heavy_atoms = int(record.get("heavy_atom_count", -1))
    if derived_heavy_atoms != expected_heavy_atoms:
        raise ExperimentalHandoffError(
            f"{compound_id} ({panel_key}): expected heavy_atom_count {expected_heavy_atoms}; "
            f"derived {derived_heavy_atoms}"
        )
    if record.get("source_measurement_transfer_allowed") is not False:
        raise ExperimentalHandoffError(
            f"{compound_id} ({panel_key}): source measurement transfer must remain false"
        )
    return molecule


def load_frozen_panel(source_package: str | Path) -> list[dict[str, Any]]:
    """Load and validate exactly the four canonical BIOEXP-001 identities."""

    root = Path(source_package)
    manifest = _load_json(root / "panel_manifest.json")
    if manifest.get("panel_id") != EXPERIMENT_ID or manifest.get("member_count") != 4:
        raise ExperimentalHandoffError("BIOEXP-001 panel manifest identity drifted")
    members = manifest.get("members")
    if not isinstance(members, list) or [item.get("panel_key") for item in members] != list(PANEL_KEYS):
        raise ExperimentalHandoffError("BIOEXP-001 panel membership/order drifted")

    records: list[dict[str, Any]] = []
    for member in members:
        if not isinstance(member, Mapping):
            raise ExperimentalHandoffError("BIOEXP-001 panel member must be an object")
        compound_path = _safe_relative_path(root, str(member.get("compound_file", "")))
        record = _load_json(compound_path)
        for key in ("panel_key", "candidate_id", "variant_id", "factor_a", "factor_b"):
            if record.get(key) != member.get(key):
                raise ExperimentalHandoffError(f"BIOEXP-001 panel drifted: {member.get('panel_key')}/{key}")
        _validate_identity(record)
        records.append(record)
    return records


def protocol_freeze_gate(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return the fail-closed gate for a real result submission."""

    if result.get("actual_experiment") is not True:
        return {
            "allowed": False,
            "code": "ACTUAL_EXPERIMENT_REQUIRED",
            "reason": "only an actual external experiment can be considered for E4",
        }
    if result.get("protocol_status") != "FROZEN":
        return {
            "allowed": False,
            "code": "PROTOCOL_NOT_FROZEN",
            "reason": "a real result cannot be ingested before human protocol review and freeze",
        }
    if not isinstance(result.get("protocol_id"), str) or not result["protocol_id"].strip():
        return {
            "allowed": False,
            "code": "PROTOCOL_IDENTITY_REQUIRED",
            "reason": "a frozen protocol identifier is required",
        }
    protocol_hash = result.get("protocol_hash")
    if not isinstance(protocol_hash, str) or len(protocol_hash) != 64 or any(
        character not in "0123456789abcdef" for character in protocol_hash.lower()
    ):
        return {
            "allowed": False,
            "code": "PROTOCOL_HASH_REQUIRED",
            "reason": "a frozen protocol SHA-256 hash is required",
        }
    return {"allowed": True, "code": "PROTOCOL_FROZEN", "reason": "protocol gate passed"}


def is_synthetic_result(result: Mapping[str, Any]) -> bool:
    provenance = result.get("provenance")
    provenance_classification = provenance.get("classification") if isinstance(provenance, Mapping) else None
    markers = (
        result.get("fixture_classification"),
        result.get("evidence_classification"),
        result.get("sample_identity_method"),
        provenance_classification,
    )
    return bool(result.get("synthetic") is True or any(str(marker) == "TEST_SYNTHETIC" for marker in markers))


def _result_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "research-os.biolab.experimental-handoff.result.v0.2",
        "title": "BIOEXP-001 laboratory result package",
        "description": "Future result contract. It is not evidence and cannot bypass the protocol freeze gate.",
        "type": "object",
        "additionalProperties": False,
        "required": ["experiment_id", "family", "protocol_status", "actual_experiment", "results"],
        "properties": {
            "experiment_id": {"const": EXPERIMENT_ID},
            "family": {"const": EXPERIMENT_FAMILY},
            "protocol_status": {"enum": list(PROTOCOL_STATUSES)},
            "protocol_id": {"type": ["string", "null"]},
            "protocol_hash": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"},
            "actual_experiment": {"type": "boolean"},
            "laboratory": {"type": ["string", "null"]},
            "source": {"type": ["string", "null"]},
            "report_id": {"type": ["string", "null"]},
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "compound_id",
                        "panel_key",
                        "batch_id",
                        "measurement",
                        "units",
                        "replicates",
                    ],
                    "properties": {
                        "compound_id": {"type": "string", "minLength": 1},
                        "panel_key": {"enum": list(PANEL_KEYS)},
                        "batch_id": {"type": "string", "minLength": 1},
                        "measurement": {},
                        "units": {"type": "string", "minLength": 1},
                        "qualifier": {"enum": list(RESULT_QUALIFIERS)},
                        "uncertainty": {},
                        "replicates": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "required": ["value", "qualifier"],
                                "properties": {
                                    "value": {},
                                    "qualifier": {"enum": list(RESULT_QUALIFIERS)},
                                    "uncertainty": {},
                                },
                            },
                        },
                        "conditions": {"type": "object"},
                        "notes": {"type": "string"},
                    },
                },
            },
        },
        "allOf": [
            {
                "if": {
                    "properties": {"actual_experiment": {"const": True}},
                    "required": ["actual_experiment"],
                },
                "then": {
                    "required": [
                        "protocol_id",
                        "protocol_hash",
                        "laboratory",
                        "source",
                        "report_id",
                    ],
                    "properties": {"protocol_status": {"const": "FROZEN"}},
                },
            }
        ],
    }


def _identity_rows(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "panel_key": record["panel_key"],
            "compound_id": record["candidate_id"],
            "variant_id": record["variant_id"],
            "factor_a": record["factor_a"],
            "factor_b": record["factor_b"],
            "isomeric_smiles": record["canonical_isomeric_smiles"],
            "inchikey": record["inchikey"],
            "formula": record["formula"],
            "heavy_atom_count": record["heavy_atom_count"],
            "source_measurement_transfer_allowed": record["source_measurement_transfer_allowed"],
        }
        for record in records
    ]


def _build_request(source_package: Path, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    source_request = _load_json(source_package / "BIOEXP-001" / "experiment_request.json")
    missing = _load_json(source_package / "BIOEXP-001" / "missing_protocol_fields.json")
    unknown = {field: source_request.get(field) for field in UNKNOWN_PROTOCOL_FIELDS}
    return {
        "schema_version": SCHEMA_VERSION,
        "handoff_version": HANDOFF_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "family": EXPERIMENT_FAMILY,
        "measurement_name": MEASUREMENT_NAME,
        "actual_experiment": False,
        "protocol_status": source_request.get("status", "AWAITING_EXTERNAL_PROTOCOL_OR_QUOTE"),
        "experimental_handoff_ready": True,
        "biolab_package_ready": True,
        "engagement_type": "SCIENTIFIC_COLLABORATION",
        "scientific_question": "Measure aqueous solubility for the same frozen 2x2 panel under one pre-declared laboratory protocol.",
        "purpose": [
            "estimate the factor A effect",
            "estimate the factor B effect",
            "describe the A×B interaction",
        ],
        "known": {
            "panel_membership": [record["panel_key"] for record in records],
            "compound_identity": "exact isomeric identity, formula and InChIKey per panel member",
            "evidence_boundary": "EXPERIMENT_REQUEST, not E4 evidence",
            "generation_gate": "NEXT_GENERATION_ALLOWED=NO",
        },
        "unknown": {
            "protocol_fields": unknown,
            "missing_protocol_fields": list(missing.get("missing_fields", UNKNOWN_PROTOCOL_FIELDS)),
        },
        "requested_from_lab": list(REQUESTED_FROM_LAB),
        "requested_material": {
            "quantity_options_per_compound": ["25 mg", "50 mg"],
            "preferred_purity": ">=95%",
            "optional_purity": ">=98%",
        },
        "analytical_characterization_requested": ["HPLC/equivalent", "MS/LC-MS", "NMR"],
        "panel": [
            {
                "panel_key": record["panel_key"],
                "compound_id": record["candidate_id"],
                "variant_id": record["variant_id"],
                "factor_a": record["factor_a"],
                "factor_b": record["factor_b"],
                "isomeric_smiles": record["canonical_isomeric_smiles"],
                "inchikey": record["inchikey"],
                "formula": record["formula"],
            }
            for record in records
        ],
        "e4_boundary": {
            "evidence_class": "EXPERIMENT_REQUEST",
            "e4_created": False,
            "interpret_as_e4": False,
            "real_experiment_executed": False,
        },
    }


def _readme(records: Sequence[Mapping[str, Any]]) -> str:
    rows = "\n".join(
        f"| {record['panel_key']} | {record['factor_a']} | {record['factor_b']} | "
        f"`{record['candidate_id']}` | `{record['inchikey']}` | `{record['formula']}` |"
        for record in records
    )
    unknown = "\n".join(f"- `{field}`" for field in UNKNOWN_PROTOCOL_FIELDS)
    return f"""# BIOEXP-001 — Experimental Collaboration Package

## Scientific question

Measure the aqueous solubility of the same frozen 2×2 panel under one
pre-declared laboratory protocol.

## Purpose

The experiment is designed to quantify the factor A effect, the factor B
effect, and their interaction. No selection decision is part of this package.

## Frozen panel

| Cell | Factor A | Factor B | Compound | InChIKey | Formula |
| --- | --- | --- | --- | --- | --- |
{rows}

```text
              B0                 B1
         ------------------------------
A0       A0B0               A0B1
A1       A1B0               A1B1
```

Exact isomeric SMILES and machine-readable identities are in
`experiment_request.json`, `compound_identity_table.csv`, `panel.sdf`, and
the individual MOL files.

## Requested material and characterization

Please quote 25 mg and 50 mg options per compound. Preferred purity is >=95%;
>=98% is optional. Preferred characterization is HPLC/equivalent, MS/LC-MS,
and NMR, with attributable batch and report traceability.

## Protocol status

`AWAITING_EXTERNAL_PROTOCOL_OR_QUOTE`

The following conditions are intentionally not frozen:

{unknown}

The laboratory should propose the method, protocol identifier, conditions,
replicate policy, sample requirements, quantification limits and raw-data or
official-report format. Human review must freeze the protocol before any real
result is submitted.

## Result boundary

**NO EXPERIMENTAL RESULT EXISTS YET.**

**THIS PACKAGE MUST NOT BE INTERPRETED AS E4 EVIDENCE.**

This is an `EXPERIMENT_REQUEST` only. `TEST_SYNTHETIC` fixtures are useful for
pipeline tests but cannot create E4. `NEXT_GENERATION_ALLOWED=NO` remains in
force, and no selection or ranking is declared.
"""


def _prepared_molecule(record: Mapping[str, Any]) -> Any:
    Chem, rdDepictor, _ = _rdkit()
    molecule = Chem.MolFromSmiles(str(record["canonical_isomeric_smiles"]))
    if molecule is None:  # defensive; load_frozen_panel already validates this
        raise ExperimentalHandoffError(f"could not prepare {record['candidate_id']}")
    rdDepictor.Compute2DCoords(molecule, canonOrient=True)
    molecule.SetProp("_Name", f"{record['panel_key']} {record['candidate_id']}")
    return molecule


def _write_mol_files(output_dir: Path, records: Sequence[Mapping[str, Any]]) -> None:
    Chem, _, _ = _rdkit()
    compounds_dir = output_dir / "compounds"
    structures_dir = output_dir / "structures"
    for record in records:
        molecule = _prepared_molecule(record)
        mol_block = Chem.MolToMolBlock(molecule, kekulize=False, includeStereo=True)
        _write_text(compounds_dir / f"{record['panel_key']}.mol", mol_block.rstrip() + "\n")
        from rdkit.Chem.Draw import rdMolDraw2D

        drawer = rdMolDraw2D.MolDraw2DSVG(640, 480)
        drawer.drawOptions().clearBackground = False
        drawer.DrawMolecule(molecule)
        drawer.FinishDrawing()
        _write_text(structures_dir / f"{record['panel_key']}.svg", drawer.GetDrawingText())


def _write_sdf(output_dir: Path, records: Sequence[Mapping[str, Any]]) -> None:
    Chem, _, _ = _rdkit()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "panel.sdf"
    writer = Chem.SDWriter(str(path))
    if writer is None:  # pragma: no cover - RDKit always returns a writer or raises
        raise ExperimentalHandoffError("could not create panel.sdf writer")
    properties = (
        ("PANEL_KEY", "panel_key"),
        ("COMPOUND_ID", "candidate_id"),
        ("VARIANT_ID", "variant_id"),
        ("FACTOR_A", "factor_a"),
        ("FACTOR_B", "factor_b"),
        ("ISOMERIC_SMILES", "canonical_isomeric_smiles"),
        ("INCHIKEY", "inchikey"),
        ("FORMULA", "formula"),
    )
    try:
        for record in records:
            molecule = _prepared_molecule(record)
            for property_name, record_key in properties:
                molecule.SetProp(property_name, str(record[record_key]))
            writer.write(molecule)
    finally:
        writer.close()
    # RDKit emits a harmless trailing space on SD property headers.  Remove it
    # so the canonical artifact also satisfies repository whitespace checks.
    normalized = "\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()) + "\n"
    _write_text(path, normalized)


def _write_identity_csv(output_dir: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path = output_dir / "compound_identity_table.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COMPOUND_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(_identity_rows(records))


def _write_result_template(output_dir: Path, records: Sequence[Mapping[str, Any]]) -> None:
    fields = (
        "experiment_id",
        "compound_id",
        "panel_key",
        "batch_id",
        "replicate_id",
        "measurement_value",
        "measurement_units",
        "qualifier",
        "uncertainty",
        "temperature_c",
        "pH",
        "medium",
        "method",
        "protocol_id",
        "protocol_hash",
        "protocol_status",
        "laboratory",
        "source",
        "report_id",
        "notes",
    )
    rows = [
        {
            "experiment_id": EXPERIMENT_ID,
            "compound_id": record["candidate_id"],
            "panel_key": record["panel_key"],
        }
        for record in records
    ]
    path = output_dir / "laboratory_result_template.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _canonical_inputs(source_package: Path, repo_root: Path) -> list[dict[str, str]]:
    paths = [
        source_package / "panel_manifest.json",
        source_package / "compound_identity_table.csv",
        *sorted((source_package / "compounds").glob("*.json")),
        source_package / "BIOEXP-001" / "experiment_request.json",
        source_package / "BIOEXP-001" / "missing_protocol_fields.json",
        repo_root / "programs" / "moldisc-019-experimental-bridge" / "program.json",
    ]
    inputs: list[dict[str, str]] = []
    for path in paths:
        if not path.is_file():
            raise ExperimentalHandoffError(f"canonical input not found: {path}")
        inputs.append(
            {
                "path": path.relative_to(repo_root).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    return inputs


def _write_manifest(output_dir: Path, source_package: Path, repo_root: Path) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    for path in sorted(item for item in output_dir.rglob("*") if item.is_file() and item.name != "manifest.json"):
        relative = path.relative_to(output_dir).as_posix()
        artifacts.append({"path": relative, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    artifact_hashes = {item["path"]: item["sha256"] for item in artifacts}
    inputs = _canonical_inputs(source_package, repo_root)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "handoff_version": HANDOFF_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "evidence_classification": "EXPERIMENT_REQUEST",
        "actual_experiment": False,
        "e4_created": False,
        "experimental_handoff_ready": True,
        "biolab_package_ready": True,
        "next_generation_allowed": False,
        "generator": "research_os.molecular_discovery.experimental_handoff",
        "canonical_inputs": inputs,
        "canonical_input_hash": sha256_json(inputs),
        "artifacts": artifacts,
        "package_hash": sha256_json(artifact_hashes),
        "manifest_scope": "manifest.json is excluded from package_hash and artifacts",
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def generate_handoff(
    source_package: str | Path,
    output_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Generate the deterministic BIOEXP-001 handoff package."""

    source = Path(source_package).resolve()
    repository = Path(repo_root).resolve() if repo_root else source.parent.parent.resolve()
    records = load_frozen_panel(source)
    destination = Path(output_dir).resolve() if output_dir else source / "BIOEXP-001" / "handoff"
    destination.mkdir(parents=True, exist_ok=True)

    _write_text(destination / "README.md", _readme(records))
    _write_json(destination / "experiment_request.json", _build_request(source, records))
    _write_identity_csv(destination, records)
    _write_sdf(destination, records)
    _write_mol_files(destination, records)
    _write_result_template(destination, records)
    _write_json(destination / "laboratory_result_schema.json", _result_schema())
    return _write_manifest(destination, source, repository)


def validate_handoff_manifest(handoff_dir: str | Path) -> dict[str, Any]:
    """Validate all generated artifact hashes without generating evidence."""

    root = Path(handoff_dir)
    manifest = _load_json(root / "manifest.json")
    actual: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "manifest.json"):
        actual[path.relative_to(root).as_posix()] = sha256_file(path)
    declared = {str(item["path"]): str(item["sha256"]) for item in manifest.get("artifacts", [])}
    if actual != declared:
        raise ExperimentalHandoffError("handoff manifest artifact hashes do not match")
    if manifest.get("actual_experiment") is not False or manifest.get("e4_created") is not False:
        raise ExperimentalHandoffError("handoff manifest crossed the experiment/evidence boundary")
    if manifest.get("experimental_handoff_ready") is not True or manifest.get("biolab_package_ready") is not True:
        raise ExperimentalHandoffError("handoff manifest is not marked ready")
    return manifest


__all__ = [
    "EXPERIMENT_FAMILY",
    "EXPERIMENT_ID",
    "ExperimentalHandoffError",
    "HANDOFF_VERSION",
    "PANEL_KEYS",
    "PROTOCOL_STATUSES",
    "RESULT_QUALIFIERS",
    "generate_handoff",
    "is_synthetic_result",
    "load_frozen_panel",
    "protocol_freeze_gate",
    "validate_handoff_manifest",
]
