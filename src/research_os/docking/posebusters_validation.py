from __future__ import annotations

import math
from typing import Any, Mapping

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from research_os.core.hashing import sha256_json
from research_os.docking import redocking as redocking_v11


PROTOCOL_ID = "research-os.posebusters.redock.v1.1"
POSEBUSTERS_VERSION = "0.6.5"
POSEBUSTERS_CONFIG = "redock"
POSEBUSTERS_REDOCK_CONFIG_GIT_BLOB_SHA1 = "8bcceebd7901e06759176d3a2b6b35965033464a"
SYMMETRY_MAX_MATCHES = 10000

REDOCK_001_PROTOCOL_ID = "research-os.redocking.v1.2"
REDOCK_001_SCIENTIFIC_RESULT_HASH = "4c24876d0a744f28b3ff4d2792102b708d9447bfd7dd35bdfa5aaf11be1bf16b"
REDOCK_002_PROTOCOL_ID = "research-os.redocking.holdout.v1.0"
REDOCK_002_SCIENTIFIC_RESULT_HASH = "8540d1acf507047af402013f9d9d5d6ad93c5ac63123b95ab2876a46ecabb00c"

INVALIDATED_V10_RUN_ID = 34541851196
INVALIDATED_V10_SCIENTIFIC_RESULT_HASH = "432a9ac17bc06a0709ecd897ae6c4955eedb3b37b8528803d5fff7a578564087"

_FLOAT_DIGITS = 12


def normalize_scalar(value: Any) -> bool | int | float | str | None:
    """Convert dataframe/numpy scalars to deterministic JSON-safe values."""

    if value is None:
        return None
    try:
        if bool(value is not value):  # NaN without importing numpy/pandas
            return None
    except Exception:
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return round(value, _FLOAT_DIGITS)
    if hasattr(value, "item"):
        try:
            return normalize_scalar(value.item())
        except Exception:
            pass
    return str(value)


def normalize_binary_results(row: Mapping[str, Any]) -> dict[str, bool | None]:
    """Normalize the default PoseBusters binary report to booleans/None."""

    normalized: dict[str, bool | None] = {}
    for raw_name in sorted(row):
        name = str(raw_name)
        value = normalize_scalar(row[raw_name])
        if value is True:
            normalized[name] = True
        elif value is False:
            normalized[name] = False
        else:
            normalized[name] = None
    return normalized


def classify_posebusters(binary_results: Mapping[str, bool | None]) -> dict[str, bool]:
    """Return official PB-valid and a localization-independent plausibility gate.

    ``pb_valid`` requires every official binary output from the PoseBusters
    ``redock`` configuration to pass. ``pb_plausible`` deliberately excludes
    only PoseBusters' RMSD binary so physical/chemical plausibility is not
    conflated with the independent Research OS same-frame localization endpoint.
    Missing/indeterminate values fail closed.
    """

    all_values = list(binary_results.values())
    non_rmsd_values = [
        value for name, value in binary_results.items() if "rmsd" not in name.lower()
    ]
    return {
        "pb_valid": bool(all_values) and all(value is True for value in all_values),
        "pb_plausible": bool(non_rmsd_values)
        and all(value is True for value in non_rmsd_values),
    }


def _heavy_isomeric_smiles(mol: Chem.Mol) -> str:
    heavy = redocking_v11._heavy_atom_copy(mol)
    return Chem.MolToSmiles(heavy, canonical=True, isomericSmiles=True)


def restore_docked_pose_chemistry(
    template: Chem.Mol,
    predicted: Chem.Mol,
) -> tuple[Chem.Mol, dict[str, Any]]:
    """Restore ligand chemistry stripped by PDBQT while preserving docked coordinates.

    AutoDock PDBQT does not retain the full SDF chemical representation and the
    Open Babel PDBQT->SDF round trip used for REDOCK evidence can lose non-polar
    hydrogens/bond-order information. PoseBusters treats those serialization
    losses as molecular identity defects. For redocking, ligand identity is
    already known before docking, so v1.1 takes chemistry from the independently
    generated ``starting_conformer.sdf`` and copies only the docked heavy-atom
    coordinates from ``pose_01.sdf``.

    No crystallographic coordinates are used for this mapping. No docked heavy
    atom is translated, rotated, fitted, minimized or otherwise moved. Existing
    stereochemical labels are cleared and reassigned from the docked 3D
    coordinates so the template cannot force a stereochemical PASS.
    """

    template_heavy = redocking_v11._heavy_atom_copy(template)
    predicted_heavy = redocking_v11._heavy_atom_copy(predicted)
    template_graph = redocking_v11._connectivity_graph(template)
    predicted_graph = redocking_v11._connectivity_graph(predicted)

    template_identity = Chem.MolToSmiles(template_graph, canonical=True, isomericSmiles=False)
    predicted_identity = Chem.MolToSmiles(predicted_graph, canonical=True, isomericSmiles=False)
    if template_identity != predicted_identity:
        raise ValueError("starting-conformer and docked heavy-atom connectivity differ")
    if template_heavy.GetNumAtoms() != predicted_heavy.GetNumAtoms():
        raise ValueError("starting-conformer and docked heavy-atom counts differ")

    matches = template_graph.GetSubstructMatches(
        predicted_graph,
        uniquify=False,
        useChirality=False,
        maxMatches=SYMMETRY_MAX_MATCHES,
    )
    if not matches:
        raise ValueError("no exact heavy-atom graph mapping for chemistry restoration")
    if len(matches) >= SYMMETRY_MAX_MATCHES:
        raise ValueError("chemistry-restoration symmetry mapping limit was reached")
    mapping = min(tuple(int(index) for index in match) for match in matches)

    restored = Chem.Mol(template_heavy)
    restored_conf = restored.GetConformer()
    predicted_conf = predicted_heavy.GetConformer()
    max_coordinate_delta = 0.0
    for predicted_index, template_index in enumerate(mapping):
        docked = predicted_conf.GetAtomPosition(predicted_index)
        restored_conf.SetAtomPosition(template_index, docked)
        copied = restored_conf.GetAtomPosition(template_index)
        delta = math.sqrt(
            (docked.x - copied.x) ** 2
            + (docked.y - copied.y) ** 2
            + (docked.z - copied.z) ** 2
        )
        max_coordinate_delta = max(max_coordinate_delta, delta)

    Chem.RemoveStereochemistry(restored)
    Chem.AssignAtomChiralTagsFromStructure(restored, confId=0, replaceExistingTags=True)
    Chem.AssignStereochemistryFrom3D(restored, confId=0, replaceExistingTags=True)
    Chem.AssignStereochemistry(restored, cleanIt=True, force=True)
    sanitize_status = Chem.SanitizeMol(restored, catchErrors=True)
    if sanitize_status != Chem.SanitizeFlags.SANITIZE_NONE:
        raise ValueError(f"chemistry-restored pose failed sanitization: {sanitize_status}")
    if max_coordinate_delta != 0.0:
        raise AssertionError("chemistry restoration moved a docked heavy atom")

    metadata = {
        "method": "starting-conformer chemistry + exact docked heavy-atom coordinates",
        "template_source": "starting_conformer.sdf",
        "predicted_coordinate_source": "pose_01.sdf",
        "crystal_coordinates_used_for_mapping": False,
        "rigid_fit_performed": False,
        "minimization_performed": False,
        "heavy_atoms": restored.GetNumAtoms(),
        "atom_mapping_predicted_to_template": list(mapping),
        "max_heavy_atom_coordinate_delta_angstrom": 0.0,
        "template_connectivity_identity": template_identity,
        "predicted_connectivity_identity": predicted_identity,
        "template_isomeric_smiles": _heavy_isomeric_smiles(template),
        "restored_isomeric_smiles": _heavy_isomeric_smiles(restored),
        "template_formula": rdMolDescriptors.CalcMolFormula(template_heavy),
        "restored_formula": rdMolDescriptors.CalcMolFormula(restored),
    }
    return restored, metadata


def build_case_record(
    *,
    benchmark_id: str,
    case_id: str,
    source_rmsd_angstrom: float | None,
    binary_results: Mapping[str, Any],
    representation_normalization: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_binary_results(binary_results)
    classification = classify_posebusters(normalized)
    source_rmsd = normalize_scalar(source_rmsd_angstrom)
    localized = isinstance(source_rmsd, (int, float)) and float(source_rmsd) <= 2.0
    return {
        "benchmark_id": benchmark_id,
        "case_id": case_id,
        "source_same_frame_pose_1_rmsd_angstrom": source_rmsd,
        "source_same_frame_rmsd_le_2_angstrom": localized,
        "representation_normalization": dict(representation_normalization or {}),
        "posebusters_binary_results": normalized,
        **classification,
        "localized_and_pb_plausible": localized and classification["pb_plausible"],
    }


def summarize_case_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    localized = sum(bool(record["source_same_frame_rmsd_le_2_angstrom"]) for record in records)
    plausible = sum(bool(record["pb_plausible"]) for record in records)
    pb_valid = sum(bool(record["pb_valid"]) for record in records)
    combined = sum(bool(record["localized_and_pb_plausible"]) for record in records)

    def fraction(count: int) -> float | None:
        return round(count / total, _FLOAT_DIGITS) if total else None

    return {
        "total_poses": total,
        "source_same_frame_rmsd_le_2_angstrom": {
            "count": localized,
            "denominator": total,
            "fraction": fraction(localized),
        },
        "pb_plausible": {
            "count": plausible,
            "denominator": total,
            "fraction": fraction(plausible),
        },
        "pb_valid": {
            "count": pb_valid,
            "denominator": total,
            "fraction": fraction(pb_valid),
        },
        "localized_and_pb_plausible": {
            "count": combined,
            "denominator": total,
            "fraction": fraction(combined),
        },
    }


def scientific_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    """Build the portable scientific identity for PoseBusters v1.1."""

    records = []
    for raw_record in report.get("records", []):
        record = dict(raw_record)
        records.append(
            {
                "benchmark_id": record.get("benchmark_id"),
                "case_id": record.get("case_id"),
                "source_same_frame_pose_1_rmsd_angstrom": record.get(
                    "source_same_frame_pose_1_rmsd_angstrom"
                ),
                "source_same_frame_rmsd_le_2_angstrom": record.get(
                    "source_same_frame_rmsd_le_2_angstrom"
                ),
                "representation_normalization": record.get("representation_normalization") or {},
                "posebusters_binary_results": record.get("posebusters_binary_results") or {},
                "pb_plausible": record.get("pb_plausible"),
                "pb_valid": record.get("pb_valid"),
                "localized_and_pb_plausible": record.get("localized_and_pb_plausible"),
            }
        )

    records.sort(key=lambda record: (str(record["benchmark_id"]), str(record["case_id"])))
    return {
        "protocol_id": report.get("protocol_id"),
        "posebusters": report.get("posebusters"),
        "source_benchmarks": report.get("source_benchmarks"),
        "endpoint_definition": report.get("endpoint_definition"),
        "records": records,
        "summary": report.get("summary"),
    }


def scientific_result_hash(report: Mapping[str, Any]) -> str:
    return sha256_json(scientific_payload(report))
