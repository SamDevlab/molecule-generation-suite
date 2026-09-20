"""MOLDISC-013: receptor-frame common-core pose geometry diagnostic."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from rdkit import Chem
from rdkit.Chem import inchi

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking import redocking as base
from research_os.engines.openbabel import OpenBabelEngine
from research_os.molecular_discovery.moldisc010 import run_moldisc_010
from research_os.molecular_discovery.moldisc012 import run_moldisc_012


PROGRAM_ID = "MOLDISC-013"
PARENT_MOLDISC010_HASH = "360ef9eb66981287781a971a7e09aebbe2749be765af5b4c6dcb33e3839eb48b"
PARENT_MOLDISC012_HASH = "e8c66a7726a3b191723e0dea072afdb5e4d4d9202b142eff83fe6d19c623f776"
PARENT_CANDIDATE_ID = "MOLDISC-009-JE2-5461A4A267"
PARENT_CANDIDATE_SMILES = "Cc1ccccc1CNC(=O)[C@H]1N(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2cccc(O)c2)CSC1(C)C"
PARENT_CANDIDATE_INCHIKEY = "XBNKKAGGYBXOJG-GMQQYTKMSA-N"
CHILD_CANDIDATE_ID = "MOLDISC-011-JE2-286E6F2BE8"
CHILD_CANDIDATE_SMILES = "CC1(C)SCN(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2cccc(O)c2)[C@@H]1C(=O)NCc1ccccc1"
CHILD_CANDIDATE_INCHIKEY = "DRIAWXDDGSORDT-KKUQBAQOSA-N"
TARGET_CASE_ID = "ATX-007"
PDB_ID = "1KZK"
GRID_HASH = "a0bf032d8bdb1bc20f13f298d604673cac1d2c7da8596cc228ec6602b5989aef"
NATIVE_REFERENCE_STRUCTURE_HASH = "82b48b534ff870fb8a922ed62da905bf77fe2e54f2420143986a4c5f9b9c9a4b"
PARENT_HEAVY_ATOMS = 40
CHILD_HEAVY_ATOMS = 39
COMMON_CORE_HEAVY_ATOMS = 39
MAPPING_RULE_ID = "research-os.moldisc-013.common-core-receptor-frame.v1"
RMSD_METRIC_ID = "RECEPTOR_FRAME_COMMON_CORE_RMSD"
NO_RIGID_BODY_ALIGNMENT = True


class MOLDISC013Error(RuntimeError):
    """Fail-closed error for MOLDISC-013 protocol, graph, or replay drift."""


@dataclass(frozen=True)
class PoseRecord:
    rank: int
    score_kcal_mol: float
    scientific_identity: str
    pdbqt_transport_sha256: str
    sdf_transport_sha256: str
    molecule: Chem.Mol

    def scientific_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "score_kcal_mol": self.score_kcal_mol,
            "scientific_identity": self.scientific_identity,
        }


@dataclass(frozen=True)
class PairAnalysis:
    parent_rank: int
    child_rank: int
    common_core_rmsd_angstrom: float
    mapping_identity: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MOLDISC013Result:
    program_id: str
    config_hash: str
    parent_moldisc010_replay_hash: str
    child_moldisc012_replay_hash: str
    target: Mapping[str, Any]
    receptor_frame_identity: str
    common_core_graph_identity: str
    common_core_mapping_hash: str
    matrix_shape: tuple[int, int]
    matrix_hash: str
    parent_pose_count: int
    child_pose_count: int
    rank1_pair_common_core_rmsd_angstrom: float
    minimum_all_pairs_common_core_rmsd_angstrom: float
    minimum_all_pairs_parent_rank: int
    minimum_all_pairs_child_rank: int
    parent_rank1_to_child_ensemble_min_rmsd_angstrom: float
    parent_rank1_to_child_ensemble_child_rank: int
    child_rank1_to_parent_ensemble_min_rmsd_angstrom: float
    child_rank1_to_parent_ensemble_parent_rank: int
    analysis_a_program_hash: str
    analysis_b_program_hash: str
    evidence_level: str
    parent_docking_capability: str
    program_scientific_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "target": dict(self.target),
            "matrix_shape": list(self.matrix_shape),
            "deterministic": self.analysis_a_program_hash == self.analysis_b_program_hash,
            "no_rigid_body_alignment": NO_RIGID_BODY_ALIGNMENT,
            "scores_used_for_candidate_selection": False,
            "scores_used_for_common_core_definition": False,
            "scores_used_for_pair_selection": False,
            "geometry_threshold": None,
            "generation_executed": False,
            "candidate_selection_executed": False,
            "aqsoldb_selection_executed": False,
            "docking_candidate_selection_executed": False,
        }


def _load_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MOLDISC013Error(f"could not load JSON config: {path}") from exc
    if not isinstance(value, dict):
        raise MOLDISC013Error("MOLDISC-013 config must be a JSON object")
    return value


def load_program_config_v13(path: str | Path) -> dict[str, Any]:
    config = _load_json(path)
    if config.get("program_id") != PROGRAM_ID or config.get("program_version") != "1.0":
        raise MOLDISC013Error("MOLDISC-013 requires frozen program_id/version 1.0")

    parents = config.get("parents") or {}
    parent010 = parents.get("moldisc010") or {}
    parent012 = parents.get("moldisc012") or {}
    if (
        parent010.get("program_scientific_hash") != PARENT_MOLDISC010_HASH
        or parent010.get("program_id") != "MOLDISC-010"
        or parent010.get("candidate_id") != PARENT_CANDIDATE_ID
        or parent010.get("pose_count") != 20
        or parent012.get("program_scientific_hash") != PARENT_MOLDISC012_HASH
        or parent012.get("program_id") != "MOLDISC-012"
        or parent012.get("candidate_id") != CHILD_CANDIDATE_ID
        or parent012.get("pose_count") != 16
    ):
        raise MOLDISC013Error("MOLDISC-013 frozen parent identity drifted")

    parent_candidate = config.get("parent_candidate") or {}
    child_candidate = config.get("child_candidate") or {}
    if (
        parent_candidate.get("candidate_id") != PARENT_CANDIDATE_ID
        or parent_candidate.get("canonical_smiles") != PARENT_CANDIDATE_SMILES
        or parent_candidate.get("inchikey") != PARENT_CANDIDATE_INCHIKEY
        or child_candidate.get("candidate_id") != CHILD_CANDIDATE_ID
        or child_candidate.get("canonical_smiles") != CHILD_CANDIDATE_SMILES
        or child_candidate.get("inchikey") != CHILD_CANDIDATE_INCHIKEY
    ):
        raise MOLDISC013Error("MOLDISC-013 candidate identity drifted")

    chemistry = config.get("chemistry") or {}
    if (
        chemistry.get("parent_heavy_atoms") != PARENT_HEAVY_ATOMS
        or chemistry.get("child_heavy_atoms") != CHILD_HEAVY_ATOMS
        or chemistry.get("common_core_heavy_atoms") != COMMON_CORE_HEAVY_ATOMS
        or chemistry.get("heavy_atom_difference") != 1
        or chemistry.get("child_must_be_exact_heavy_substructure") is not True
    ):
        raise MOLDISC013Error("MOLDISC-013 frozen chemistry relation drifted")

    target = config.get("target") or {}
    if (
        target.get("case_id") != TARGET_CASE_ID
        or target.get("pdb_id") != PDB_ID
        or target.get("native_ligand") != "JE2"
        or target.get("native_ligand_author_chain") != "A"
        or tuple(target.get("receptor_author_chains") or ()) != ("A", "B")
        or target.get("grid_hash") != GRID_HASH
        or target.get("native_reference_structure_hash") != NATIVE_REFERENCE_STRUCTURE_HASH
    ):
        raise MOLDISC013Error("MOLDISC-013 target or frame identity drifted")

    mapping = config.get("mapping") or {}
    if (
        mapping.get("mapping_rule_id") != MAPPING_RULE_ID
        or mapping.get("metric") != RMSD_METRIC_ID
        or mapping.get("no_rigid_body_alignment") is not True
        or mapping.get("allow_graph_automorphisms") is not True
        or mapping.get("coordinate_frame") != "RECEPTOR_FRAME"
        or mapping.get("pairwise_matrix_complete") is not True
    ):
        raise MOLDISC013Error("MOLDISC-013 mapping rule drifted")

    endpoints = config.get("endpoints") or {}
    if (
        endpoints.get("score_success_threshold") is not None
        or endpoints.get("geometry_threshold") is not None
        or endpoints.get("scores_used_for_candidate_selection") is not False
        or endpoints.get("scores_used_for_common_core_definition") is not False
        or endpoints.get("scores_used_for_pair_selection") is not False
        or tuple(endpoints.get("required_summaries") or ()) != (
            "rank1_pair_common_core_rmsd_angstrom",
            "minimum_all_pairs_common_core_rmsd_angstrom",
            "parent_rank1_to_child_ensemble_min_rmsd_angstrom",
            "child_rank1_to_parent_ensemble_min_rmsd_angstrom",
        )
    ):
        raise MOLDISC013Error("MOLDISC-013 endpoint boundary drifted")

    execution = config.get("execution_boundary") or {}
    if any(execution.get(key) is not False for key in (
        "generation_executed",
        "candidate_selection_executed",
        "aqsoldb_selection_executed",
        "docking_candidate_selection_executed",
    )):
        raise MOLDISC013Error("MOLDISC-013 must not execute generation or selection")
    return config


def _strip_hydrogens(molecule: Chem.Mol) -> Chem.Mol:
    if molecule is None:
        raise MOLDISC013Error("molecule is required")
    rw = Chem.RWMol(Chem.Mol(molecule))
    for index in reversed(range(rw.GetNumAtoms())):
        if rw.GetAtomWithIdx(index).GetAtomicNum() == 1:
            rw.RemoveAtom(index)
    return rw.GetMol()


def _normalized_graph(molecule: Chem.Mol) -> Chem.Mol:
    graph = _strip_hydrogens(molecule)
    for atom in graph.GetAtoms():
        atom.SetIsAromatic(False)
        atom.SetChiralTag(Chem.ChiralType.CHI_UNSPECIFIED)
        atom.SetFormalCharge(0)
        atom.SetNumExplicitHs(0)
        atom.SetNumRadicalElectrons(0)
        atom.SetNoImplicit(True)
    for bond in graph.GetBonds():
        bond.SetIsAromatic(False)
        bond.SetStereo(Chem.BondStereo.STEREONONE)
        bond.SetBondType(Chem.BondType.SINGLE)
    Chem.RemoveStereochemistry(graph)
    return graph


def _graph_identity(molecule: Chem.Mol) -> str:
    graph = _normalized_graph(molecule)
    return Chem.MolToSmiles(graph, canonical=True, isomericSmiles=False)


def _heavy_atom_count(molecule: Chem.Mol) -> int:
    return sum(atom.GetAtomicNum() != 1 for atom in molecule.GetAtoms())


def _coordinates(molecule: Chem.Mol, label: str) -> list[tuple[float, float, float]]:
    if molecule.GetNumConformers() != 1:
        raise MOLDISC013Error(f"{label} requires exactly one conformer")
    coordinates: list[tuple[float, float, float]] = []
    conformer = molecule.GetConformer()
    for atom in molecule.GetAtoms():
        if atom.GetAtomicNum() == 1:
            continue
        point = conformer.GetAtomPosition(atom.GetIdx())
        xyz = (float(point.x), float(point.y), float(point.z))
        if any(not math.isfinite(value) for value in xyz):
            raise MOLDISC013Error(f"{label} contains a non-finite coordinate")
        coordinates.append(xyz)
    if len(coordinates) != _normalized_graph(molecule).GetNumAtoms():
        raise MOLDISC013Error(f"{label} coordinate count is inconsistent")
    return coordinates


def _deduplicate_matches(matches: Sequence[tuple[int, ...]]) -> list[tuple[int, ...]]:
    return sorted(set(tuple(match) for match in matches))


def _exact_matches(target: Chem.Mol, query: Chem.Mol, label: str) -> list[tuple[int, ...]]:
    target_graph = _normalized_graph(target)
    query_graph = _normalized_graph(query)
    if target_graph.GetNumAtoms() != query_graph.GetNumAtoms():
        raise MOLDISC013Error(f"{label} heavy-atom count differs")
    matches = _deduplicate_matches(target_graph.GetSubstructMatches(query_graph, uniquify=False, useChirality=False))
    if not matches:
        raise MOLDISC013Error(f"{label} graph cannot be matched")
    return matches


def _child_to_parent_mappings(parent: Chem.Mol, child: Chem.Mol) -> list[tuple[int, ...]]:
    parent_graph = _normalized_graph(parent)
    child_graph = _normalized_graph(child)
    matches = _deduplicate_matches(parent_graph.GetSubstructMatches(child_graph, uniquify=False, useChirality=False))
    if not matches:
        raise MOLDISC013Error("child heavy graph is not a valid parent subgraph")
    if any(len(set(match)) != child_graph.GetNumAtoms() for match in matches):
        raise MOLDISC013Error("child graph mapping is not injective")
    return matches


def _core_mapping_identity(parent: Chem.Mol, child: Chem.Mol) -> tuple[str, dict[str, Any]]:
    mappings = _child_to_parent_mappings(parent, child)
    payload = {
        "schema": "moldisc-013.common-core-graph.v1",
        "parent_graph": _graph_identity(parent),
        "child_graph": _graph_identity(child),
        "parent_heavy_atoms": _heavy_atom_count(parent),
        "child_heavy_atoms": _heavy_atom_count(child),
        "common_core_heavy_atoms": _heavy_atom_count(child),
        "child_to_parent_mappings": [list(mapping) for mapping in mappings],
    }
    return sha256_json(payload), payload


def _canonical_pose_identity(source: Chem.Mol, pose: Chem.Mol, label: str) -> tuple[str, list[tuple[int, ...]]]:
    mappings = _exact_matches(pose, source, label)
    source_graph = _normalized_graph(source)
    coordinates = _coordinates(pose, label)
    coordinate_orders = []
    for source_to_pose in mappings:
        ordered = [coordinates[pose_index] for pose_index in source_to_pose]
        coordinate_orders.append(ordered)
    canonical_coordinates = min(coordinate_orders)
    payload = {
        "schema": "moldisc-013.pose-scientific-identity.v1",
        "source_graph": Chem.MolToSmiles(source_graph, canonical=True, isomericSmiles=False),
        "heavy_atom_count": source_graph.GetNumAtoms(),
        "coordinates_in_canonical_source_mapping": canonical_coordinates,
    }
    return sha256_json(payload), mappings


def _rmsd_without_alignment(
    parent_coordinates: Sequence[tuple[float, float, float]],
    child_coordinates: Sequence[tuple[float, float, float]],
) -> float:
    if len(parent_coordinates) != len(child_coordinates) or not parent_coordinates:
        raise MOLDISC013Error("common-core coordinate count is inconsistent")
    squared = []
    for parent_xyz, child_xyz in zip(parent_coordinates, child_coordinates):
        difference = [float(a) - float(b) for a, b in zip(parent_xyz, child_xyz)]
        if any(not math.isfinite(value) for value in difference):
            raise MOLDISC013Error("common-core displacement is non-finite")
        squared.append(sum(value * value for value in difference))
    return math.sqrt(sum(squared) / len(squared))


def analyze_pose_pair(parent_source: Chem.Mol, child_source: Chem.Mol, parent_pose: Chem.Mol, child_pose: Chem.Mol) -> PairAnalysis:
    """Compare one parent/child pose pair directly in the receptor frame."""
    if _heavy_atom_count(parent_source) != _heavy_atom_count(parent_pose):
        raise MOLDISC013Error("parent source/pose heavy-atom identity is invalid")
    if _heavy_atom_count(child_source) != _heavy_atom_count(child_pose):
        raise MOLDISC013Error("child source/pose heavy-atom identity is invalid")
    child_to_parent = _child_to_parent_mappings(parent_source, child_source)
    parent_source_to_pose = _exact_matches(parent_pose, parent_source, "parent pose/source")
    child_source_to_pose = _exact_matches(child_pose, child_source, "child pose/source")
    parent_coordinates = _coordinates(parent_pose, "parent pose")
    child_coordinates = _coordinates(child_pose, "child pose")
    candidates: list[tuple[float, str]] = []
    for core_mapping in child_to_parent:
        for parent_mapping in parent_source_to_pose:
            for child_mapping in child_source_to_pose:
                ordered_parent = [parent_coordinates[parent_mapping[parent_index]] for parent_index in core_mapping]
                ordered_child = [child_coordinates[child_mapping[child_index]] for child_index in range(len(core_mapping))]
                rmsd = _rmsd_without_alignment(ordered_parent, ordered_child)
                mapping_payload = {
                    "schema": "moldisc-013.pose-pair-mapping.v1",
                    "child_source_to_parent_source": list(core_mapping),
                    "parent_source_to_pose": list(parent_mapping),
                    "child_source_to_pose": list(child_mapping),
                }
                candidates.append((rmsd, sha256_json(mapping_payload)))
    if not candidates:
        raise MOLDISC013Error("no chemically valid common-core pose mapping exists")
    rmsd, mapping_identity = min(candidates, key=lambda item: (round(item[0], 12), item[1]))
    return PairAnalysis(0, 0, round(rmsd, 9), mapping_identity, "PASS")


def _analyze_pose_ensembles(
    *,
    parent_source: Chem.Mol,
    child_source: Chem.Mol,
    parent_poses: Sequence[PoseRecord],
    child_poses: Sequence[PoseRecord],
    output_root: Path,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=False)
    mapping_hash, mapping_payload = _core_mapping_identity(parent_source, child_source)
    cells: list[dict[str, Any]] = []
    for parent_pose in parent_poses:
        for child_pose in child_poses:
            result = analyze_pose_pair(parent_source, child_source, parent_pose.molecule, child_pose.molecule)
            cell = {
                "parent_pose_rank": parent_pose.rank,
                "child_pose_rank": child_pose.rank,
                "common_core_rmsd_angstrom": result.common_core_rmsd_angstrom,
                "mapping_identity": result.mapping_identity,
                "status": result.status,
            }
            cells.append(cell)
    matrix_core = {
        "schema": "moldisc-013.common-core-pose-matrix.v1",
        "metric": RMSD_METRIC_ID,
        "coordinate_frame": "RECEPTOR_FRAME",
        "no_rigid_body_alignment": True,
        "matrix_shape": [len(parent_poses), len(child_poses)],
        "cells": cells,
    }
    matrix_hash = sha256_json(matrix_core)
    by_pair = {(cell["parent_pose_rank"], cell["child_pose_rank"]): cell for cell in cells}
    rank1 = by_pair[(1, 1)]
    minimum = min(cells, key=lambda cell: (cell["common_core_rmsd_angstrom"], cell["parent_pose_rank"], cell["child_pose_rank"]))
    parent_rank1 = min((cell for cell in cells if cell["parent_pose_rank"] == 1), key=lambda cell: (cell["common_core_rmsd_angstrom"], cell["child_pose_rank"]))
    child_rank1 = min((cell for cell in cells if cell["child_pose_rank"] == 1), key=lambda cell: (cell["common_core_rmsd_angstrom"], cell["parent_pose_rank"]))
    summary = {
        "rank1_pair_common_core_rmsd_angstrom": rank1["common_core_rmsd_angstrom"],
        "minimum_all_pairs_common_core_rmsd_angstrom": minimum["common_core_rmsd_angstrom"],
        "minimum_all_pairs_parent_rank": minimum["parent_pose_rank"],
        "minimum_all_pairs_child_rank": minimum["child_pose_rank"],
        "parent_rank1_to_child_ensemble_min_rmsd_angstrom": parent_rank1["common_core_rmsd_angstrom"],
        "parent_rank1_to_child_ensemble_child_rank": parent_rank1["child_pose_rank"],
        "child_rank1_to_parent_ensemble_min_rmsd_angstrom": child_rank1["common_core_rmsd_angstrom"],
        "child_rank1_to_parent_ensemble_parent_rank": child_rank1["parent_pose_rank"],
    }
    analysis_payload = {
        "schema": "moldisc-013.analysis.v1",
        "mapping": mapping_payload,
        "mapping_scientific_hash": mapping_hash,
        "matrix": matrix_core,
        "matrix_scientific_hash": matrix_hash,
        "summary": summary,
        "parent_pose_scientific_identity": [pose.scientific_dict() for pose in parent_poses],
        "child_pose_scientific_identity": [pose.scientific_dict() for pose in child_poses],
        "evidence_level": "E2_COMPUTATIONAL",
        "interpretation_boundary": "descriptive derived geometry over frozen computational docking outputs; not experimental pose truth",
    }
    analysis_hash = sha256_json(analysis_payload)
    (output_root / "common_core_mapping.json").write_text(json.dumps({**mapping_payload, "mapping_scientific_hash": mapping_hash}, indent=2, sort_keys=True), encoding="utf-8")
    (output_root / "common_core_pose_matrix.json").write_text(json.dumps({**matrix_core, "matrix_scientific_hash": matrix_hash, "summary": summary}, indent=2, sort_keys=True), encoding="utf-8")
    (output_root / "analysis_scientific_payload.json").write_text(json.dumps(analysis_payload, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "analysis_program_hash": analysis_hash,
        "mapping_scientific_hash": mapping_hash,
        "matrix_scientific_hash": matrix_hash,
        "mapping_payload": mapping_payload,
        "matrix_payload": matrix_core,
        "summary": summary,
        "analysis_payload": analysis_payload,
    }


def _pdbqt_atom_records(path: Path) -> list[dict[str, Any]]:
    atoms: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        record = line[0:6].strip()
        if record not in {"ATOM", "HETATM"}:
            continue
        if len(line) < 78:
            raise MOLDISC013Error("receptor PDBQT contains a truncated atom record")
        try:
            atoms.append({
                "record": record,
                "atom_name": line[12:16].strip(),
                "alternate_location": line[16].strip(),
                "residue_name": line[17:20].strip(),
                "chain": line[21].strip(),
                "residue_sequence": line[22:26].strip(),
                "insertion_code": line[26].strip(),
                "x": round(float(line[30:38]), 6),
                "y": round(float(line[38:46]), 6),
                "z": round(float(line[46:54]), 6),
                "partial_charge": round(float(line[70:76]), 6),
                "atom_type": line[77:].strip(),
            })
        except ValueError as exc:
            raise MOLDISC013Error("receptor PDBQT contains a malformed atom record") from exc
    if not atoms:
        raise MOLDISC013Error("receptor PDBQT contains no atom records")
    return atoms


def _receptor_frame_identity(path: Path, extracted_sha256: str) -> str:
    return sha256_json({
        "schema": "moldisc-013.receptor-frame.v1",
        "receptor_extracted_sha256": extracted_sha256,
        "atoms_in_file_order": _pdbqt_atom_records(path),
    })


def _write_replay_manifest(path: Path, result: Any, frozen_hash: str, replay_match: bool, receptor_frame_identity: str) -> None:
    manifest = result.to_dict()
    manifest.update({
        "frozen_program_scientific_hash": frozen_hash,
        "replayed_program_scientific_hash": result.program_scientific_hash,
        "replay_match": replay_match,
        "receptor_frame_identity": receptor_frame_identity,
    })
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def _verify_parent_result(result: Any, *, program_id: str, frozen_hash: str, expected_candidate_id: str, expected_pose_count: int) -> None:
    if result.program_id != program_id or result.program_scientific_hash != frozen_hash:
        raise MOLDISC013Error(f"FAIL_CLOSED_PARENT_REPLAY_DRIFT: {program_id}")
    if result.technical_status != "PASS" or result.candidate_id != expected_candidate_id or result.pose_count != expected_pose_count:
        raise MOLDISC013Error(f"{program_id} replay technical or candidate identity drifted")
    if result.grid.get("grid_hash") != GRID_HASH or result.native_reference_structure_hash != NATIVE_REFERENCE_STRUCTURE_HASH:
        raise MOLDISC013Error(f"{program_id} replay target/grid identity drifted")


def _prepare_pose_set(run_root: Path, source: Chem.Mol, label: str, obabel: OpenBabelEngine, timeout: float) -> list[PoseRecord]:
    vina_paths = list(run_root.glob("*_vina_poses.pdbqt"))
    if len(vina_paths) != 1:
        raise MOLDISC013Error(f"{label} replay has no unique Vina pose output")
    vina_path = vina_paths[0]
    text = vina_path.read_text(encoding="utf-8", errors="replace")
    models = base.split_vina_pdbqt_models(text)
    scores = [float(value) for value in base.parse_vina_pose_scores(text)]
    if len(models) != len(scores) or not models:
        raise MOLDISC013Error(f"{label} replay pose/model count is inconsistent")
    pose_root = run_root / "moldisc013_pose_sdf"
    pose_root.mkdir(parents=True, exist_ok=False)
    records: list[PoseRecord] = []
    for rank, (model, score) in enumerate(zip(models, scores), start=1):
        pdbqt = pose_root / f"pose_{rank:02d}.pdbqt"
        sdf = pose_root / f"pose_{rank:02d}.sdf"
        pdbqt.write_text(model, encoding="utf-8")
        conversion = obabel.convert(pdbqt, sdf, timeout=timeout, protocol_id="moldisc013.pose-openbabel.v1")
        if conversion.returncode != 0 or not sdf.is_file():
            raise MOLDISC013Error(f"{label} pose {rank} Open Babel conversion failed: {conversion.stderr}")
        molecules = base.load_pose_sdf(sdf)
        if len(molecules) != 1:
            raise MOLDISC013Error(f"{label} pose {rank} SDF contains multiple molecules")
        pose = molecules[0]
        scientific_identity, _ = _canonical_pose_identity(source, pose, f"{label} pose {rank}")
        records.append(PoseRecord(rank, score, scientific_identity, sha256_file(pdbqt), sha256_file(sdf), pose))
    return records


def _transport_provenance(parent_result: Any, child_result: Any, parent_poses: Sequence[PoseRecord], child_poses: Sequence[PoseRecord]) -> dict[str, Any]:
    parent = parent_result.to_dict()
    child = child_result.to_dict()
    return {
        "raw_hashes_are_not_scientific_identity": True,
        "parent_moldisc010": {key: parent[key] for key in ("source_pdb_transport_sha256", "native_reference_transport_sha256", "receptor_pdbqt_sha256", "ligand_pdbqt_sha256", "vina_output_sha256")},
        "child_moldisc012": {key: child[key] for key in ("source_pdb_transport_sha256", "native_reference_transport_sha256", "receptor_pdbqt_sha256", "ligand_pdbqt_sha256", "vina_output_transport_sha256")},
        "parent_pose_conversion": [{"rank": pose.rank, "pdbqt_transport_sha256": pose.pdbqt_transport_sha256, "sdf_transport_sha256": pose.sdf_transport_sha256} for pose in parent_poses],
        "child_pose_conversion": [{"rank": pose.rank, "pdbqt_transport_sha256": pose.pdbqt_transport_sha256, "sdf_transport_sha256": pose.sdf_transport_sha256} for pose in child_poses],
    }


def run_moldisc_013(*, config_path: str | Path, output_root: str | Path, timeout: float = 120.0) -> MOLDISC013Result:
    config = load_program_config_v13(config_path)
    config_hash = sha256_json(config)
    parent_source = Chem.MolFromSmiles(PARENT_CANDIDATE_SMILES)
    child_source = Chem.MolFromSmiles(CHILD_CANDIDATE_SMILES)
    if parent_source is None or child_source is None:
        raise MOLDISC013Error("frozen candidate SMILES is not parseable")
    if _heavy_atom_count(parent_source) != PARENT_HEAVY_ATOMS or _heavy_atom_count(child_source) != CHILD_HEAVY_ATOMS:
        raise MOLDISC013Error("frozen parent/child heavy-atom count drifted")
    mapping_hash, mapping_payload = _core_mapping_identity(parent_source, child_source)
    if len(mapping_payload["child_to_parent_mappings"]) < 1:
        raise MOLDISC013Error("frozen common core is empty")

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=False)
    parent_root = root / "parent-moldisc-010"
    child_root = root / "child-moldisc-012"
    parent_result = run_moldisc_010(
        config_path="programs/moldisc-010-demethyl03-crossdock/program.json",
        output_root=parent_root,
        timeout=timeout,
    )
    child_result = run_moldisc_012(
        config_path="programs/moldisc-012-step2-demethyl01-crossdock/program.json",
        output_root=child_root,
        timeout=timeout,
    )
    _verify_parent_result(parent_result, program_id="MOLDISC-010", frozen_hash=PARENT_MOLDISC010_HASH, expected_candidate_id=PARENT_CANDIDATE_ID, expected_pose_count=20)
    _verify_parent_result(child_result, program_id="MOLDISC-012", frozen_hash=PARENT_MOLDISC012_HASH, expected_candidate_id=CHILD_CANDIDATE_ID, expected_pose_count=16)

    parent_receptor = parent_root / "receptor.pdbqt"
    child_receptor = child_root / "receptor.pdbqt"
    parent_frame_identity = _receptor_frame_identity(parent_receptor, parent_result.receptor_extracted_sha256)
    child_frame_identity = _receptor_frame_identity(child_receptor, child_result.receptor_extracted_sha256)
    if parent_frame_identity != child_frame_identity or parent_result.receptor_extracted_sha256 != child_result.receptor_extracted_sha256:
        raise MOLDISC013Error("FAIL_CLOSED_PARENT_REPLAY_DRIFT: receptor coordinate frame differs")
    if parent_result.grid.get("grid_hash") != child_result.grid.get("grid_hash"):
        raise MOLDISC013Error("FAIL_CLOSED_PARENT_REPLAY_DRIFT: derived grid differs")

    _write_replay_manifest(root / "parent_replay_manifest.json", parent_result, PARENT_MOLDISC010_HASH, True, parent_frame_identity)
    _write_replay_manifest(root / "child_replay_manifest.json", child_result, PARENT_MOLDISC012_HASH, True, child_frame_identity)
    (root / "common_core_mapping.json").write_text(json.dumps({**mapping_payload, "mapping_scientific_hash": mapping_hash}, indent=2, sort_keys=True), encoding="utf-8")

    obabel = OpenBabelEngine()
    if not obabel.available:
        raise MOLDISC013Error("Open Babel is unavailable for pose replay conversion")
    parent_poses = _prepare_pose_set(parent_root, parent_source, "MOLDISC-010", obabel, timeout)
    child_poses = _prepare_pose_set(child_root, child_source, "MOLDISC-012", obabel, timeout)
    if len(parent_poses) != 20 or len(child_poses) != 16:
        raise MOLDISC013Error("FAIL_CLOSED_PARENT_REPLAY_DRIFT: frozen pose dimensions changed")

    analysis_root = root / "analysis"
    analysis_a = _analyze_pose_ensembles(parent_source=parent_source, child_source=child_source, parent_poses=parent_poses, child_poses=child_poses, output_root=analysis_root / "a")
    analysis_b = _analyze_pose_ensembles(parent_source=parent_source, child_source=child_source, parent_poses=parent_poses, child_poses=child_poses, output_root=analysis_root / "b")
    for key in ("mapping_scientific_hash", "matrix_scientific_hash", "summary"):
        if analysis_a[key] != analysis_b[key]:
            raise MOLDISC013Error(f"MOLDISC-013 analysis A/B drifted: {key}")
    if analysis_a["mapping_scientific_hash"] != mapping_hash:
        raise MOLDISC013Error("MOLDISC-013 mapping hash drifted")
    (root / "common_core_pose_matrix.json").write_text(json.dumps({**analysis_a["matrix_payload"], "matrix_scientific_hash": analysis_a["matrix_scientific_hash"], "summary": analysis_a["summary"]}, indent=2, sort_keys=True), encoding="utf-8")

    target = {
        "case_id": TARGET_CASE_ID,
        "pdb_id": PDB_ID,
        "native_ligand": "JE2",
        "native_ligand_author_chain": "A",
        "receptor_author_chains": ["A", "B"],
        "native_reference_structure_hash": NATIVE_REFERENCE_STRUCTURE_HASH,
        "grid_hash": GRID_HASH,
        "receptor_frame_identity": parent_frame_identity,
    }
    summary = analysis_a["summary"]
    scientific = {
        "program_id": PROGRAM_ID,
        "config_hash": config_hash,
        "parent_programs": {
            "moldisc010_frozen_hash": PARENT_MOLDISC010_HASH,
            "moldisc010_replayed_hash": parent_result.program_scientific_hash,
            "moldisc012_frozen_hash": PARENT_MOLDISC012_HASH,
            "moldisc012_replayed_hash": child_result.program_scientific_hash,
        },
        "candidates": {
            "parent": {"candidate_id": PARENT_CANDIDATE_ID, "canonical_smiles": PARENT_CANDIDATE_SMILES, "inchikey": PARENT_CANDIDATE_INCHIKEY},
            "child": {"candidate_id": CHILD_CANDIDATE_ID, "canonical_smiles": CHILD_CANDIDATE_SMILES, "inchikey": CHILD_CANDIDATE_INCHIKEY},
        },
        "target": target,
        "common_core": {
            "graph_identity": mapping_hash,
            "mapping_rule_id": MAPPING_RULE_ID,
            "mapping_scientific_hash": mapping_hash,
            "parent_heavy_atoms": PARENT_HEAVY_ATOMS,
            "child_heavy_atoms": CHILD_HEAVY_ATOMS,
            "common_core_heavy_atoms": COMMON_CORE_HEAVY_ATOMS,
        },
        "parent_pose_scientific_identity": [pose.scientific_dict() for pose in parent_poses],
        "child_pose_scientific_identity": [pose.scientific_dict() for pose in child_poses],
        "matrix": analysis_a["matrix_payload"],
        "matrix_scientific_hash": analysis_a["matrix_scientific_hash"],
        "summary": summary,
        "evidence_boundary": {
            "evidence_level": "E2_COMPUTATIONAL",
            "parent_docking_capability": "NON_COGNATE_HOLO_CROSSDOCKING / PARTIALLY_VALIDATED",
            "metric": RMSD_METRIC_ID,
            "no_rigid_body_alignment": True,
            "scores_used_for_candidate_selection": False,
            "scores_used_for_common_core_definition": False,
            "scores_used_for_pair_selection": False,
            "score_success_threshold": None,
            "geometry_threshold": None,
            "interpretation": "descriptive derived geometry over frozen computational docking outputs; rank 1 is a docking-engine rank, not experimentally validated pose truth",
        },
    }
    program_hash = sha256_json(scientific)
    result = MOLDISC013Result(
        program_id=PROGRAM_ID,
        config_hash=config_hash,
        parent_moldisc010_replay_hash=parent_result.program_scientific_hash,
        child_moldisc012_replay_hash=child_result.program_scientific_hash,
        target=target,
        receptor_frame_identity=parent_frame_identity,
        common_core_graph_identity=mapping_hash,
        common_core_mapping_hash=analysis_a["mapping_scientific_hash"],
        matrix_shape=(len(parent_poses), len(child_poses)),
        matrix_hash=analysis_a["matrix_scientific_hash"],
        parent_pose_count=len(parent_poses),
        child_pose_count=len(child_poses),
        rank1_pair_common_core_rmsd_angstrom=summary["rank1_pair_common_core_rmsd_angstrom"],
        minimum_all_pairs_common_core_rmsd_angstrom=summary["minimum_all_pairs_common_core_rmsd_angstrom"],
        minimum_all_pairs_parent_rank=summary["minimum_all_pairs_parent_rank"],
        minimum_all_pairs_child_rank=summary["minimum_all_pairs_child_rank"],
        parent_rank1_to_child_ensemble_min_rmsd_angstrom=summary["parent_rank1_to_child_ensemble_min_rmsd_angstrom"],
        parent_rank1_to_child_ensemble_child_rank=summary["parent_rank1_to_child_ensemble_child_rank"],
        child_rank1_to_parent_ensemble_min_rmsd_angstrom=summary["child_rank1_to_parent_ensemble_min_rmsd_angstrom"],
        child_rank1_to_parent_ensemble_parent_rank=summary["child_rank1_to_parent_ensemble_parent_rank"],
        analysis_a_program_hash=analysis_a["analysis_program_hash"],
        analysis_b_program_hash=analysis_b["analysis_program_hash"],
        evidence_level="E2_COMPUTATIONAL",
        parent_docking_capability="NON_COGNATE_HOLO_CROSSDOCKING / PARTIALLY_VALIDATED",
        program_scientific_hash=program_hash,
    )
    (root / "program_manifest.json").write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (root / "scientific_payload.json").write_text(json.dumps(scientific, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (root / "transport_provenance.json").write_text(json.dumps(_transport_provenance(parent_result, child_result, parent_poses, child_poses), indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (root / "program_report.md").write_text(_markdown(result), encoding="utf-8")
    return result


def _markdown(result: MOLDISC013Result) -> str:
    return "\n".join([
        "# MOLDISC-013 — common-core pose geometry diagnostic",
        "",
        "- parent: MOLDISC-010 / DEMETHYL-03",
        "- child: MOLDISC-012 / STEP2-DEMETHYL-01",
        f"- target: {TARGET_CASE_ID} / {PDB_ID} / JE2 pocket",
        f"- metric: {RMSD_METRIC_ID}",
        f"- matrix: {result.matrix_shape[0]} x {result.matrix_shape[1]}",
        f"- rank-1 pair common-core RMSD: {result.rank1_pair_common_core_rmsd_angstrom} Å",
        f"- minimum all-pairs common-core RMSD: {result.minimum_all_pairs_common_core_rmsd_angstrom} Å (parent rank {result.minimum_all_pairs_parent_rank}, child rank {result.minimum_all_pairs_child_rank})",
        f"- program scientific hash: {result.program_scientific_hash}",
        "",
        "## Interpretation boundary",
        "",
        "Coordinates remain in the unchanged receptor frame. No Kabsch alignment, rigid-body fitting, centering, translation normalization, or rotation normalization is performed.",
        "",
        "Rank 1 is a docking-engine rank, not an experimentally validated pose. This derived E2 computational geometry diagnostic does not establish affinity, binding conservation, potency, efficacy, or superiority.",
        "",
    ])


__all__ = [
    "CHILD_CANDIDATE_ID",
    "CHILD_CANDIDATE_INCHIKEY",
    "CHILD_CANDIDATE_SMILES",
    "COMMON_CORE_HEAVY_ATOMS",
    "GRID_HASH",
    "MOLDISC013Error",
    "MOLDISC013Result",
    "PARENT_CANDIDATE_ID",
    "PARENT_CANDIDATE_INCHIKEY",
    "PARENT_CANDIDATE_SMILES",
    "PARENT_HEAVY_ATOMS",
    "PARENT_MOLDISC010_HASH",
    "PARENT_MOLDISC012_HASH",
    "RMSD_METRIC_ID",
    "analyze_pose_pair",
    "load_program_config_v13",
    "run_moldisc_013",
]
