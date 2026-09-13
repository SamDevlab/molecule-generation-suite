"""Postmortem-only raw-coordinate adapter for APODOCK-001.

This module is intentionally not the v1.1 evaluator and is not a protocol
change.  It answers one bounded question after a sealed run: can the raw
PDBQT coordinates be evaluated when a byte-preserved, already-converted
representation template is available?

The template supplies atom order and connectivity.  Coordinates and scores
come only from the raw PDBQT.  No bond graph is inferred from distances, no
Open Babel or Vina subprocess is invoked, and the raw file is never written.
All results produced through this module must be labelled
``POSTMORTEM_DIAGNOSTIC_ONLY``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Sequence

from rdkit import Chem

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking.apodock001_analysis import (
    MAX_ANALYZED_POSES,
    SYMMETRY_MAX_MATCHES,
    SameFrameRmsdResult,
    same_frame_symmetry_aware_rmsd,
)
from research_os.docking.redocking import _heavy_atom_copy


ADAPTER_PAYLOAD = {
    "schema_version": "research-os.apodock001.postmortem-raw-coordinate-adapter.v1",
    "coordinate_source": "sealed raw Vina PDBQT atom coordinates",
    "template_source": "preserved converted representation template",
    "mapping_policy": "template atom order plus element identity; no geometry-derived graph",
    "rmsd_semantics": "same-frame symmetry-aware heavy-atom RMSD",
    "symmetry_max_matches": SYMMETRY_MAX_MATCHES,
    "pose_order": "raw Vina output order",
    "raw_mutation": False,
    "subprocess_invocation": False,
}
ADAPTER_ID = (
    "research-os.apodock001.postmortem.raw-coordinate-adapter.v1+"
    f"{sha256_json(ADAPTER_PAYLOAD)[:16]}"
)
DIAGNOSTIC_STATUS = "POSTMORTEM_DIAGNOSTIC_ONLY"

_SCORE_RE = re.compile(r"^REMARK\s+VINA\s+RESULT:\s+(-?\d+(?:\.\d+)?)")
_ATOM_TYPES = {
    "C": "C",
    "A": "C",
    "N": "N",
    "NA": "N",
    "O": "O",
    "OA": "O",
    "P": "P",
    "S": "S",
    "SA": "S",
    "F": "F",
    "CL": "Cl",
    "BR": "Br",
    "I": "I",
    "H": "H",
    "HD": "H",
}


class RawCoordinateAdapterError(ValueError):
    """Raised when raw/template identity cannot be proven."""


@dataclass(frozen=True)
class RawPdbqtAtom:
    serial: int
    atom_name: str
    autodock_type: str
    element: str
    xyz: tuple[float, float, float]


@dataclass(frozen=True)
class RawPdbqtPose:
    pose_index: int
    score_kcal_mol: float | None
    atoms: tuple[RawPdbqtAtom, ...]


@dataclass(frozen=True)
class DiagnosticPoseResult:
    pose_index: int
    score_kcal_mol: float | None
    rmsd: SameFrameRmsdResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "pose_index": self.pose_index,
            "vina_score_kcal_mol": self.score_kcal_mol,
            "rmsd": self.rmsd.to_dict(),
            "status": DIAGNOSTIC_STATUS,
        }


def _element_from_pdbqt_type(atom_type: str, atom_name: str) -> str:
    normalized = atom_type.strip().upper()
    if normalized in _ATOM_TYPES:
        return _ATOM_TYPES[normalized]
    letters = "".join(character for character in atom_name if character.isalpha())
    if not letters:
        raise RawCoordinateAdapterError("PDBQT atom has no element identity")
    candidate = letters[:2].title()
    if candidate in {"Cl", "Br"}:
        return candidate
    return candidate[0].upper()


def _split_models(text: str) -> list[str]:
    lines = text.splitlines()
    models: list[list[str]] = []
    current: list[str] | None = None
    saw_model = False
    for line in lines:
        if line.startswith("MODEL"):
            saw_model = True
            if current:
                models.append(current)
            current = [line]
        elif line.startswith("ENDMDL"):
            if current is not None:
                current.append(line)
                models.append(current)
                current = None
        elif current is not None:
            current.append(line)
    if current:
        models.append(current)
    if not saw_model and text.strip():
        return [text.rstrip() + "\n"]
    return ["\n".join(model) + "\n" for model in models if model]


def parse_raw_pdbqt(path: str | Path, *, max_poses: int = MAX_ANALYZED_POSES) -> tuple[RawPdbqtPose, ...]:
    """Parse raw PDBQT records without changing or materializing the input."""

    source = Path(path)
    if not source.is_file():
        raise RawCoordinateAdapterError(f"raw PDBQT is missing: {source}")
    poses: list[RawPdbqtPose] = []
    for pose_index, model in enumerate(_split_models(source.read_text(encoding="utf-8", errors="strict")), 1):
        atoms: list[RawPdbqtAtom] = []
        score: float | None = None
        for line in model.splitlines():
            score_match = _SCORE_RE.match(line)
            if score_match:
                if score is not None:
                    raise RawCoordinateAdapterError(f"multiple Vina scores in pose {pose_index}")
                score = float(score_match.group(1))
            if not line.startswith(("ATOM", "HETATM")):
                continue
            try:
                # AutoDock atom types occupy columns 77-79 (one-based),
                # hence the zero-based slice 76:79.
                autodock_type = line[76:79].strip()
                atom_name = line[12:16].strip()
                atoms.append(
                    RawPdbqtAtom(
                        serial=int(line[6:11]),
                        atom_name=atom_name,
                        autodock_type=autodock_type,
                        element=_element_from_pdbqt_type(autodock_type, atom_name),
                        xyz=(float(line[30:38]), float(line[38:46]), float(line[46:54])),
                    )
                )
            except (IndexError, ValueError) as exc:
                raise RawCoordinateAdapterError(
                    f"malformed raw PDBQT atom record in pose {pose_index}"
                ) from exc
        if not atoms:
            raise RawCoordinateAdapterError(f"pose {pose_index} has no atoms")
        poses.append(RawPdbqtPose(pose_index, score, tuple(atoms)))
    if not poses:
        raise RawCoordinateAdapterError("raw PDBQT contains no poses")
    return tuple(poses[:max_poses])


def _load_template(path: str | Path) -> Chem.Mol:
    supplier = Chem.SDMolSupplier(str(path), removeHs=False, sanitize=False)
    molecules = [molecule for molecule in supplier if molecule is not None]
    if len(molecules) != 1 or molecules[0].GetNumConformers() != 1:
        raise RawCoordinateAdapterError(f"template must contain exactly one 3D molecule: {path}")
    return molecules[0]


def _copy_raw_coordinates(template: Chem.Mol, atoms: Sequence[RawPdbqtAtom]) -> Chem.Mol:
    if template.GetNumAtoms() != len(atoms):
        raise RawCoordinateAdapterError(
            f"template/raw atom count differs: {template.GetNumAtoms()} != {len(atoms)}"
        )
    template_elements = tuple(atom.GetSymbol() for atom in template.GetAtoms())
    raw_elements = tuple(atom.element for atom in atoms)
    if template_elements != raw_elements:
        raise RawCoordinateAdapterError(
            "template/raw atom identity differs; no coordinate-only mapping is proven"
        )
    molecule = Chem.Mol(template)
    conformer = molecule.GetConformer()
    for index, atom in enumerate(atoms):
        conformer.SetAtomPosition(index, atom.xyz)
    return molecule


def evaluate_raw_pdbqt(
    raw_pdbqt: str | Path,
    reference: Chem.Mol,
    template_sdf: str | Path,
    *,
    max_matches: int = SYMMETRY_MAX_MATCHES,
    max_poses: int = MAX_ANALYZED_POSES,
) -> tuple[DiagnosticPoseResult, ...]:
    """Evaluate raw coordinates against a trusted representation template.

    The template is not re-derived from pose geometry.  It is an explicit
    prerequisite and its atom ordering is checked against every raw PDBQT
    pose.  The raw PDBQT remains byte-for-byte untouched.
    """

    template = _load_template(template_sdf)
    poses = parse_raw_pdbqt(raw_pdbqt, max_poses=max_poses)
    results: list[DiagnosticPoseResult] = []
    for pose in poses:
        results.append(
            evaluate_raw_pose(
                pose,
                reference,
                template,
                max_matches=max_matches,
            )
        )
    return tuple(results)


def evaluate_raw_pose(
    pose: RawPdbqtPose,
    reference: Chem.Mol,
    template: Chem.Mol | str | Path,
    *,
    max_matches: int = SYMMETRY_MAX_MATCHES,
) -> DiagnosticPoseResult:
    """Evaluate one parsed raw pose with an explicit trusted template."""

    molecule = _load_template(template) if isinstance(template, (str, Path)) else template
    predicted = _copy_raw_coordinates(molecule, pose.atoms)
    rmsd = same_frame_symmetry_aware_rmsd(
        reference, predicted, max_matches=max_matches
    )
    return DiagnosticPoseResult(pose.pose_index, pose.score_kcal_mol, rmsd)


def template_identity(path: str | Path) -> dict[str, Any]:
    """Return a byte-addressed identity for the trusted template artifact."""

    molecule = _load_template(path)
    heavy = _heavy_atom_copy(molecule)
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "atom_count": molecule.GetNumAtoms(),
        "heavy_atom_count": heavy.GetNumAtoms(),
        "element_sequence": [atom.GetSymbol() for atom in molecule.GetAtoms()],
    }


__all__ = [
    "ADAPTER_ID",
    "DIAGNOSTIC_STATUS",
    "DiagnosticPoseResult",
    "RawCoordinateAdapterError",
    "RawPdbqtAtom",
    "RawPdbqtPose",
    "evaluate_raw_pdbqt",
    "evaluate_raw_pose",
    "parse_raw_pdbqt",
    "template_identity",
]
