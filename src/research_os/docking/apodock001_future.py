"""Future-facing APODOCK-001 provenance and pose-representation guards.

This module is deliberately separate from the v1.0.2 historical evaluator.
It contains only infrastructure that may be used by a future protocol:

* a complete raw-results seal payload;
* a fail-closed timeout classifier; and
* a representation repair for Open Babel SDFs whose valence model omitted a
  formal charge, while preserving the raw pose coordinates.

No function in this module invokes Vina.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from rdkit import Chem

from research_os.core.hashing import sha256_json
from research_os.docking.apodock001_analysis import (
    SYMMETRY_MAX_MATCHES,
    same_frame_symmetry_aware_rmsd,
)


RAW_SEAL_SCHEMA_VERSION = "research-os.apodock001.raw-results-seal.v2"
POSE_ADAPTER_ID = "research-os.apodock001.pose-representation.openbabel-reference-repair"
POSE_ADAPTER_VERSION = "1.1.0"


class FuturePoseConversionError(ValueError):
    """Raised when a future pose representation cannot be validated."""


def build_complete_raw_results_seal(
    *,
    protocol_id: str,
    protocol_hash: str,
    planned_run_id: str,
    run_id: str,
    raw_output_hashes: Mapping[str, str | None],
    status: str = "SEALED",
) -> dict[str, Any]:
    """Build the complete future seal contract.

    ``protocol_hash`` is required here by construction.  The historical
    v1.0.2 seal is not rewritten; this function is for future runs only.
    """

    required = {
        "protocol_id": protocol_id,
        "protocol_hash": protocol_hash,
        "planned_run_id": planned_run_id,
        "run_id": run_id,
        "status": status,
    }
    if any(not isinstance(value, str) or not value for value in required.values()):
        raise ValueError("future raw seal requires non-empty protocol/run identities and status")
    if status != "SEALED":
        raise ValueError("future raw seal must be SEALED")
    ordered_hashes = dict(sorted(raw_output_hashes.items()))
    seal_hash = sha256_json(ordered_hashes)
    return {
        "schema_version": RAW_SEAL_SCHEMA_VERSION,
        "status": status,
        "protocol_id": protocol_id,
        "protocol_hash": protocol_hash,
        "planned_run_id": planned_run_id,
        "run_id": run_id,
        "raw_results_seal_sha256": seal_hash,
        "raw_output_hashes": ordered_hashes,
    }


def classify_timeout_record(
    record: Mapping[str, Any], *, timeout_seconds: float = 900.0
) -> dict[str, Any]:
    """Classify a recorded adapter timeout without retrying or rerunning it."""

    if record.get("status") != "FAILED" or record.get("returncode") != -1:
        return {"stage": None, "confidence": None, "is_timeout": False}
    raw_hash = record.get("raw_output_sha256")
    if raw_hash is not None:
        return {
            "stage": "EXECUTION_PROVENANCE_INCONSISTENT",
            "confidence": "HIGH",
            "is_timeout": False,
        }
    return {
        "stage": "ADAPTER_SUBPROCESS_TIMEOUT",
        "confidence": "HIGH",
        "is_timeout": True,
        "timeout_seconds": timeout_seconds,
        "retry_count": 0,
        "raw_output_present": False,
    }


def _remove_explicit_hydrogens_without_sanitizing(molecule: Chem.Mol) -> Chem.Mol:
    rw_molecule = Chem.RWMol(molecule)
    hydrogen_indices = [
        atom.GetIdx() for atom in rw_molecule.GetAtoms() if atom.GetAtomicNum() == 1
    ]
    for atom_index in sorted(hydrogen_indices, reverse=True):
        rw_molecule.RemoveAtom(atom_index)
    return rw_molecule.GetMol()


def normalize_openbabel_pose_for_reference(
    converted_sdf: str | Path,
    reference: Chem.Mol,
    *,
    max_matches: int = SYMMETRY_MAX_MATCHES,
) -> tuple[Chem.Mol, tuple[int, ...]]:
    """Repair a converted pose using the frozen reference graph.

    Open Babel may emit a valid coordinate-bearing SDF whose atom valence is
    not sanitizable by RDKit when a tetravalent nitrogen's formal charge was
    not serialized.  The repair is intentionally narrow: remove explicit H
    atoms, identify a graph-isomorphic heavy-atom correspondence, copy only
    frozen reference formal charges, and sanitize.  Coordinates are never
    fitted, rotated, translated, or replaced.
    """

    supplier = Chem.SDMolSupplier(str(converted_sdf), removeHs=False, sanitize=False)
    if len(supplier) != 1 or supplier[0] is None:
        raise FuturePoseConversionError(
            f"expected exactly one unsanitized SDF molecule in {converted_sdf}"
        )
    converted = supplier[0]
    converted_heavy = _remove_explicit_hydrogens_without_sanitizing(converted)
    reference_heavy = _remove_explicit_hydrogens_without_sanitizing(reference)
    matches = reference_heavy.GetSubstructMatches(
        converted_heavy,
        uniquify=False,
        useChirality=False,
        maxMatches=max_matches,
    )
    if not matches:
        raise FuturePoseConversionError(
            "converted pose graph does not match the frozen reference graph"
        )
    if len(matches) >= max_matches:
        raise FuturePoseConversionError("pose graph mapping cap was reached")
    mapping = min(tuple(match) for match in matches)

    repaired = Chem.RWMol(converted_heavy)
    for predicted_index, reference_index in enumerate(mapping):
        predicted = repaired.GetAtomWithIdx(predicted_index)
        frozen = reference_heavy.GetAtomWithIdx(reference_index)
        predicted.SetFormalCharge(frozen.GetFormalCharge())
    repaired_molecule = repaired.GetMol()
    try:
        Chem.SanitizeMol(repaired_molecule)
    except Exception as exc:  # RDKit exposes several concrete sanitize errors
        raise FuturePoseConversionError(
            f"reference-guided pose sanitization failed: {exc}"
        ) from exc
    if same_frame_symmetry_aware_rmsd(
        reference_heavy, repaired_molecule, max_matches=max_matches
    ).status != "PASS":
        raise FuturePoseConversionError(
            "reference-guided pose failed same-frame graph validation"
        )
    return repaired_molecule, mapping


def scientific_pose_identity(
    molecule: Chem.Mol,
    *,
    source_raw_sha256: str,
    atom_mapping: Sequence[int],
    adapter_id: str = POSE_ADAPTER_ID,
    adapter_version: str = POSE_ADAPTER_VERSION,
) -> str:
    """Hash scientific pose content, independent of derived SDF bytes.

    The explicit mapping is to frozen reference atom indices.  Sorting by
    that mapping makes SDF title lines, property ordering, and serialization
    choices irrelevant while retaining source raw provenance and coordinates.
    """

    conformer = molecule.GetConformer()
    atoms = []
    for predicted_index, reference_index in enumerate(atom_mapping):
        atom = molecule.GetAtomWithIdx(predicted_index)
        position = conformer.GetAtomPosition(predicted_index)
        atoms.append(
            {
                "reference_atom_index": int(reference_index),
                "element": atom.GetSymbol(),
                "formal_charge": atom.GetFormalCharge(),
                "xyz_angstrom": [
                    round(float(position.x), 6),
                    round(float(position.y), 6),
                    round(float(position.z), 6),
                ],
            }
        )
    payload = {
        "schema_version": "research-os.apodock001.scientific-pose-identity.v1",
        "adapter_id": adapter_id,
        "adapter_version": adapter_version,
        "source_raw_sha256": source_raw_sha256,
        "graph_identity": Chem.MolToSmiles(
            molecule, canonical=True, isomericSmiles=True
        ),
        "atoms": sorted(atoms, key=lambda item: item["reference_atom_index"]),
    }
    return sha256_json(payload)


__all__ = [
    "POSE_ADAPTER_ID",
    "POSE_ADAPTER_VERSION",
    "RAW_SEAL_SCHEMA_VERSION",
    "FuturePoseConversionError",
    "build_complete_raw_results_seal",
    "classify_timeout_record",
    "normalize_openbabel_pose_for_reference",
    "scientific_pose_identity",
]
