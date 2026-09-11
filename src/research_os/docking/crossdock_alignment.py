from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np

from research_os.docking import redocking as base


_AMINO_ACIDS = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
    "SEC": "U", "PYL": "O", "MSE": "M",
}


@dataclass(frozen=True)
class ProteinResidue:
    auth_seq_id: int
    insertion_code: str
    resname: str
    one_letter: str
    ca_xyz: tuple[float, float, float]
    heavy_xyz: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True)
class LigandInstance:
    auth_seq_id: int
    insertion_code: str
    heavy_xyz: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True)
class RigidTransform:
    rotation: tuple[tuple[float, float, float], ...]
    translation: tuple[float, float, float]
    rmsd_angstrom: float
    pair_count: int

    def apply(self, points: Iterable[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
        rotation = np.asarray(self.rotation, dtype=float)
        translation = np.asarray(self.translation, dtype=float)
        array = np.asarray(list(points), dtype=float)
        if array.size == 0:
            return []
        transformed = array @ rotation + translation
        return [tuple(float(value) for value in row) for row in transformed]


def _xyz(line: str) -> tuple[float, float, float]:
    return float(line[30:38]), float(line[38:46]), float(line[46:54])


def parse_protein_chain(pdb_text: str, chain: str) -> tuple[ProteinResidue, ...]:
    grouped: dict[tuple[int, str, str], list[str]] = {}
    order: list[tuple[int, str, str]] = []
    for line in pdb_text.splitlines():
        if len(line) < 54 or not base._primary_altloc(line):
            continue
        if line[:6].strip() != "ATOM" or line[21].strip() != chain:
            continue
        try:
            seq = int(line[22:26].strip())
        except ValueError:
            continue
        key = (seq, line[26].strip(), line[17:20].strip())
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(line)

    residues: list[ProteinResidue] = []
    for seq, insertion, resname in order:
        one_letter = _AMINO_ACIDS.get(resname)
        if one_letter is None:
            continue
        lines = grouped[(seq, insertion, resname)]
        ca_lines = [line for line in lines if line[12:16].strip() == "CA"]
        if len(ca_lines) != 1:
            continue
        heavy = tuple(
            _xyz(line)
            for line in lines
            if base._element_from_pdb_line(line) not in {"H", "D"}
        )
        if not heavy:
            continue
        residues.append(
            ProteinResidue(
                auth_seq_id=seq,
                insertion_code=insertion,
                resname=resname,
                one_letter=one_letter,
                ca_xyz=_xyz(ca_lines[0]),
                heavy_xyz=heavy,
            )
        )
    if not residues:
        raise ValueError(f"author chain {chain!r} contains no parseable protein residues")
    return tuple(residues)


def parse_ligand_instance(
    pdb_text: str,
    *,
    ligand_id: str,
    ligand_author_chain: str,
) -> LigandInstance:
    grouped: dict[tuple[int, str], list[tuple[float, float, float]]] = {}
    for line in pdb_text.splitlines():
        if len(line) < 54 or not base._primary_altloc(line):
            continue
        if line[:6].strip() != "HETATM":
            continue
        if line[17:20].strip() != ligand_id or line[21].strip() != ligand_author_chain:
            continue
        if base._element_from_pdb_line(line) in {"H", "D"}:
            continue
        try:
            seq = int(line[22:26].strip())
        except ValueError:
            continue
        grouped.setdefault((seq, line[26].strip()), []).append(_xyz(line))
    if len(grouped) != 1:
        raise ValueError(
            f"expected exactly one {ligand_id} instance on author chain {ligand_author_chain}, "
            f"found {len(grouped)}"
        )
    (seq, insertion), coordinates = next(iter(grouped.items()))
    if not coordinates:
        raise ValueError("ligand instance contains no heavy atoms")
    return LigandInstance(seq, insertion, tuple(coordinates))


def needleman_wunsch_indices(
    source_sequence: str,
    target_sequence: str,
    *,
    match_score: int = 2,
    mismatch_score: int = -1,
    gap_score: int = -2,
) -> tuple[tuple[int | None, int | None], ...]:
    """Deterministic global alignment with diagonal > up > left tie-breaking."""

    n, m = len(source_sequence), len(target_sequence)
    score = np.zeros((n + 1, m + 1), dtype=int)
    trace = np.zeros((n + 1, m + 1), dtype=np.int8)
    for i in range(1, n + 1):
        score[i, 0] = i * gap_score
        trace[i, 0] = 2  # up
    for j in range(1, m + 1):
        score[0, j] = j * gap_score
        trace[0, j] = 3  # left

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            diagonal = score[i - 1, j - 1] + (
                match_score if source_sequence[i - 1] == target_sequence[j - 1] else mismatch_score
            )
            up = score[i - 1, j] + gap_score
            left = score[i, j - 1] + gap_score
            best = max(diagonal, up, left)
            score[i, j] = best
            trace[i, j] = 1 if diagonal == best else (2 if up == best else 3)

    aligned: list[tuple[int | None, int | None]] = []
    i, j = n, m
    while i > 0 or j > 0:
        move = int(trace[i, j])
        if i > 0 and j > 0 and move == 1:
            aligned.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif i > 0 and (j == 0 or move == 2):
            aligned.append((i - 1, None))
            i -= 1
        else:
            aligned.append((None, j - 1))
            j -= 1
    aligned.reverse()
    return tuple(aligned)


def target_pocket_residue_indices(
    target_residues: tuple[ProteinResidue, ...],
    target_ligand: LigandInstance,
    *,
    cutoff_angstrom: float,
) -> frozenset[int]:
    cutoff2 = cutoff_angstrom * cutoff_angstrom
    selected: set[int] = set()
    for index, residue in enumerate(target_residues):
        if any(
            (ax - lx) ** 2 + (ay - ly) ** 2 + (az - lz) ** 2 <= cutoff2
            for ax, ay, az in residue.heavy_xyz
            for lx, ly, lz in target_ligand.heavy_xyz
        ):
            selected.add(index)
    return frozenset(selected)


def matched_pocket_ca_pairs(
    source_residues: tuple[ProteinResidue, ...],
    target_residues: tuple[ProteinResidue, ...],
    target_pocket_indices: frozenset[int],
) -> tuple[tuple[tuple[float, float, float], tuple[float, float, float]], ...]:
    source_sequence = "".join(residue.one_letter for residue in source_residues)
    target_sequence = "".join(residue.one_letter for residue in target_residues)
    aligned = needleman_wunsch_indices(source_sequence, target_sequence)
    pairs: list[tuple[tuple[float, float, float], tuple[float, float, float]]] = []
    for source_index, target_index in aligned:
        if source_index is None or target_index is None:
            continue
        if target_index not in target_pocket_indices:
            continue
        source_residue = source_residues[source_index]
        target_residue = target_residues[target_index]
        if source_residue.one_letter != target_residue.one_letter:
            continue
        pairs.append((source_residue.ca_xyz, target_residue.ca_xyz))
    return tuple(pairs)


def kabsch_source_to_target(
    pairs: tuple[tuple[tuple[float, float, float], tuple[float, float, float]], ...],
) -> RigidTransform:
    if len(pairs) < 3:
        raise ValueError("at least three coordinate pairs are required for a rigid transform")
    source = np.asarray([pair[0] for pair in pairs], dtype=float)
    target = np.asarray([pair[1] for pair in pairs], dtype=float)
    source_center = source.mean(axis=0)
    target_center = target.mean(axis=0)
    source_centered = source - source_center
    target_centered = target - target_center
    covariance = source_centered.T @ target_centered
    u, _, vt = np.linalg.svd(covariance)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1
        rotation = u @ vt
    translation = target_center - source_center @ rotation
    fitted = source @ rotation + translation
    rmsd = math.sqrt(float(np.mean(np.sum((fitted - target) ** 2, axis=1))))
    return RigidTransform(
        rotation=tuple(tuple(float(value) for value in row) for row in rotation),
        translation=tuple(float(value) for value in translation),
        rmsd_angstrom=rmsd,
        pair_count=len(pairs),
    )


def minimum_distance(
    first: Iterable[tuple[float, float, float]],
    second: Iterable[tuple[float, float, float]],
) -> float:
    first_points = tuple(first)
    second_points = tuple(second)
    if not first_points or not second_points:
        raise ValueError("both coordinate sets must be non-empty")
    return math.sqrt(
        min(
            (ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2
            for ax, ay, az in first_points
            for bx, by, bz in second_points
        )
    )
