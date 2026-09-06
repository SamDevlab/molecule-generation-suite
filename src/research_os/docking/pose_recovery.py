"""Deterministic ligand pose recovery and RMSD diagnostics.

This module computes a geometric comparison only.  It does not create an
Evidence object and cannot promote a docking result beyond E2_COMPUTATIONAL.
Atom identity is explicit; ambiguous atom maps are returned as indeterminate
instead of being resolved by a best-score guess.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from itertools import permutations, product
from math import sqrt
from typing import Any, Iterable, Mapping

import numpy as np


class PoseRecoveryStatus(str, Enum):
    VALID = "VALID"
    INDETERMINATE = "INDETERMINATE"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PoseAtom:
    atom_name: str
    element: str
    x: float
    y: float
    z: float
    neighbors: tuple[str, ...] = ()

    @property
    def coordinates(self) -> tuple[float, float, float]:
        return (float(self.x), float(self.y), float(self.z))


@dataclass(frozen=True)
class PoseRecoveryResult:
    status: PoseRecoveryStatus
    ligand_identity: str
    atom_count: int
    mapping_method: str | None
    mapping: tuple[tuple[str, str], ...]
    raw_rmsd_angstrom: float | None
    aligned_rmsd_angstrom: float | None
    symmetry_permutations_tested: int
    reason_code: str | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return self.status == PoseRecoveryStatus.VALID

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["mapping"] = [list(item) for item in self.mapping]
        data["diagnostics"] = dict(self.diagnostics)
        return data


def _invalid(status: PoseRecoveryStatus, ligand_identity: str, code: str, detail: str, *, atom_count: int = 0) -> PoseRecoveryResult:
    return PoseRecoveryResult(status, ligand_identity, atom_count, None, (), None, None, 0, code, {"detail": detail})


def _kabsch(reference: np.ndarray, candidate: np.ndarray) -> tuple[float, float]:
    reference_center = reference.mean(axis=0)
    candidate_center = candidate.mean(axis=0)
    raw = float(np.sqrt(np.mean(np.sum((reference - candidate) ** 2, axis=1))))
    ref_centered = reference - reference_center
    candidate_centered = candidate - candidate_center
    covariance = candidate_centered.T @ ref_centered
    u, _singular, vt = np.linalg.svd(covariance)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        u[:, -1] *= -1
        rotation = u @ vt
    aligned = candidate_centered @ rotation
    aligned_rmsd = float(np.sqrt(np.mean(np.sum((ref_centered - aligned) ** 2, axis=1))))
    return raw, aligned_rmsd


def recover_pose(reference: Iterable[PoseAtom], candidate: Iterable[PoseAtom], *, ligand_identity: str, symmetric_atom_groups: Iterable[Iterable[str]] = (), max_symmetry_permutations: int = 4096) -> PoseRecoveryResult:
    """Recover a chemically declared atom map and calculate aligned RMSD.

    ``symmetric_atom_groups`` must come from a chemical identity/topology
    source.  The function will enumerate only those declared alternatives;
    it never infers symmetry from a favorable RMSD.
    """

    if not ligand_identity.strip():
        return _invalid(PoseRecoveryStatus.REJECTED, ligand_identity, "LIGAND_IDENTITY_MISSING", "ligand identity is required")
    reference_atoms, candidate_atoms = tuple(reference), tuple(candidate)
    if not reference_atoms or not candidate_atoms:
        return _invalid(PoseRecoveryStatus.REJECTED, ligand_identity, "EMPTY_POSE", "reference and candidate poses must contain atoms")
    if len(reference_atoms) != len(candidate_atoms):
        return _invalid(PoseRecoveryStatus.REJECTED, ligand_identity, "ATOM_COUNT_MISMATCH", "reference and candidate atom counts differ", atom_count=min(len(reference_atoms), len(candidate_atoms)))
    if any(atom.element.strip().upper() == "" for atom in (*reference_atoms, *candidate_atoms)):
        return _invalid(PoseRecoveryStatus.REJECTED, ligand_identity, "ELEMENT_MISSING", "every atom must have an element", atom_count=len(reference_atoms))
    candidate_by_name: dict[str, list[int]] = {}
    for index, atom in enumerate(candidate_atoms):
        candidate_by_name.setdefault(atom.atom_name, []).append(index)
    reference_names = [atom.atom_name for atom in reference_atoms]
    if len(set(reference_names)) != len(reference_names) or any(len(value) != 1 for value in candidate_by_name.values()):
        # Duplicate labels are permissible only when a declared symmetry group
        # supplies a chemically meaningful disambiguation.
        if not tuple(tuple(group) for group in symmetric_atom_groups):
            return _invalid(PoseRecoveryStatus.INDETERMINATE, ligand_identity, "AMBIGUOUS_ATOM_MAPPING", "duplicate atom labels require an explicit symmetry group", atom_count=len(reference_atoms))
    if {atom.element.strip().upper() for atom in reference_atoms} != {atom.element.strip().upper() for atom in candidate_atoms}:
        return _invalid(PoseRecoveryStatus.REJECTED, ligand_identity, "ELEMENT_SET_MISMATCH", "reference and candidate element sets differ", atom_count=len(reference_atoms))
    groups = tuple(tuple(str(name) for name in group) for group in symmetric_atom_groups)
    covered: set[str] = set()
    for group in groups:
        if not group or len(set(group)) != len(group) or covered.intersection(group):
            return _invalid(PoseRecoveryStatus.REJECTED, ligand_identity, "INVALID_SYMMETRY_GROUP", "symmetry groups must contain unique, non-overlapping atom labels", atom_count=len(reference_atoms))
        covered.update(group)
        if any(name not in reference_names or name not in candidate_by_name or len(candidate_by_name[name]) != 1 for name in group):
            return _invalid(PoseRecoveryStatus.REJECTED, ligand_identity, "SYMMETRY_GROUP_NOT_MAPPABLE", "declared symmetry group is not present in both poses", atom_count=len(reference_atoms))
    fixed_names = [name for name in reference_names if name not in covered]
    if any(name not in candidate_by_name or len(candidate_by_name[name]) != 1 for name in fixed_names):
        return _invalid(PoseRecoveryStatus.INDETERMINATE, ligand_identity, "ATOM_MAPPING_INCOMPLETE", "not every non-symmetric atom has a unique counterpart", atom_count=len(reference_atoms))
    permutation_count = 1
    options: list[tuple[tuple[str, ...], ...]] = []
    for group in groups:
        candidates = tuple(group)
        permutations_for_group = tuple(permutations(candidates))
        permutation_count *= len(permutations_for_group)
        if permutation_count > max_symmetry_permutations:
            return _invalid(PoseRecoveryStatus.INDETERMINATE, ligand_identity, "SYMMETRY_SEARCH_LIMIT", "declared symmetry alternatives exceed the deterministic search limit", atom_count=len(reference_atoms))
        options.append(permutations_for_group)
    combinations = product(*options) if options else ((),)
    best: tuple[float, float, tuple[int, ...], tuple[tuple[str, str], ...]] | None = None
    base_mapping = {name: candidate_by_name[name][0] for name in fixed_names}
    for selected in combinations:
        mapping_by_name = dict(base_mapping)
        for group, permutation in zip(groups, selected):
            for reference_name, candidate_name in zip(group, permutation):
                mapping_by_name[reference_name] = candidate_by_name[candidate_name][0]
        if len(mapping_by_name) != len(reference_atoms):
            return _invalid(PoseRecoveryStatus.INDETERMINATE, ligand_identity, "ATOM_MAPPING_INCOMPLETE", "mapping does not cover all reference atoms", atom_count=len(reference_atoms))
        mapping_indices = tuple(mapping_by_name[name] for name in reference_names)
        ref_elements = tuple(atom.element.strip().upper() for atom in reference_atoms)
        cand_elements = tuple(candidate_atoms[index].element.strip().upper() for index in mapping_indices)
        if ref_elements != cand_elements:
            continue
        ref_coords = np.asarray([atom.coordinates for atom in reference_atoms], dtype=float)
        cand_coords = np.asarray([candidate_atoms[index].coordinates for index in mapping_indices], dtype=float)
        raw, aligned = _kabsch(ref_coords, cand_coords)
        mapping_names = tuple((reference_atoms[index].atom_name, candidate_atoms[mapping_indices[index]].atom_name) for index in range(len(reference_atoms)))
        candidate_key = (aligned, raw, mapping_indices, mapping_names)
        if best is None or candidate_key < best:
            best = candidate_key
    if best is None:
        return _invalid(PoseRecoveryStatus.REJECTED, ligand_identity, "CHEMICAL_MAPPING_MISMATCH", "no declared atom map preserves element identity", atom_count=len(reference_atoms))
    aligned, raw, _indices, mapping_names = best
    return PoseRecoveryResult(PoseRecoveryStatus.VALID, ligand_identity, len(reference_atoms), "SYMMETRY_PERMUTATION" if groups else "ATOM_NAME", mapping_names, raw, aligned, permutation_count, diagnostics={"algorithm": "kabsch", "symmetry_groups": [list(group) for group in groups], "evidence_ceiling": "E2_COMPUTATIONAL"})
