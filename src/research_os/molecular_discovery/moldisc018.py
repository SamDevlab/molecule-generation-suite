"""MOLDISC-018: reciprocal holo cross-docking capability validation.

This is a bounded capability program.  It uses only four experimentally
observed reciprocal cases plus four K57 cognate controls.  It does not create
or select molecules and it never interprets a Vina score as affinity.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, inchi, rdMolDescriptors

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking import redocking as base
from research_os.docking.capability import profile_identity_from_mapping
from research_os.docking.schema import DockingRequest, GridBox
from research_os.engines.openbabel import OpenBabelEngine
from research_os.engines.vina import VinaEngine
from research_os.molecular_discovery import moldisc016
from research_os.molecular_discovery import moldisc017


PROGRAM_ID = "MOLDISC-018"
PROGRAM_VERSION = "1.0"
PARENT_MOLDISC017_HASH = "6508ac7b0e658bc67b10a835f4f172ff95426f648ace89755d41197ae2019724"
PARENT_MOLDISC017_PROTOCOL_HASH = "c4dac30cfe54363d8468ccc2532d4010653f117c56e4aa3401e79eac13502270"
CAPABILITY_CONTEXT = "NON_COGNATE_HOLO_CROSSDOCKING"
CAPABILITY_SOURCE_ID = "MOLDISC-018-RECIPROCAL-HOLO"
CAPABILITY_BENCHMARK_ID = "MOLDISC-018"
JE2_BACKGROUND = "1MSM"
K57_BACKGROUND = "1MRW"
JE2_MUTANT = "1MSN"
K57_MUTANT = "1MRX"
JE2_INCHIKEY = "CUFQBQOBLVLKRF-RZDMPUFOSA-N"
K57_INCHIKEY = "CGFVYUGIPISJQG-ACIOBRDBSA-N"
K57_FORMULA = "C28H37N3O5S"
GRID_1MSM = "5967ad06319d2d02646f96bf9ed70769eb345d76e1e50e2ab29aedb348ed0766"
GRID_1MSN = "ddcc2e6bb18e78e0517380a168496db1f5fab16407861189c2f3f89842fcf40a"
GRID_1MRW = "e8a22e5c534876dd50bcddfc14faa00df25b73f5f9243fbb777b9377e5e359f7"
GRID_1MRX = "7f2972c64361d59491280b1415c150c3bab238952ce5188f65bbcf18e36fc847"
VINA_VERSION = "1.2.7"
VINA_SEED = 42
VINA_CPU = 1
VINA_EXHAUSTIVENESS = 16
VINA_NUM_MODES = 20
ETKDG_SEEDS = (42, 1337, 2025)
SUCCESS_THRESHOLD = 2.0
EXPECTED_DOCKING_RUNS = 20


class MOLDISC018Error(RuntimeError):
    """Fail-closed MOLDISC-018 protocol, source, or execution error."""


def _load_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MOLDISC018Error(f"could not load JSON: {path}") from exc
    if not isinstance(value, dict):
        raise MOLDISC018Error("JSON object required")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def protocol_hash(config: Mapping[str, Any]) -> str:
    return sha256_json(dict(config))


def load_program_config_v18(path: str | Path) -> dict[str, Any]:
    config = _load_json(path)
    if config.get("program_id") != PROGRAM_ID or config.get("program_version") != PROGRAM_VERSION:
        raise MOLDISC018Error("MOLDISC-018 program identity/version drifted")
    parent = config.get("parents", {}).get("moldisc017", {})
    if parent.get("program_scientific_hash") != PARENT_MOLDISC017_HASH or parent.get("protocol_hash") != PARENT_MOLDISC017_PROTOCOL_HASH:
        raise MOLDISC018Error("MOLDISC-017 parent identity drifted")
    if parent.get("measurement_transfer_allowed") is not False:
        raise MOLDISC018Error("MOLDISC-017 measurement transfer boundary drifted")
    panel = config.get("structures", {})
    expected = {
        "JE2_BACKGROUND": (JE2_BACKGROUND, "JE2", JE2_INCHIKEY, ["Q7K", "L33I", "L63I"], GRID_1MSM),
        "K57_BACKGROUND": (K57_BACKGROUND, "K57", K57_INCHIKEY, ["Q7K", "L33I", "L63I"], GRID_1MRW),
        "JE2_MUTANT": (JE2_MUTANT, "JE2", JE2_INCHIKEY, ["Q7K", "L33I", "L63I", "V82F", "I84V"], GRID_1MSN),
        "K57_MUTANT": (K57_MUTANT, "K57", K57_INCHIKEY, ["Q7K", "L33I", "L63I", "V82F", "I84V"], GRID_1MRX),
    }
    for label, (pdb, ligand, key, mutations, grid_hash) in expected.items():
        item = panel.get(label, {})
        if item.get("pdb_id") != pdb or item.get("ligand") != ligand or item.get("inchikey") != key or item.get("mutations") != mutations or item.get("grid_hash") != grid_hash:
            raise MOLDISC018Error(f"structure boundary drifted: {label}")
        if item.get("receptor_author_chains") != ["A", "B"] or item.get("ligand_auth_seq_id") != 1001:
            raise MOLDISC018Error(f"source chain boundary drifted: {label}")
    if config.get("native_context", {}).get("k57_is_generated_candidate") is not False or config.get("native_context", {}).get("generated_candidate_is_k57") is not False:
        raise MOLDISC018Error("K57 candidate identity boundary drifted")
    if config.get("native_context", {}).get("experimental_activity_transfer_allowed") is not False:
        raise MOLDISC018Error("experimental activity transfer boundary drifted")
    docking = config.get("docking_protocol", {})
    frozen = {"rdkit_conformer_engine": "ETKDGv3", "etkdg_seeds": [42, 1337, 2025], "vina_seed": 42, "cpu": 1, "exhaustiveness": 16, "num_modes": 20, "scoring_function": "vina", "vina_version": "1.2.7", "retry_count": 0}
    if any(docking.get(key) != value for key, value in frozen.items()):
        raise MOLDISC018Error("docking protocol drifted")
    if len(config.get("cases", [])) != 4 or [case.get("case_id") for case in config.get("cases", [])] != ["RX-01", "RX-02", "RX-03", "RX-04"]:
        raise MOLDISC018Error("reciprocal case set/order drifted")
    if [item.get("campaign_id") for item in config.get("campaigns", [])] != [f"CAMP-018-{letter}" for letter in "ABCDEFGHI"]:
        raise MOLDISC018Error("campaign set/order drifted")
    if sum(int(item.get("planned_runs", -1)) for item in config.get("campaigns", [])) != EXPECTED_DOCKING_RUNS:
        raise MOLDISC018Error("planned run count drifted")
    if (config.get("resource_bounds") or {}).get("planned_new_docking_runs") != EXPECTED_DOCKING_RUNS:
        raise MOLDISC018Error("resource bounds drifted")
    boundaries = config.get("boundaries", {})
    for name in ("molecule_generation_executed", "generated_candidate_docking_executed", "candidate_selection_executed", "lead_selection_executed", "affinity_inference", "adaptive_execution"):
        if boundaries.get(name) is not False:
            raise MOLDISC018Error(f"boundary {name} must be false")
    if boundaries.get("evidence_ceiling") != "E2_COMPUTATIONAL":
        raise MOLDISC018Error("evidence ceiling drifted")
    if [claim.get("claim_id") for claim in config.get("claims", [])] != [f"CLAIM-018-0{i}" for i in range(1, 7)]:
        raise MOLDISC018Error("claim set/order drifted")
    return config


def build_execution_plan(config: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    cases = list((config or {}).get("cases", [])) if config else [
        {"case_id": "RX-01", "background": "BACKGROUND", "ligand": "K57", "target": "JE2_BACKGROUND", "reference": "K57_BACKGROUND"},
        {"case_id": "RX-02", "background": "BACKGROUND", "ligand": "JE2", "target": "K57_BACKGROUND", "reference": "JE2_BACKGROUND"},
        {"case_id": "RX-03", "background": "MUTANT", "ligand": "K57", "target": "JE2_MUTANT", "reference": "K57_MUTANT"},
        {"case_id": "RX-04", "background": "MUTANT", "ligand": "JE2", "target": "K57_MUTANT", "reference": "JE2_MUTANT"},
    ]
    plan: list[dict[str, Any]] = []
    for state, pdb, ligand in (("K57_BACKGROUND", K57_BACKGROUND, "K57"), ("K57_MUTANT", K57_MUTANT, "K57")):
        for replicate in ("RUN_A", "RUN_B"):
            plan.append({"run_id": f"{state}__cognate__{replicate}", "campaign_id": "CAMP-018-B", "case_id": state, "kind": "K57_COGNATE_REDOCK", "target": state, "reference": state, "ligand": ligand, "pdb_id": pdb, "etkdg_seed": 42, "replicate": replicate})
    for case in cases:
        for seed, replicates in ((42, ("RUN_A", "RUN_B")), (1337, ("RUN_A",)), (2025, ("RUN_A",))):
            for replicate in replicates:
                plan.append({"run_id": f"{case['case_id']}__etkdg_{seed}__{replicate}", "campaign_id": "CAMP-018-C" if case["background"] == "BACKGROUND" else "CAMP-018-D", "case_id": case["case_id"], "kind": "RECIPROCAL_CROSSDOCK", "target": case["target"], "reference": case["reference"], "ligand": case["ligand"], "etkdg_seed": seed, "replicate": replicate})
    if len(plan) != EXPECTED_DOCKING_RUNS or len({item["run_id"] for item in plan}) != EXPECTED_DOCKING_RUNS:
        raise MOLDISC018Error("execution plan is not exactly 20 unique docking runs")
    return plan


def _pdb_resolution(text: str) -> float:
    match = re.search(r"^REMARK\s+2\s+RESOLUTION\.\s+([0-9.]+)\s+ANGSTROMS", text, re.MULTILINE)
    if not match:
        raise MOLDISC018Error("PDB resolution unavailable")
    return float(match.group(1))


def _atom_chains(text: str) -> tuple[str, ...]:
    return tuple(sorted({line[21].strip() for line in text.splitlines() if line.startswith("ATOM") and line[21].strip()}))


def _state_case(pdb_id: str, ligand: str, chain: str) -> base.RedockingCase:
    return base.RedockingCase(f"MOLDISC018-{pdb_id}", pdb_id, ligand, chain, ("A", "B"), "HIV-1 protease", 2.0, f"https://www.rcsb.org/structure/{pdb_id}")


def _state_spec(config: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    return config["structures"][label]


def run_source_audit(config_path: str | Path, root: Path, *, timeout: float = 120.0) -> dict[str, Any]:
    config = _load_json(config_path)
    source_root = root / "source_audit"
    obabel = OpenBabelEngine()
    if not obabel.available:
        raise MOLDISC018Error("Open Babel is required for source audit")
    states: dict[str, Any] = {}
    fixtures = ("JE2_BACKGROUND", "K57_BACKGROUND", "JE2_MUTANT", "K57_MUTANT")
    for label in fixtures:
        spec = _state_spec(config, label)
        directory = source_root / label
        directory.mkdir(parents=True, exist_ok=True)
        pdb_id = spec["pdb_id"]
        raw = directory / f"{pdb_id}.pdb"
        raw_sha = base._download(f"https://files.rcsb.org/download/{pdb_id}.pdb", raw, timeout=timeout)
        text = raw.read_text(encoding="utf-8", errors="replace")
        if _pdb_resolution(text) != 2.0 or not {"A", "B"}.issubset(_atom_chains(text)):
            raise MOLDISC018Error(f"source audit resolution/chains failed: {label}")
        mutation_values = sorted(moldisc017._mutations(text, ("A", "B")), key=lambda item: (int(re.findall(r"\d+", item)[0]), item))
        if mutation_values != spec["mutations"]:
            raise MOLDISC018Error(f"source audit mutation drift: {label}: {mutation_values}")
        extraction = base.extract_case_from_pdb(text, _state_case(pdb_id, spec["ligand"], spec["ligand_author_chain"]))
        receptor_pdb = directory / "receptor_extracted.pdb"
        receptor_pdb.write_text(extraction.receptor_pdb, encoding="utf-8")
        native_sdf = directory / f"{spec['ligand']}_native.sdf"
        native_sha = base._download(base._instance_sdf_url(_state_case(pdb_id, spec["ligand"], spec["ligand_author_chain"]), extraction.ligand_auth_seq_id), native_sdf, timeout=timeout)
        native = base.load_single_sdf(native_sdf)
        ccd = moldisc017._load_json(directory / f"ccd-{spec['ligand']}.json") if (directory / f"ccd-{spec['ligand']}.json").is_file() else None
        if ccd is None:
            ccd_descriptor = base._download(f"https://data.rcsb.org/rest/v1/core/chemcomp/{spec['ligand']}", directory / f"ccd-{spec['ligand']}.json", timeout=timeout)
            ccd = moldisc017._load_json(directory / f"ccd-{spec['ligand']}.json")
        chem = ccd.get("chem_comp") or {}
        descriptor = ccd.get("rcsb_chem_comp_descriptor") or {}
        ccd_identity = {"component_id": spec["ligand"], "formula": chem.get("formula"), "inchikey": descriptor.get("InChIKey"), "canonical_smiles": descriptor.get("SMILES")}
        if ccd_identity["inchikey"] != spec["inchikey"] or (spec["ligand"] == "K57" and ccd_identity["formula"].replace(" ", "") != K57_FORMULA):
            raise MOLDISC018Error(f"CCD identity drift: {label}")
        grid = base.derive_redocking_grid(native)
        if grid.grid_hash != spec["grid_hash"]:
            raise MOLDISC018Error(f"grid hash drift: {label}: {grid.grid_hash}")
        receptor_pdbqt = directory / "receptor.pdbqt"
        preparation = moldisc017._prepare_receptor(receptor_pdb, receptor_pdbqt, obabel, timeout)
        state = {
            "label": label, "pdb_id": pdb_id, "ligand": spec["ligand"], "ligand_alias": spec["ligand_alias"],
            "ligand_author_chain": spec["ligand_author_chain"], "ligand_auth_seq_id": extraction.ligand_auth_seq_id,
            "receptor_author_chains": ["A", "B"], "resolution_angstrom": _pdb_resolution(text), "mutations": mutation_values,
            "inchikey": ccd_identity["inchikey"], "formula": rdMolDescriptors.CalcMolFormula(native), "ccd_identity": ccd_identity,
            "raw_pdb_transport_sha256": raw_sha, "native_sdf_transport_sha256": native_sha, "native_sdf_sha256": sha256_file(native_sdf),
            "native_sdf_rdkit_inchikey": inchi.MolToInchiKey(native), "receptor_pdb_sha256": sha256_file(receptor_pdb),
            "receptor_pdbqt_sha256": sha256_file(receptor_pdbqt), "grid": grid.to_dict(), "grid_hash": grid.grid_hash,
            "receptor_pdb_path": str(receptor_pdb), "receptor_pdbqt_path": str(receptor_pdbqt), "native_sdf_path": str(native_sdf),
            "docking_allowed": True,
        }
        state["state_hash"] = sha256_json({key: value for key, value in state.items() if not key.endswith("_path") and key != "state_hash"})
        _write_json(directory / "source_state.json", state)
        states[label] = state
    scientific_states = {label: {key: value for key, value in state.items() if not key.endswith("_path")} for label, state in states.items()}
    payload = {"schema_version": "research-os.molecular-discovery.moldisc018.source-audit.v1", "states": scientific_states, "source_contract": {"official_rcsb_resources_only": True, "native_identity_verified": True, "resolution_verified": True, "mutation_sets_verified": True, "chains_verified": True}, "k57_is_generated_candidate": False, "generated_candidate_is_k57": False, "experimental_activity_transfer_allowed": False}
    result = {**payload, "source_audit_hash": sha256_json(payload), "states_with_paths": states}
    _write_json(root / "source_audit.json", result)
    return result


def _prepare_ligand(label: str, native: Chem.Mol, seed: int, root: Path, obabel: OpenBabelEngine, timeout: float) -> dict[str, Any]:
    directory = root / "prepared" / label / f"etkdg_{seed}"
    directory.mkdir(parents=True, exist_ok=False)
    molecule = Chem.RemoveHs(Chem.Mol(native))
    sdf = directory / "starting_conformer.sdf"
    prepared = Chem.AddHs(Chem.Mol(molecule))
    params = AllChem.ETKDGv3(); params.randomSeed = int(seed)
    if AllChem.EmbedMolecule(prepared, params) != 0:
        raise MOLDISC018Error(f"ETKDGv3 failed for {label}/{seed}")
    if AllChem.UFFHasAllMoleculeParams(prepared):
        AllChem.UFFOptimizeMolecule(prepared, maxIters=1000)
    writer = Chem.SDWriter(str(sdf)); writer.write(prepared); writer.close()
    pdbqt = directory / "ligand.pdbqt"
    conversion = obabel.convert(sdf, pdbqt, options=("-h", "--partialcharge", "gasteiger"), timeout=timeout, protocol_id="moldisc018.ligand-openbabel.v1")
    if conversion.returncode != 0 or not pdbqt.is_file():
        raise MOLDISC018Error(f"ligand preparation failed: {label}/{seed}")
    return {"label": label, "etkdg_seed": seed, "sdf_path": str(sdf), "pdbqt_path": str(pdbqt), "sdf_sha256": sha256_file(sdf), "pdbqt_sha256": sha256_file(pdbqt), "ligand_scientific_identity": moldisc016._pdbqt_scientific_identity(pdbqt, f"{label} ligand"), "starting_molecule_inchikey": inchi.MolToInchiKey(molecule)}


def _run_vina(spec: Mapping[str, Any], root: Path, receptor: Mapping[str, Any], ligand: Mapping[str, Any], vina: VinaEngine) -> dict[str, Any]:
    run_root = root / "runs" / str(spec["run_id"]); run_root.mkdir(parents=True, exist_ok=False)
    _write_json(run_root / "protocol_parameters.json", dict(spec))
    output = run_root / "vina_poses.pdbqt"; grid = receptor["grid"]
    request = DockingRequest(receptor_path=receptor["receptor_pdbqt_path"], ligand_path=ligand["pdbqt_path"], grid=GridBox(grid["center_x"], grid["center_y"], grid["center_z"], grid["size_x"], grid["size_y"], grid["size_z"]), exhaustiveness=VINA_EXHAUSTIVENESS, cpu=VINA_CPU, seed=VINA_SEED, output_path=str(output), target_id=f"MOLDISC018:{spec['target']}", role=CAPABILITY_CONTEXT, protocol_id="research-os.moldisc-018.reciprocal-holo.v1", timeout=1200.0, num_modes=VINA_NUM_MODES)
    result = vina.run(request)
    record = {**dict(spec), "vina_version": vina.version, "technical_status": "PASS" if result.returncode == 0 and output.is_file() else "NONPASS", "engine_returncode": result.returncode, "output_path": str(output), "ligand_scientific_identity": ligand["ligand_scientific_identity"], "receptor_pdbqt_sha256": receptor["receptor_pdbqt_sha256"], "grid_hash": receptor["grid_hash"], "generation_executed": False, "generated_candidate_docking_executed": False, "candidate_selection_executed": False, "scores_used_for_success": False, "scores_used_for_pose_selection": False, "scores_used_for_capability_classification": False}
    if record["technical_status"] != "PASS":
        record.update({"first_loss": "EXECUTION_FAILED", "pose_count": 0, "pose_scores_kcal_mol": [], "pose_1_score_kcal_mol": None, "error": result.stderr[-4000:]})
    else:
        text = output.read_text(encoding="utf-8", errors="replace"); models = base.split_vina_pdbqt_models(text); scores = [float(value) for value in base.parse_vina_pose_scores(text)]
        if len(models) != len(scores) or not models or len(models) > VINA_NUM_MODES or any(not math.isfinite(value) for value in scores):
            record.update({"technical_status": "NONPASS", "first_loss": "NO_VALID_POSES", "pose_count": 0, "pose_scores_kcal_mol": [], "pose_1_score_kcal_mol": None})
        else:
            record.update({"first_loss": None, "pose_count": len(models), "pose_scores_kcal_mol": scores, "pose_1_score_kcal_mol": scores[0], "vina_output_scientific_hash": moldisc016._vina_scientific_identity(models, scores), "vina_output_transport_sha256": sha256_file(output)})
    _write_json(run_root / "run_manifest.json", record)
    return record


def _heavy_graph_coords(molecule: Chem.Mol) -> tuple[Chem.Mol, list[tuple[float, float, float]]]:
    heavy = base._heavy_atom_copy(molecule)
    graph = base._connectivity_graph(molecule)
    conf = heavy.GetConformer()
    coords = [(float(conf.GetAtomPosition(index).x), float(conf.GetAtomPosition(index).y), float(conf.GetAtomPosition(index).z)) for index in range(heavy.GetNumAtoms())]
    return graph, coords


def no_fit_symmetry_aware_rmsd(reference: Chem.Mol, predicted: Chem.Mol, reference_coords: Sequence[Sequence[float]] | None = None) -> dict[str, Any]:
    """Symmetry-aware heavy-atom RMSD without a ligand rigid-body fit."""
    try:
        ref_graph, ref_coords = _heavy_graph_coords(reference); pred_graph, pred_coords = _heavy_graph_coords(predicted)
    except ValueError as exc:
        return {"status": "ANALYSIS_INDETERMINATE", "rmsd_angstrom": None, "reason": str(exc)}
    if reference_coords is not None:
        ref_coords = [tuple(map(float, point)) for point in reference_coords]
    if ref_graph.GetNumAtoms() != pred_graph.GetNumAtoms() or ref_graph.GetNumBonds() != pred_graph.GetNumBonds():
        return {"status": "ANALYSIS_INDETERMINATE", "rmsd_angstrom": None, "reason": "heavy-atom graph size mismatch"}
    matches = pred_graph.GetSubstructMatches(ref_graph, uniquify=False)
    if not matches:
        return {"status": "ANALYSIS_INDETERMINATE", "rmsd_angstrom": None, "reason": "no element-labeled connectivity match"}
    values = []
    for match in matches:
        values.append(math.sqrt(sum(sum((ref_coords[index][axis] - pred_coords[match[index]][axis]) ** 2 for axis in range(3)) for index in range(len(match))) / len(match)))
    return {"status": "PASS", "rmsd_angstrom": min(values), "symmetry_match_count": len(matches), "reference_heavy_atoms": len(ref_coords), "predicted_heavy_atoms": len(pred_coords), "ligand_fit_applied": False}


def _transform_coords(molecule: Chem.Mol, alignment: Mapping[str, Any]) -> list[tuple[float, float, float]]:
    _, coords = _heavy_graph_coords(molecule)
    rotation = np.asarray(alignment["rotation"], dtype=float); translation = np.asarray(alignment["translation"], dtype=float)
    return ((rotation @ np.asarray(coords, dtype=float).T).T + translation).tolist()


def _alignment_from_pdbs(target: Path, moving: Path) -> dict[str, Any]:
    def ca(path: Path) -> dict[tuple[str, str, str, str], tuple[float, float, float]]:
        result = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("ATOM") and line[12:16].strip() == "CA" and line[21].strip() in {"A", "B"}:
                key = (line[21].strip(), line[22:26].strip(), line[26].strip(), line[17:20].strip())
                result[key] = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
        return result
    target_atoms, moving_atoms = ca(target), ca(moving)
    if set(target_atoms) != set(moving_atoms) or len(target_atoms) < 3:
        raise MOLDISC018Error("alignment lacks exact A/B author-residue identity correspondence")
    keys = sorted(target_atoms); p = np.asarray([moving_atoms[key] for key in keys], dtype=float); q = np.asarray([target_atoms[key] for key in keys], dtype=float)
    pre = float(np.sqrt(np.mean(np.sum((p - q) ** 2, axis=1))))
    pc, qc = p.mean(axis=0), q.mean(axis=0); u, _, vt = np.linalg.svd((p - pc).T @ (q - qc)); rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0: vt[-1, :] *= -1; rotation = vt.T @ u.T
    translation = qc - rotation @ pc; transformed = (rotation @ p.T).T + translation; post = float(np.sqrt(np.mean(np.sum((transformed - q) ** 2, axis=1))))
    payload = {"algorithm": "KABSCH", "chain_mapping": {"A": "A", "B": "B"}, "atom_selection": "C-alpha; same chain; same author residue number; same residue identity; C-alpha present in both", "atom_count": len(keys), "keys_hash": sha256_json(keys), "pre_alignment_rmsd_angstrom": pre, "post_alignment_rmsd_angstrom": post, "rotation": rotation.round(12).tolist(), "translation": translation.round(12).tolist()}
    return {**payload, "alignment_hash": sha256_json(payload)}


def kabsch_align(reference: Sequence[Sequence[float]], moving: Sequence[Sequence[float]]) -> dict[str, Any]:
    """Align moving receptor coordinates to reference coordinates.

    This helper is intentionally receptor-only.  The pose evaluator below
    never calls it for ligand coordinates.
    """
    p, q = np.asarray(moving, dtype=float), np.asarray(reference, dtype=float)
    if p.shape != q.shape or p.ndim != 2 or p.shape[1] != 3 or len(p) < 3:
        raise MOLDISC018Error("Kabsch requires equal Nx3 arrays with N>=3")
    pre = float(np.sqrt(np.mean(np.sum((p - q) ** 2, axis=1))))
    pc, qc = p.mean(axis=0), q.mean(axis=0)
    u, _, vt = np.linalg.svd((p - pc).T @ (q - qc))
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1
        rotation = vt.T @ u.T
    translation = qc - rotation @ pc
    transformed = (rotation @ p.T).T + translation
    post = float(np.sqrt(np.mean(np.sum((transformed - q) ** 2, axis=1))))
    return {"rotation": rotation.tolist(), "translation": translation.tolist(), "pre_alignment_rmsd_angstrom": pre, "post_alignment_rmsd_angstrom": post, "atom_count": len(p)}


def _load_pose_models(record: Mapping[str, Any], root: Path, obabel: OpenBabelEngine) -> list[Chem.Mol]:
    output = record.get("output_path")
    if not output or not Path(output).is_file():
        return []
    source = Path(output); directory = root / "converted-poses" / source.parent.name; directory.mkdir(parents=True, exist_ok=True)
    result = []
    for index, model in enumerate(base.split_vina_pdbqt_models(source.read_text(encoding="utf-8", errors="replace")), start=1):
        sdf = directory / f"pose-{index:02d}.sdf"
        if not sdf.is_file():
            pdbqt = directory / f"pose-{index:02d}.pdbqt"; pdbqt.write_text(model, encoding="utf-8")
            conversion = obabel.convert(pdbqt, sdf, timeout=120.0, protocol_id="moldisc018.pose-openbabel.v1")
            if conversion.returncode != 0 or not sdf.is_file(): continue
        try: result.append(base.load_single_sdf(sdf))
        except (OSError, ValueError): continue
    return result


def _metrics(record: Mapping[str, Any], reference: Chem.Mol, reference_coords: Sequence[Sequence[float]] | None, root: Path, obabel: OpenBabelEngine) -> dict[str, Any]:
    poses = _load_pose_models(record, root, obabel); values = [no_fit_symmetry_aware_rmsd(reference, pose, reference_coords) for pose in poses]
    valid = [(index + 1, item["rmsd_angstrom"]) for index, item in enumerate(values) if item.get("rmsd_angstrom") is not None]
    minimum = min(valid, key=lambda item: item[1]) if valid else (None, None)
    return {"technical_status": record.get("technical_status"), "rank1_rmsd_angstrom": values[0].get("rmsd_angstrom") if values else None, "minimum_rmsd_angstrom": minimum[1], "minimum_pose_rank": minimum[0], "pose_count": len(poses), "pose_scores_kcal_mol": record.get("pose_scores_kcal_mol", []), "rank1_success": bool(values and values[0].get("rmsd_angstrom") is not None and values[0]["rmsd_angstrom"] <= SUCCESS_THRESHOLD), "any_pose_success": bool(minimum[1] is not None and minimum[1] <= SUCCESS_THRESHOLD), "pose_analysis": values, "scores_used_for_success": False, "scores_used_for_pose_selection": False, "scores_used_for_capability_classification": False}


def _failure_class(metrics: Mapping[str, Any]) -> str:
    if metrics.get("technical_status") != "PASS": return "EXECUTION_FAILED"
    rank1, minimum = metrics.get("rank1_rmsd_angstrom"), metrics.get("minimum_rmsd_angstrom")
    if rank1 is None or minimum is None: return "ANALYSIS_INDETERMINATE"
    if rank1 <= SUCCESS_THRESHOLD: return "RANK1_NEAR_NATIVE"
    if minimum <= SUCCESS_THRESHOLD: return "NEAR_NATIVE_POSE_MISRANKED"
    return "NO_NEAR_NATIVE_POSE_RETURNED"


def _case_map(config: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {case["case_id"]: case for case in config["cases"]}


def _profile_append(profile_path: Path, evidence: Mapping[str, Any]) -> dict[str, Any]:
    profile = _load_json(profile_path); old_id, old_hash = profile_identity_from_mapping(profile)
    sources = [item for item in profile.get("evidence_sources", []) if item.get("source_id") != CAPABILITY_SOURCE_ID]
    sources.append(dict(evidence))
    profile["evidence_sources"] = sources
    for context in profile.get("contexts", []):
        if context.get("context_id") == CAPABILITY_CONTEXT:
            context["classification"] = "PARTIALLY_VALIDATED"
            context["evidence_source_ids"] = ["CROSSDOCK-001", CAPABILITY_SOURCE_ID]
    new_id, new_hash = profile_identity_from_mapping(profile)
    profile["profile_id"], profile["profile_hash"] = new_id, new_hash
    _write_json(profile_path, profile)
    return {"profile_path": str(profile_path), "old_profile_id": old_id, "old_profile_hash": old_hash, "new_profile_id": new_id, "new_profile_hash": new_hash, "classification_after_campaign": "PARTIALLY_VALIDATED", "evidence_source_ids": ["CROSSDOCK-001", CAPABILITY_SOURCE_ID]}


def run_moldisc_018(*, config_path: str | Path, output_root: str | Path, timeout: float = 120.0, source_audit_only: bool = False, update_profile: bool = True) -> dict[str, Any]:
    config = _load_json(config_path) if source_audit_only else load_program_config_v18(config_path)
    root = Path(output_root); root.mkdir(parents=True, exist_ok=False)
    _write_json(root / "program_protocol_payload.json", config)
    source = run_source_audit(config_path, root, timeout=timeout)
    if source_audit_only:
        return {"program_id": PROGRAM_ID, "program_protocol_hash": protocol_hash(config), "source_audit_hash": source["source_audit_hash"], "source_audit_only": True}
    plan = build_execution_plan(config); obabel = OpenBabelEngine(); vina = VinaEngine()
    if not obabel.available or not vina.available or not vina.version or VINA_VERSION not in vina.version:
        raise MOLDISC018Error("Open Babel and AutoDock Vina 1.2.7 are required")
    native = {label: base.load_single_sdf(state["native_sdf_path"]) for label, state in source["states_with_paths"].items()}
    prepared = {(label, seed): _prepare_ligand(label.split("_")[0], molecule, seed, root, obabel, timeout) for label, molecule in (("K57", native["K57_BACKGROUND"]), ("JE2", native["JE2_BACKGROUND"])) for seed in ETKDG_SEEDS}
    records: dict[str, Any] = {}
    receptor_by_label = source["states_with_paths"]
    ligand_by_run = {}
    for spec in plan:
        ligand_label = "K57" if spec["ligand"] == "K57" else "JE2"
        ligand_by_run[spec["run_id"]] = prepared[(ligand_label, spec["etkdg_seed"])]
    def execute(spec: Mapping[str, Any]) -> dict[str, Any]:
        target = receptor_by_label[spec["target"]]
        return _run_vina(spec, root, target, ligand_by_run[spec["run_id"]], VinaEngine())
    workers = max(1, min(4, int(os.environ.get("MOLDISC018_MAX_WORKERS", "4"))))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="moldisc018-vina") as executor:
        futures = {item["run_id"]: executor.submit(execute, item) for item in plan}
        for item in plan: records[item["run_id"]] = futures[item["run_id"]].result()
    alignments = {
        "BACKGROUND": _alignment_from_pdbs(Path(receptor_by_label["JE2_BACKGROUND"]["receptor_pdb_path"]), Path(receptor_by_label["K57_BACKGROUND"]["receptor_pdb_path"])),
        "MUTANT": _alignment_from_pdbs(Path(receptor_by_label["JE2_MUTANT"]["receptor_pdb_path"]), Path(receptor_by_label["K57_MUTANT"]["receptor_pdb_path"])),
    }
    reverse_alignments = {
        "BACKGROUND": _alignment_from_pdbs(Path(receptor_by_label["K57_BACKGROUND"]["receptor_pdb_path"]), Path(receptor_by_label["JE2_BACKGROUND"]["receptor_pdb_path"])),
        "MUTANT": _alignment_from_pdbs(Path(receptor_by_label["K57_MUTANT"]["receptor_pdb_path"]), Path(receptor_by_label["JE2_MUTANT"]["receptor_pdb_path"])),
    }
    alignments_payload = {"background_je2_target": alignments["BACKGROUND"], "background_k57_target": reverse_alignments["BACKGROUND"], "mutant_je2_target": alignments["MUTANT"], "mutant_k57_target": reverse_alignments["MUTANT"], "background_receptor_post_alignment_rmsd": alignments["BACKGROUND"]["post_alignment_rmsd_angstrom"], "mutant_receptor_post_alignment_rmsd": alignments["MUTANT"]["post_alignment_rmsd_angstrom"]}
    _write_json(root / "receptor_alignment.json", alignments_payload)
    reference_coords = {
        "RX-01": _transform_coords(native["K57_BACKGROUND"], alignments["BACKGROUND"]),
        "RX-02": _transform_coords(native["JE2_BACKGROUND"], reverse_alignments["BACKGROUND"]),
        "RX-03": _transform_coords(native["K57_MUTANT"], alignments["MUTANT"]),
        "RX-04": _transform_coords(native["JE2_MUTANT"], reverse_alignments["MUTANT"]),
    }
    reference_pose_transfer = {case_id: {"reference_state": _case_map(config)[case_id]["reference"], "target_state": _case_map(config)[case_id]["target"], "transformed_heavy_atom_count": len(coords), "reference_transform_alignment_hash": (alignments["BACKGROUND"] if case_id in {"RX-01", "RX-02"} else alignments["MUTANT"])["alignment_hash"], "ligand_fit_applied": False, "coordinates_hash": sha256_json(coords)} for case_id, coords in reference_coords.items()}
    _write_json(root / "reference_pose_transfer.json", reference_pose_transfer)
    metrics: dict[str, Any] = {}
    for spec in plan:
        if spec["kind"] == "K57_COGNATE_REDOCK":
            reference = native[spec["reference"]]; coords = None
        else:
            reference = native[spec["reference"]]; coords = reference_coords[spec["case_id"]]
        metrics[spec["run_id"]] = _metrics(records[spec["run_id"]], reference, coords, root, obabel)
        metrics[spec["run_id"]]["failure_class"] = _failure_class(metrics[spec["run_id"]])
    k57 = {label: {rep: {**metrics[f"{label}__cognate__{rep}"], "case_id": label} for rep in ("RUN_A", "RUN_B")} for label in ("K57_BACKGROUND", "K57_MUTANT")}
    _write_json(root / "k57_redocking.json", {"controls": k57, "threshold_angstrom": SUCCESS_THRESHOLD, "symmetry_aware": True, "ligand_fit_applied": False, "scientific_hash": sha256_json(k57)})
    matrix = {}
    for case in _case_map(config).values():
        primary = metrics[f"{case['case_id']}__etkdg_42__RUN_A"]
        matrix[case["case_id"]] = {"case_id": case["case_id"], "ligand": case["ligand"], "target_receptor": case["target"], "reference_receptor": case["reference"], "mutation_state": case["mutation_state"], "rank1_rmsd_angstrom": primary["rank1_rmsd_angstrom"], "minimum_rmsd_angstrom": primary["minimum_rmsd_angstrom"], "minimum_pose_rank": primary["minimum_pose_rank"], "rank1_success": primary["rank1_success"], "any_pose_success": primary["any_pose_success"], "failure_classification": primary["failure_class"], "scores_used_for_success": False, "scores_used_for_pose_selection": False, "scores_used_for_capability_classification": False}
    background = {key: value for key, value in matrix.items() if key in {"RX-01", "RX-02"}}; mutant = {key: value for key, value in matrix.items() if key in {"RX-03", "RX-04"}}
    _write_json(root / "background_reciprocal_crossdock.json", {"cases": background, "primary_sample_size": 2, "scientific_hash": sha256_json(background)})
    _write_json(root / "mutant_reciprocal_crossdock.json", {"cases": mutant, "primary_sample_size": 2, "scientific_hash": sha256_json(mutant)})
    _write_json(root / "reciprocal_pose_recovery_matrix.json", {"case_order": ["RX-01", "RX-02", "RX-03", "RX-04"], "cases": [matrix[key] for key in ("RX-01", "RX-02", "RX-03", "RX-04")], "threshold_angstrom": SUCCESS_THRESHOLD, "scientific_hash": sha256_json(matrix)})
    primary_values = list(matrix.values()); rank1_success = sum(item["rank1_success"] for item in primary_values); any_success = sum(item["any_pose_success"] for item in primary_values)
    failure_counts = {name: sum(item["failure_classification"] == name for item in primary_values) for name in ("NEAR_NATIVE_POSE_MISRANKED", "NO_NEAR_NATIVE_POSE_RETURNED", "ANALYSIS_INDETERMINATE", "EXECUTION_FAILED")}
    failure = {"threshold_angstrom": SUCCESS_THRESHOLD, "primary_sample_size": 4, "rank1_success_count": rank1_success, "any_pose_success_count": any_success, "misranking_count": failure_counts["NEAR_NATIVE_POSE_MISRANKED"], "sampling_failure_count": failure_counts["NO_NEAR_NATIVE_POSE_RETURNED"], "indeterminate_count": failure_counts["ANALYSIS_INDETERMINATE"] + failure_counts["EXECUTION_FAILED"], "cases": {key: value["failure_classification"] for key, value in matrix.items()}, "vocabulary": ["RANK1_NEAR_NATIVE", "NEAR_NATIVE_POSE_MISRANKED", "NO_NEAR_NATIVE_POSE_RETURNED", "ANALYSIS_INDETERMINATE", "EXECUTION_FAILED"]}
    _write_json(root / "failure_decomposition.json", {**failure, "scientific_hash": sha256_json(failure)})
    robustness = {}
    for case in _case_map(config).values():
        rows = []
        for seed in ETKDG_SEEDS:
            run_a = metrics[f"{case['case_id']}__etkdg_{seed}__RUN_A"]; run_b = metrics.get(f"{case['case_id']}__etkdg_{seed}__RUN_B")
            rows.append({"seed": seed, "run_a_rank1_rmsd_angstrom": run_a["rank1_rmsd_angstrom"], "run_a_minimum_rmsd_angstrom": run_a["minimum_rmsd_angstrom"], "run_a_minimum_pose_rank": run_a["minimum_pose_rank"], "run_a_failure_class": run_a["failure_class"], "run_a_rank1_success": run_a["rank1_success"], "run_a_any_pose_success": run_a["any_pose_success"], "run_b_scientific_identity_equal": (records[f"{case['case_id']}__etkdg_{seed}__RUN_A"].get("vina_output_scientific_hash") == records[f"{case['case_id']}__etkdg_{seed}__RUN_B"].get("vina_output_scientific_hash")) if run_b else None})
        robustness[case["case_id"]] = rows
    _write_json(root / "conformer_robustness.json", {"cases": robustness, "primary_sample_size": 4, "diagnostic_conformers": [42, 1337, 2025], "scientific_hash": sha256_json(robustness)})
    direction = {"BACKGROUND": {"rank1_rmsd_difference_RX01_minus_RX02": matrix["RX-01"]["rank1_rmsd_angstrom"] - matrix["RX-02"]["rank1_rmsd_angstrom"], "minimum_rmsd_difference_RX01_minus_RX02": matrix["RX-01"]["minimum_rmsd_angstrom"] - matrix["RX-02"]["minimum_rmsd_angstrom"], "failure_classes": [matrix["RX-01"]["failure_classification"], matrix["RX-02"]["failure_classification"]]}, "MUTANT": {"rank1_rmsd_difference_RX03_minus_RX04": matrix["RX-03"]["rank1_rmsd_angstrom"] - matrix["RX-04"]["rank1_rmsd_angstrom"], "minimum_rmsd_difference_RX03_minus_RX04": matrix["RX-03"]["minimum_rmsd_angstrom"] - matrix["RX-04"]["minimum_rmsd_angstrom"], "failure_classes": [matrix["RX-03"]["failure_classification"], matrix["RX-04"]["failure_classification"]]}, "name": "RECIPROCAL_DIRECTIONAL_DIFFERENCE"}
    state_change = {"K57_to_JE2": {"rank1_rmsd_change_mutant_minus_background": matrix["RX-03"]["rank1_rmsd_angstrom"] - matrix["RX-01"]["rank1_rmsd_angstrom"], "minimum_rmsd_change_mutant_minus_background": matrix["RX-03"]["minimum_rmsd_angstrom"] - matrix["RX-01"]["minimum_rmsd_angstrom"], "failure_class_transition": [matrix["RX-01"]["failure_classification"], matrix["RX-03"]["failure_classification"]]}, "JE2_to_K57": {"rank1_rmsd_change_mutant_minus_background": matrix["RX-04"]["rank1_rmsd_angstrom"] - matrix["RX-02"]["rank1_rmsd_angstrom"], "minimum_rmsd_change_mutant_minus_background": matrix["RX-04"]["minimum_rmsd_angstrom"] - matrix["RX-02"]["minimum_rmsd_angstrom"], "failure_class_transition": [matrix["RX-02"]["failure_classification"], matrix["RX-04"]["failure_classification"]]}, "name": "RECEPTOR_STATE_LOCALIZATION_CHANGE"}
    _write_json(root / "capability_evidence.json", {"context": CAPABILITY_CONTEXT, "benchmark_id": CAPABILITY_BENCHMARK_ID, "sample_size": 4, "crossdock001_reference": {"rank1": "3/10", "any_pose": "5/10", "pooled": False}, "primary_performance": {"rank1_success_count": rank1_success, "rank1_denominator": 4, "any_pose_success_count": any_success, "any_pose_denominator": 4, "threshold_angstrom": SUCCESS_THRESHOLD, **failure_counts}, "directional_difference": direction, "receptor_state_localization_change": state_change, "classification_after_campaign": "PARTIALLY_VALIDATED", "evidence_level": "E2_COMPUTATIONAL", "scientific_hash": sha256_json({"matrix": matrix, "failure": failure, "direction": direction, "state_change": state_change})})
    _write_json(root / "capability_profile_update.json", {"source_id": CAPABILITY_SOURCE_ID, "benchmark_id": CAPABILITY_BENCHMARK_ID, "classification_after_campaign": "PARTIALLY_VALIDATED", "profile_update_pending": True})
    k57_hash = sha256_json(k57); background_hash = sha256_json(background); mutant_hash = sha256_json(mutant); alignment_hash = sha256_json(alignments_payload); pose_hash = sha256_json(matrix); failure_hash = sha256_json(failure); robustness_hash = sha256_json(robustness); evidence_hash = _load_json(root / "capability_evidence.json")["scientific_hash"]
    source_hash = source["source_audit_hash"]
    synthesis = {"evidence_ceiling": "E2_COMPUTATIONAL", "capability_context": CAPABILITY_CONTEXT, "question": "reciprocal holo cross-docking pose recovery and sampling-versus-ranking decomposition", "claims": {"CLAIM-018-01": "SUPPORTS" if all(item["technical_status"] == "PASS" for label in k57.values() for item in label.values()) else "INDETERMINATE", "CLAIM-018-02": "SUPPORTS" if any_success >= 1 else "CONTRADICTS", "CLAIM-018-03": "SUPPORTS" if any_success == 4 else "CONTRADICTS", "CLAIM-018-04": "SUPPORTS" if rank1_success == 4 else "CONTRADICTS", "CLAIM-018-05": "SUPPORTS" if all(item["failure_classification"] in failure["vocabulary"] for item in primary_values) else "INDETERMINATE", "CLAIM-018-06": "SUPPORTS" if all(row.get("run_b_scientific_identity_equal") is True for rows in robustness.values() for row in rows if row["seed"] == 42) else "INDETERMINATE"}, "scores_used_for_success": False, "scores_used_for_pose_selection": False, "scores_used_for_capability_classification": False, "molecule_generation_executed": False, "generated_candidate_docking_executed": False, "candidate_selection_executed": False, "lead_selection_executed": False, "no_affinity_inference": True, "no_experimental_truth": True, "no_universal_validation": True, "candidate_docking_paused_reason": "MOLDISC-016/017 produced substantial candidate-specific computational evidence, but candidate interpretation depends on a partially validated non-cognate holo cross-docking capability. MOLDISC-018 therefore spends the next computation budget on known experimental structures rather than additional generated chemistry."}
    knowledge = {"evidence_ids": [CAPABILITY_SOURCE_ID], "gap_assessment": {"GAP-NONCOGNATE-CAPABILITY": "PARTIALLY_RESOLVED", "GAP-RANKING-VS-SAMPLING": "DIRECTLY_TARGETED", "GAP-EXPERIMENTAL-BINDING-VALIDATION": "UNRESOLVED"}, "summary": "MOLDISC-018 directly characterizes reciprocal non-cognate holo pose recovery and separates ranking from sampling failures while keeping the capability classification PARTIALLY_VALIDATED and experimental binding unresolved."}
    hashes = {"source_audit_hash": source_hash, "k57_redock_hash": k57_hash, "background_crossdock_hash": background_hash, "mutant_crossdock_hash": mutant_hash, "alignment_hash": alignment_hash, "pose_recovery_hash": pose_hash, "failure_decomposition_hash": failure_hash, "conformer_robustness_hash": robustness_hash, "capability_evidence_hash": evidence_hash, "synthesis_hash": sha256_json(synthesis)}
    scientific = {"program_id": PROGRAM_ID, "program_version": PROGRAM_VERSION, "program_protocol_hash": protocol_hash(config), "parent_moldisc017_hash": PARENT_MOLDISC017_HASH, "source_audit_hash": source_hash, "hashes": hashes, "primary_case_count": 4, "rank1_success_count": rank1_success, "any_pose_success_count": any_success, "failure_counts": failure_counts, "alignment_post_fit_rmsd": {"background": alignments["BACKGROUND"]["post_alignment_rmsd_angstrom"], "mutant": alignments["MUTANT"]["post_alignment_rmsd_angstrom"]}, "generation_executed": False, "generated_candidate_docking_executed": False, "candidate_selection_executed": False, "lead_selection_executed": False, "evidence_ceiling": "E2_COMPUTATIONAL", "capability_classification": "PARTIALLY_VALIDATED", "records": [{key: value for key, value in records[item["run_id"]].items() if not key.endswith("_path")} for item in plan]}
    program_hash = sha256_json(scientific)
    profile_update = None
    if update_profile:
        evidence_entry = {"source_id": CAPABILITY_SOURCE_ID, "benchmark_id": CAPABILITY_BENCHMARK_ID, "protocol_id": "research-os.moldisc-018.reciprocal-holo.v1", "protocol_hash": protocol_hash(config), "protocol_hash_status": "DECLARED", "run_or_result_identity": f"scientific_result_hash:{evidence_hash}", "scientific_result_hash": evidence_hash, "sample_size": 4, "endpoint": "receptor-aligned symmetry-aware heavy-atom pose localization in matched reciprocal non-cognate holo receptors", "primary_performance": {"rank_1_success_count": rank1_success, "rank_1_denominator": 4, "any_returned_pose_success_count": any_success, "any_returned_pose_denominator": 4, "threshold_angstrom": SUCCESS_THRESHOLD, "misranking_count": failure_counts["NEAR_NATIVE_POSE_MISRANKED"], "sampling_failure_count": failure_counts["NO_NEAR_NATIVE_POSE_RETURNED"], "indeterminate_count": failure_counts["ANALYSIS_INDETERMINATE"] + failure_counts["EXECUTION_FAILED"]}, "limitations": ["single protein family", "only two ligand identities", "two matched receptor states", "known pocket", "rigid receptors", "small benchmark", "not affinity or biological validation", "not pooled automatically with CROSSDOCK-001"]}
        profile_update = _profile_append(Path("configs/docking-capability-profile-v1.json"), evidence_entry)
        _write_json(root / "capability_profile_update.json", {**profile_update, "source_id": CAPABILITY_SOURCE_ID, "benchmark_id": CAPABILITY_BENCHMARK_ID})
    _write_json(root / "capability_evidence.json", {**_load_json(root / "capability_evidence.json"), "profile_update": profile_update})
    _write_json(root / "program_synthesis.json", {**synthesis, "scientific_hash": hashes["synthesis_hash"]})
    _write_json(root / "knowledge_gain.json", {**knowledge, "scientific_hash": sha256_json(knowledge)})
    manifest = {"schema_version": "research-os.molecular-discovery.megacampaign-result.v1", "program_id": PROGRAM_ID, "program_version": PROGRAM_VERSION, "status": "CLOSED_FIRST_RESULT_PRESERVED", "program_protocol_hash": protocol_hash(config), "program_scientific_hash": program_hash, "docking_runs_planned": EXPECTED_DOCKING_RUNS, "docking_runs_executed": sum(record.get("technical_status") in {"PASS", "NONPASS"} for record in records.values()), "docking_runs_skipped": sum(record.get("technical_status") not in {"PASS", "NONPASS"} for record in records.values()), "docking_runs_nonpass": sum(record.get("technical_status") != "PASS" for record in records.values()), "generation_executed": False, "generated_candidate_docking_executed": False, "candidate_selection_executed": False, "lead_selection_executed": False, "evidence_ceiling": "E2_COMPUTATIONAL", "capability_classification": "PARTIALLY_VALIDATED", "hashes": hashes}
    validation = {**manifest, "source_audit": source, "k57_redocking": k57, "reciprocal_pose_recovery_matrix": matrix, "failure_decomposition": failure, "conformer_robustness": robustness, "receptor_alignment": alignments_payload, "reference_pose_transfer": reference_pose_transfer, "claims": synthesis["claims"], "knowledge_gain": knowledge, "profile_update": profile_update, "negative_results": {"affinity_inference": False, "efficacy_inference": False, "experimental_truth_claim": False, "universal_validation": False, "k57_is_generated_candidate": False, "generated_candidate_is_k57": False, "experimental_activity_transferred": False}, "new_docking_runs": {"planned": EXPECTED_DOCKING_RUNS, "executed": manifest["docking_runs_executed"], "skipped": manifest["docking_runs_skipped"], "nonpass": manifest["docking_runs_nonpass"]}}
    _write_json(root / "program_manifest.json", manifest); _write_json(root / "program_scientific_payload.json", scientific); _write_json(root / "moldisc-018-first-run-v1.json", validation)
    report = "# MOLDISC-018 first result\n\nReciprocal holo cross-docking is an E2 computational capability benchmark. Scores are provenance only; no affinity, biological, or candidate claim is made.\n"
    (root / "program_report.md").write_text(report, encoding="utf-8")
    return {**manifest, "validation_file": str(root / "moldisc-018-first-run-v1.json"), "profile_update": profile_update}
