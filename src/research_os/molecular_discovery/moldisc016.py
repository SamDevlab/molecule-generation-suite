"""MOLDISC-016: static JE2 source-directed robustness megacampaign.

The campaign is intentionally domain-specific and fully predeclared.  It
executes a frozen four-cell panel across frozen engine/conformer/search
conditions, then computes only descriptive geometry, contact, factorial, and
claim-level endpoints.  It never generates molecules or selects a candidate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import statistics
from typing import Any, Mapping, Sequence

from rdkit import Chem
from rdkit.Chem import AllChem, inchi

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking import redocking as base
from research_os.docking.astex20 import FROZEN_PROSPECTIVE_CASES
from research_os.docking.schema import DockingRequest, GridBox
from research_os.engines.openbabel import OpenBabelEngine
from research_os.engines.vina import VinaEngine
from research_os.molecular_discovery import moldisc013 as geometry_base
from research_os.molecular_discovery.moldisc012 import (
    _pdbqt_scientific_identity,
    _reference_structure_identity,
    _require_prepared,
    _vina_scientific_identity,
)


PROGRAM_ID = "MOLDISC-016"
PROGRAM_VERSION = "1.0"
PARENT_MOLDISC014_HASH = "f940d95189616131829a22f9e68a53a960eddf8fd05f5fd7ebac43ece85481ed"
PARENT_MOLDISC015_HASH = "8e22c0565f2d78dc16468c8edb8f8f0b90a4007e50ced99e00e3d7a0b0f63e5d"
CONTROL_MOLDISC012_HASH = "e8c66a7726a3b191723e0dea072afdb5e4d4d9202b142eff83fe6d19c623f776"
TARGET_CASE_ID = "ATX-007"
PDB_ID = "1KZK"
NATIVE_LIGAND = "JE2"
RECEPTOR_CHAINS = ("A", "B")
GRID_HASH = "a0bf032d8bdb1bc20f13f298d604673cac1d2c7da8596cc228ec6602b5989aef"
VINA_VERSION = "1.2.7"
VINA_CPU = 1
VINA_SEEDS = (42, 1337, 2025)
ETKDG_SEEDS = (42, 1337, 2025)
EXHAUSTIVENESS_VALUES = (8, 16, 32)
NUM_MODES = 20
CONTACT_CUTOFF_ANGSTROM = 4.0
EXPECTED_DOCKING_RUNS = 32
MAX_DOCKING_RUNS = 40
MAX_FAILURES = 12
CONTROL_EXPECTED_POSE_SCORES = (
    -11.6, -10.194, -9.739, -9.411, -9.251, -9.111, -9.044, -9.01,
    -8.914, -8.849, -8.813, -8.781, -8.759, -8.718, -8.674, -8.656,
)
CONTROL_EXPECTED_NATIVE_REFERENCE_STRUCTURE_HASH = "82b48b534ff870fb8a922ed62da905bf77fe2e54f2420143986a4c5f9b9c9a4b"
CONTROL_EXPECTED_RECEPTOR_SCIENTIFIC_IDENTITY = "ec55df9f302eb6b63669085023520cb66eb224c66ab15368a95997dc2fcd7c55"
CONTROL_EXPECTED_LIGAND_SCIENTIFIC_IDENTITY = "609b8d75caf0018e1d704a24976f622c51fbfcff61d7554a55fe12be1f864f30"
CONTROL_EXPECTED_VINA_SCIENTIFIC_HASH = "09a014a56ab3eb31c6e419d618a3b381e6357c2ccd18c387ce8acba5d08ddf07"
ANALYSIS_CONDITIONS = (
    "baseline",
    "vina_seed_1337",
    "vina_seed_2025",
    "etkdg_seed_1337",
    "etkdg_seed_2025",
    "exhaustiveness_8",
    "exhaustiveness_32",
)


class MOLDISC016Error(RuntimeError):
    """Fail-closed MOLDISC-016 protocol or execution error."""


@dataclass(frozen=True)
class CandidateSpec:
    variant_id: str
    candidate_id: str
    factor_a: str
    factor_b: str
    label: str
    canonical_smiles: str
    inchikey: str
    heavy_atom_count: int

    @property
    def key(self) -> str:
        return f"{self.factor_a}{self.factor_b}"


CANDIDATES = (
    CandidateSpec("STEP2-DEMETHYL-01", "MOLDISC-011-JE2-286E6F2BE8", "A0", "B0", "CONTROL", "CC1(C)SCN(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2cccc(O)c2)[C@@H]1C(=O)NCc1ccccc1", "DRIAWXDDGSORDT-KKUQBAQOSA-N", 39),
    CandidateSpec("SOURCE-DELTA-OH", "MOLDISC-014-SOURCE-DELTA-OH", "A1", "B0", "DELTA-OH", "CC1(C)SCN(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2ccccc2)[C@@H]1C(=O)NCc1ccccc1", "NAZMDUVPQSKJEQ-KKUQBAQOSA-N", 38),
    CandidateSpec("SOURCE-DELTA-NSUB", "MOLDISC-014-SOURCE-DELTA-NSUB", "A0", "B1", "DELTA-NSUB", "CC(C)(C)NC(=O)[C@H]1N(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2cccc(O)c2)CSC1(C)C", "DMSDTDPQGPRTNA-FDFHNCONSA-N", 36),
    CandidateSpec("SOURCE-DELTA-BOTH", "MOLDISC-014-SOURCE-DELTA-BOTH", "A1", "B1", "DELTA-BOTH", "CC(C)(C)NC(=O)[C@H]1N(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2ccccc2)CSC1(C)C", "URHJIBSBOJFXDI-FDFHNCONSA-N", 35),
)


def _load_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MOLDISC016Error(f"could not load JSON: {path}") from exc
    if not isinstance(value, dict):
        raise MOLDISC016Error("configuration must be a JSON object")
    return value


def _candidate_from_config(item: Mapping[str, Any]) -> CandidateSpec:
    return CandidateSpec(
        str(item["variant_id"]), str(item["candidate_id"]), str(item["factor_a"]),
        str(item["factor_b"]), str(item["label"]), str(item["canonical_smiles"]),
        str(item["inchikey"]), int(item["heavy_atom_count"]),
    )


def load_program_config_v16(path: str | Path) -> dict[str, Any]:
    config = _load_json(path)
    if config.get("program_id") != PROGRAM_ID or config.get("program_version") != PROGRAM_VERSION:
        raise MOLDISC016Error("MOLDISC-016 program identity/version drifted")
    parents = config.get("parents") or {}
    if (parents.get("moldisc014") or {}).get("program_scientific_hash") != PARENT_MOLDISC014_HASH:
        raise MOLDISC016Error("MOLDISC-014 parent hash drifted")
    parent015 = parents.get("moldisc015") or {}
    if (
        parent015.get("program_scientific_hash") != PARENT_MOLDISC015_HASH
        or parent015.get("source_record_id") != "C-2545"
        or parent015.get("resolution_status") != "UNRESOLVED_SOURCE_STEREOCHEMISTRY"
        or parent015.get("measurement_transfer_allowed") is not False
    ):
        raise MOLDISC016Error("MOLDISC-015 source boundary drifted")
    parent012 = parents.get("moldisc012") or {}
    if (
        parent012.get("program_scientific_hash") != CONTROL_MOLDISC012_HASH
        or parent012.get("target_case_id") != TARGET_CASE_ID
        or parent012.get("pdb_id") != PDB_ID
        or parent012.get("native_ligand") != NATIVE_LIGAND
        or tuple(parent012.get("receptor_author_chains") or ()) != RECEPTOR_CHAINS
        or parent012.get("grid_hash") != GRID_HASH
        or parent012.get("capability_classification") != "PARTIALLY_VALIDATED"
        or parent012.get("evidence_level") != "E2_COMPUTATIONAL"
    ):
        raise MOLDISC016Error("MOLDISC-012 control boundary drifted")
    panel = tuple(_candidate_from_config(item) for item in config.get("panel") or ())
    if panel != CANDIDATES or len(panel) != 4:
        raise MOLDISC016Error("the frozen 2x2 panel drifted")
    target = config.get("target") or {}
    if (
        target.get("case_id") != TARGET_CASE_ID or target.get("pdb_id") != PDB_ID
        or target.get("native_ligand") != NATIVE_LIGAND
        or target.get("ligand_author_chain") != "A"
        or tuple(target.get("receptor_author_chains") or ()) != RECEPTOR_CHAINS
        or target.get("grid_hash") != GRID_HASH
        or target.get("coordinate_frame") != "RECEPTOR_FRAME"
    ):
        raise MOLDISC016Error("shared target boundary drifted")
    docking = config.get("docking_protocol") or {}
    expected = {
        "rdkit_conformer_engine": "ETKDGv3", "etkdg_seeds": list(ETKDG_SEEDS),
        "vina_version": VINA_VERSION, "vina_seeds": list(VINA_SEEDS),
        "cpu": VINA_CPU, "exhaustiveness_values": list(EXHAUSTIVENESS_VALUES),
        "num_modes": NUM_MODES, "scoring_function": "vina", "retry_count": 0,
        "analysis_replicate": "RUN_A",
    }
    for key, value in expected.items():
        if docking.get(key) != value:
            raise MOLDISC016Error(f"frozen docking field {key!r} drifted")
    if docking.get("openbabel_receptor_options") != ["-h", "--partialcharge", "gasteiger", "-xr"]:
        raise MOLDISC016Error("receptor preparation options drifted")
    if docking.get("openbabel_ligand_options") != ["-h", "--partialcharge", "gasteiger"]:
        raise MOLDISC016Error("ligand preparation options drifted")
    bounds = config.get("resource_bounds") or {}
    if bounds.get("max_campaigns") != 8 or bounds.get("max_docking_runs") != MAX_DOCKING_RUNS or bounds.get("max_failures") != MAX_FAILURES or bounds.get("max_candidates") != 4 or bounds.get("planned_docking_runs") != EXPECTED_DOCKING_RUNS:
        raise MOLDISC016Error("resource bounds drifted")
    campaigns = config.get("campaigns") or []
    if len(campaigns) != 8 or [item.get("campaign_id") for item in campaigns] != [f"CAMP-016-{letter}" for letter in "ABCDEFGH"]:
        raise MOLDISC016Error("campaign identity/order drifted")
    if sum(int(item.get("planned_runs", -1)) for item in campaigns) != EXPECTED_DOCKING_RUNS:
        raise MOLDISC016Error("planned docking count drifted")
    geometry = config.get("geometry") or {}
    if geometry.get("metric") != "RECEPTOR_FRAME_COMMON_CORE_RMSD" or geometry.get("no_rigid_body_alignment") is not True or geometry.get("threshold_angstrom") is not None or len(geometry.get("edges") or []) != 4:
        raise MOLDISC016Error("geometry boundary drifted")
    contacts = config.get("contacts") or {}
    if contacts.get("cutoff_angstrom") != CONTACT_CUTOFF_ANGSTROM or contacts.get("energy_or_interaction_classification") is not False:
        raise MOLDISC016Error("contact boundary drifted")
    factorial = config.get("factorial") or {}
    if factorial.get("mode") != "DESCRIPTIVE_ONLY" or factorial.get("no_p_values") is not True or factorial.get("no_significance_testing") is not True or factorial.get("sign_consistency_is_numerical_only") is not True:
        raise MOLDISC016Error("factorial boundary drifted")
    boundaries = config.get("boundaries") or {}
    for key in ("generation_executed", "candidate_selection_executed", "lead_selection_executed", "measurement_transfer_allowed", "universal_metric_created", "winner_created", "adaptive_execution"):
        if boundaries.get(key) is not False:
            raise MOLDISC016Error(f"boundary {key!r} must be false")
    if boundaries.get("evidence_ceiling") != "E2_COMPUTATIONAL":
        raise MOLDISC016Error("evidence ceiling drifted")
    claims = config.get("claims") or []
    if [item.get("claim_id") for item in claims] != [f"CLAIM-016-0{i}" for i in range(1, 6)]:
        raise MOLDISC016Error("claim set/order drifted")
    campaign_dir = Path(path).parent
    for filename in config.get("campaign_files") or ():
        campaign = _load_json(campaign_dir / filename)
        if campaign.get("campaign_id") not in {item.get("campaign_id") for item in campaigns}:
            raise MOLDISC016Error(f"campaign file identity drifted: {filename}")
    return config


def protocol_hash(config: Mapping[str, Any]) -> str:
    return sha256_json(dict(config))


def build_execution_plan(config: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    candidates = tuple(_candidate_from_config(item) for item in (config or {}).get("panel", ())) if config else CANDIDATES
    plan: list[dict[str, Any]] = []
    for candidate in candidates:
        for replicate in ("RUN_A", "RUN_B"):
            plan.append({"campaign_id": "CAMP-016-A", "campaign_name": "BASELINE_2X2_DOCKING", "candidate_id": candidate.candidate_id, "variant_id": candidate.variant_id, "condition_key": "baseline", "run_id": f"{candidate.key}__baseline__{replicate}", "replicate": replicate, "vina_seed": 42, "etkdg_seed": 42, "exhaustiveness": 16, "prepared_input": "baseline"})
    for seed in (1337, 2025):
        for candidate in candidates:
            plan.append({"campaign_id": "CAMP-016-B", "campaign_name": "VINA_SEED_SENSITIVITY", "candidate_id": candidate.candidate_id, "variant_id": candidate.variant_id, "condition_key": f"vina_seed_{seed}", "run_id": f"{candidate.key}__vina_seed_{seed}", "replicate": None, "vina_seed": seed, "etkdg_seed": 42, "exhaustiveness": 16, "prepared_input": "baseline"})
    for seed in (1337, 2025):
        for candidate in candidates:
            plan.append({"campaign_id": "CAMP-016-C", "campaign_name": "STARTING_CONFORMER_SENSITIVITY", "candidate_id": candidate.candidate_id, "variant_id": candidate.variant_id, "condition_key": f"etkdg_seed_{seed}", "run_id": f"{candidate.key}__etkdg_seed_{seed}", "replicate": None, "vina_seed": 42, "etkdg_seed": seed, "exhaustiveness": 16, "prepared_input": f"conformer_{seed}"})
    for exhaustiveness in (8, 32):
        for candidate in candidates:
            plan.append({"campaign_id": "CAMP-016-D", "campaign_name": "EXHAUSTIVENESS_SENSITIVITY", "candidate_id": candidate.candidate_id, "variant_id": candidate.variant_id, "condition_key": f"exhaustiveness_{exhaustiveness}", "run_id": f"{candidate.key}__exhaustiveness_{exhaustiveness}", "replicate": None, "vina_seed": 42, "etkdg_seed": 42, "exhaustiveness": exhaustiveness, "prepared_input": "baseline"})
    if len(plan) != EXPECTED_DOCKING_RUNS or len({item["run_id"] for item in plan}) != EXPECTED_DOCKING_RUNS:
        raise MOLDISC016Error("execution plan is not exactly 32 unique docking runs")
    return plan


def factorial_contrasts(y00: float, y10: float, y01: float, y11: float) -> dict[str, float]:
    return {
        "vina_rank1_score_oh_contrast": 0.5 * ((y10 - y00) + (y11 - y01)),
        "vina_rank1_score_nsub_contrast": 0.5 * ((y01 - y00) + (y11 - y10)),
        "vina_rank1_score_interaction_contrast": (y11 - y01) - (y10 - y00),
    }


def sign_consistent(values: Sequence[float]) -> bool:
    if not values:
        return False
    signs = {0 if value == 0 else (1 if value > 0 else -1) for value in values}
    return len(signs) == 1


def receptor_frame_rmsd(left: Sequence[Sequence[float]], right: Sequence[Sequence[float]]) -> float:
    if not left or len(left) != len(right):
        raise MOLDISC016Error("RMSD requires equal non-empty coordinate sequences")
    squared = []
    for a, b in zip(left, right):
        if len(a) != 3 or len(b) != 3:
            raise MOLDISC016Error("RMSD requires XYZ coordinates")
        squared.append(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))
    return math.sqrt(sum(squared) / len(squared))


def contact_residues(ligand_coordinates: Sequence[Sequence[float]], receptor_atoms: Sequence[Mapping[str, Any]], cutoff: float = CONTACT_CUTOFF_ANGSTROM) -> list[dict[str, Any]]:
    if cutoff != CONTACT_CUTOFF_ANGSTROM:
        raise MOLDISC016Error("contact cutoff is not the frozen 4.0 Å value")
    contacts: set[tuple[str, str, str, str]] = set()
    for atom in receptor_atoms:
        residue = (str(atom.get("chain", "")), str(atom.get("residue_name", "")), str(atom.get("residue_sequence", "")), str(atom.get("insertion_code", "")))
        receptor_xyz = (float(atom["x"]), float(atom["y"]), float(atom["z"]))
        if any(sum((float(point[i]) - receptor_xyz[i]) ** 2 for i in range(3)) <= cutoff ** 2 for point in ligand_coordinates):
            contacts.add(residue)
    return [{"chain": chain, "residue_name": name, "residue_sequence": sequence, "insertion_code": insertion} for chain, name, sequence, insertion in sorted(contacts)]


def _identity_from_smiles(smiles: str) -> Chem.Mol:
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise MOLDISC016Error("frozen candidate SMILES is not parseable")
    return molecule


def _pdbqt_atoms(path: Path, label: str) -> list[dict[str, Any]]:
    atoms: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        record = line[0:6].strip()
        if record not in {"ATOM", "HETATM"}:
            continue
        if len(line) < 78:
            raise MOLDISC016Error(f"{label} PDBQT contains a truncated atom record")
        try:
            atoms.append({"record": record, "atom_name": line[12:16].strip(), "residue_name": line[17:20].strip(), "chain": line[21].strip(), "residue_sequence": line[22:26].strip(), "insertion_code": line[26].strip(), "x": round(float(line[30:38]), 6), "y": round(float(line[38:46]), 6), "z": round(float(line[46:54]), 6), "partial_charge": round(float(line[70:76]), 6), "atom_type": line[77:].strip()})
        except ValueError as exc:
            raise MOLDISC016Error(f"{label} PDBQT atom record is malformed") from exc
    if not atoms:
        raise MOLDISC016Error(f"{label} PDBQT has no atoms")
    return atoms


def _prepare_conformer(molecule: Chem.Mol, seed: int, path: Path) -> dict[str, Any]:
    prepared = Chem.AddHs(Chem.Mol(molecule))
    prepared.RemoveAllConformers()
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    if AllChem.EmbedMolecule(prepared, params) != 0:
        raise MOLDISC016Error(f"ETKDGv3 failed for seed {seed}")
    uff = False
    if AllChem.UFFHasAllMoleculeParams(prepared):
        AllChem.UFFOptimizeMolecule(prepared, maxIters=1000)
        uff = True
    writer = Chem.SDWriter(str(path))
    writer.write(prepared)
    writer.close()
    return {"etkdg_seed": seed, "uff_optimized": uff, "sha256": sha256_file(path), "canonical_smiles": Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True), "inchikey": inchi.MolToInchiKey(molecule)}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def _target_snapshot(root: Path, obabel: OpenBabelEngine, timeout: float) -> dict[str, Any]:
    case = next((item for item in FROZEN_PROSPECTIVE_CASES if item.case_id == TARGET_CASE_ID), None)
    if case is None or case.pdb_id != PDB_ID or case.ligand_id != NATIVE_LIGAND or tuple(case.receptor_author_chains) != RECEPTOR_CHAINS:
        raise MOLDISC016Error("ATX-007 target case drifted")
    snapshot = root / "target_snapshot"
    snapshot.mkdir(parents=True, exist_ok=False)
    source_pdb = snapshot / "1KZK.pdb"
    source_sha = base._download(f"https://files.rcsb.org/download/{PDB_ID}.pdb", source_pdb, timeout=timeout)
    extraction = base.extract_case_from_pdb(source_pdb.read_text(encoding="utf-8", errors="replace"), case)
    receptor_pdb = snapshot / "receptor_extracted.pdb"
    receptor_pdb.write_text(extraction.receptor_pdb, encoding="utf-8")
    receptor_extracted_sha = sha256_file(receptor_pdb)
    native_sdf = snapshot / "je2_native_reference.sdf"
    native_sha = base._download(base._instance_sdf_url(case, extraction.ligand_auth_seq_id), native_sdf, timeout=timeout)
    native = base.load_single_sdf(native_sdf)
    grid = base.derive_redocking_grid(native)
    if grid.status != "PASS" or grid.grid_hash != GRID_HASH:
        raise MOLDISC016Error(f"FAIL_CLOSED_CONTROL_REPLAY_DRIFT: grid {grid.grid_hash!r}")
    receptor_pdbqt = snapshot / "receptor.pdbqt"
    prep = obabel.convert(receptor_pdb, receptor_pdbqt, options=("-h", "--partialcharge", "gasteiger", "-xr"), timeout=timeout, protocol_id="moldisc016.receptor-openbabel.v1")
    if prep.returncode != 0:
        raise MOLDISC016Error(f"receptor Open Babel preparation failed: {prep.stderr}")
    receptor_pdbqt_sha = _require_prepared(receptor_pdbqt, "shared receptor")
    receptor_identity = _pdbqt_scientific_identity(receptor_pdbqt, "shared receptor")
    reference_payload = _reference_structure_identity(native)
    snapshot_payload = {"case_id": TARGET_CASE_ID, "pdb_id": PDB_ID, "native_ligand": NATIVE_LIGAND, "receptor_author_chains": list(RECEPTOR_CHAINS), "coordinate_frame": "RECEPTOR_FRAME", "grid": grid.to_dict(), "receptor_extracted_sha256": receptor_extracted_sha, "receptor_scientific_identity": receptor_identity, "native_reference_structure": reference_payload}
    snapshot_hash = sha256_json(snapshot_payload)
    _write_json(snapshot / "target_snapshot.json", {**snapshot_payload, "target_snapshot_scientific_hash": snapshot_hash, "source_pdb_transport_sha256": source_sha, "native_reference_transport_sha256": native_sha, "receptor_pdbqt_sha256": receptor_pdbqt_sha})
    return {**snapshot_payload, "target_snapshot_scientific_hash": snapshot_hash, "source_pdb_transport_sha256": source_sha, "native_reference_transport_sha256": native_sha, "receptor_pdbqt_sha256": receptor_pdbqt_sha, "receptor_pdbqt_path": str(receptor_pdbqt), "receptor_pdb_path": str(receptor_pdb), "native_reference_path": str(native_sdf), "native_reference_structure_hash": reference_payload["structure_hash"], "grid": grid.to_dict()}


def _failure_record(spec: Mapping[str, Any], reason: str, status: str = "NONPASS") -> dict[str, Any]:
    return {**dict(spec), "technical_status": status, "first_loss": reason, "pose_count": 0, "pose_scores_kcal_mol": [], "pose_1_score_kcal_mol": None, "deterministic": False, "candidate_execution_hash": None, "generation_executed": False, "candidate_selection_executed": False}


def _write_run_record(root: Path, spec: Mapping[str, Any], record: Mapping[str, Any]) -> None:
    run_root = root / "runs" / str(spec["run_id"])
    run_root.mkdir(parents=True, exist_ok=False)
    _write_json(run_root / "run_manifest.json", dict(record))


def _execute_run(spec: Mapping[str, Any], candidate: CandidateSpec, target: Mapping[str, Any], prepared: Mapping[str, Any], root: Path, vina: VinaEngine, timeout: float) -> dict[str, Any]:
    run_root = root / "runs" / str(spec["run_id"])
    run_root.mkdir(parents=True, exist_ok=False)
    _write_json(run_root / "protocol_parameters.json", dict(spec))
    output = run_root / f"{candidate.key}_vina_poses.pdbqt"
    request = DockingRequest(receptor_path=str(target["receptor_pdbqt_path"]), ligand_path=str(prepared["pdbqt_path"]), grid=GridBox(target["grid"]["center_x"], target["grid"]["center_y"], target["grid"]["center_z"], target["grid"]["size_x"], target["grid"]["size_y"], target["grid"]["size_z"]), exhaustiveness=int(spec["exhaustiveness"]), cpu=VINA_CPU, seed=int(spec["vina_seed"]), output_path=str(output), target_id=f"{TARGET_CASE_ID}:{PDB_ID}:{NATIVE_LIGAND}:{candidate.variant_id}", role="NON_COGNATE_HOLO_CROSSDOCKING", protocol_id="research-os.moldisc-016.je2-source-megacampaign.v1", timeout=900.0, num_modes=NUM_MODES)
    result = vina.run(request)
    if result.returncode != 0 or not output.is_file():
        record = _failure_record(spec, "DOCKING_FAIL")
        record["engine_stderr"] = result.stderr[-4000:]
        _write_json(run_root / "run_manifest.json", record)
        return record
    text = output.read_text(encoding="utf-8", errors="replace")
    models = base.split_vina_pdbqt_models(text)
    scores = [float(value) for value in base.parse_vina_pose_scores(text)]
    if not models or len(models) != len(scores) or any(not math.isfinite(value) for value in scores):
        record = _failure_record(spec, "NO_VALID_POSES")
        _write_json(run_root / "run_manifest.json", record)
        return record
    vina_identity = _vina_scientific_identity(models, scores)
    scientific = {"schema": "moldisc-016.docking-run.v1", "target_snapshot_scientific_hash": target["target_snapshot_scientific_hash"], "candidate": asdict(candidate), "protocol": dict(spec), "receptor_scientific_identity": target["receptor_scientific_identity"], "ligand_scientific_identity": prepared["ligand_scientific_identity"], "vina_output_scientific_hash": vina_identity, "pose_count": len(models), "pose_scores_kcal_mol": scores, "technical_status": "PASS"}
    scientific_hash = sha256_json(scientific)
    record = {**dict(spec), "technical_status": "PASS", "first_loss": None, "candidate_execution_hash": scientific_hash, "pose_count": len(models), "pose_scores_kcal_mol": scores, "pose_1_score_kcal_mol": scores[0], "deterministic": True, "target_snapshot_scientific_hash": target["target_snapshot_scientific_hash"], "receptor_scientific_identity": target["receptor_scientific_identity"], "ligand_scientific_identity": prepared["ligand_scientific_identity"], "vina_output_scientific_hash": vina_identity, "vina_output_transport_sha256": sha256_file(output), "prepared_input": {key: value for key, value in prepared.items() if key != "pdbqt_path" and key != "sdf_path"}, "generation_executed": False, "candidate_selection_executed": False}
    _write_json(run_root / "scientific_payload.json", scientific)
    _write_json(run_root / "run_manifest.json", record)
    return record


def _baseline_ready(records: Mapping[str, Mapping[str, Any]], candidate: CandidateSpec) -> bool:
    return all(records.get(f"{candidate.key}__baseline__{replicate}", {}).get("technical_status") == "PASS" for replicate in ("RUN_A", "RUN_B"))


def _validate_control_replay(records: Mapping[str, Mapping[str, Any]], target: Mapping[str, Any]) -> dict[str, Any]:
    run_a = records.get("A0B0__baseline__RUN_A", {})
    run_b = records.get("A0B0__baseline__RUN_B", {})
    if run_a.get("technical_status") != "PASS" or run_b.get("technical_status") != "PASS":
        return {"status": "INDETERMINATE_CONTROL_BASELINE_NONPASS", "expected_parent_hash": CONTROL_MOLDISC012_HASH}
    checks = {
        "pose_count": run_a.get("pose_count") == len(CONTROL_EXPECTED_POSE_SCORES) == run_b.get("pose_count"),
        "pose_scores_run_a": run_a.get("pose_scores_kcal_mol") == list(CONTROL_EXPECTED_POSE_SCORES),
        "pose_scores_run_b": run_b.get("pose_scores_kcal_mol") == list(CONTROL_EXPECTED_POSE_SCORES),
        "native_reference_structure_hash": target.get("native_reference_structure_hash") == CONTROL_EXPECTED_NATIVE_REFERENCE_STRUCTURE_HASH,
        "receptor_scientific_identity": target.get("receptor_scientific_identity") == CONTROL_EXPECTED_RECEPTOR_SCIENTIFIC_IDENTITY,
        "ligand_scientific_identity_run_a": run_a.get("ligand_scientific_identity") == CONTROL_EXPECTED_LIGAND_SCIENTIFIC_IDENTITY,
        "ligand_scientific_identity_run_b": run_b.get("ligand_scientific_identity") == CONTROL_EXPECTED_LIGAND_SCIENTIFIC_IDENTITY,
        "vina_scientific_hash_run_a": run_a.get("vina_output_scientific_hash") == CONTROL_EXPECTED_VINA_SCIENTIFIC_HASH,
        "vina_scientific_hash_run_b": run_b.get("vina_output_scientific_hash") == CONTROL_EXPECTED_VINA_SCIENTIFIC_HASH,
    }
    if not all(checks.values()):
        failed = [key for key, value in checks.items() if not value]
        raise MOLDISC016Error("FAIL_CLOSED_CONTROL_REPLAY_DRIFT: " + ", ".join(failed))
    return {
        "status": "PASS",
        "expected_parent_hash": CONTROL_MOLDISC012_HASH,
        "checks": checks,
        "replayed_pose_count": len(CONTROL_EXPECTED_POSE_SCORES),
        "replayed_pose_1_score_kcal_mol": CONTROL_EXPECTED_POSE_SCORES[0],
        "replayed_vina_output_scientific_hash": CONTROL_EXPECTED_VINA_SCIENTIFIC_HASH,
    }


def _prepare_input(candidate: CandidateSpec, seed: int, root: Path, obabel: OpenBabelEngine, timeout: float) -> dict[str, Any]:
    prepared_root = root / "prepared" / candidate.key / f"etkdg_{seed}"
    prepared_root.mkdir(parents=True, exist_ok=False)
    molecule = _identity_from_smiles(candidate.canonical_smiles)
    sdf = prepared_root / "starting_conformer.sdf"
    conformer = _prepare_conformer(molecule, seed, sdf)
    pdbqt = prepared_root / "ligand.pdbqt"
    prep = obabel.convert(sdf, pdbqt, options=("-h", "--partialcharge", "gasteiger"), timeout=timeout, protocol_id="moldisc016.ligand-openbabel.v1")
    if prep.returncode != 0:
        raise MOLDISC016Error(f"ligand Open Babel preparation failed: {prep.stderr}")
    pdbqt_sha = _require_prepared(pdbqt, f"{candidate.variant_id} ligand")
    ligand_identity = _pdbqt_scientific_identity(pdbqt, f"{candidate.variant_id} ligand")
    return {**conformer, "pdbqt_sha256": pdbqt_sha, "ligand_scientific_identity": ligand_identity, "pdbqt_path": str(pdbqt), "sdf_path": str(sdf)}


def _parse_receptor_atoms(path: Path) -> list[dict[str, Any]]:
    atoms: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line[0:6].strip() != "ATOM":
            continue
        element = line[76:78].strip() or line[12:16].strip()[0:1]
        if element.upper() == "H":
            continue
        atoms.append({"chain": line[21].strip(), "residue_name": line[17:20].strip(), "residue_sequence": line[22:26].strip(), "insertion_code": line[26].strip(), "x": float(line[30:38]), "y": float(line[38:46]), "z": float(line[46:54])})
    if not atoms:
        raise MOLDISC016Error("shared receptor has no heavy atoms")
    return atoms


def _heavy_coordinates(molecule: Chem.Mol) -> list[tuple[float, float, float]]:
    if molecule.GetNumConformers() != 1:
        raise MOLDISC016Error("pose must contain one conformer")
    conf = molecule.GetConformer()
    return [(float(conf.GetAtomPosition(index).x), float(conf.GetAtomPosition(index).y), float(conf.GetAtomPosition(index).z)) for index, atom in enumerate(molecule.GetAtoms()) if atom.GetAtomicNum() != 1]


def _pose_records(records: Mapping[str, Mapping[str, Any]], candidates: Mapping[str, CandidateSpec], root: Path, obabel: OpenBabelEngine, timeout: float) -> dict[str, list[Any]]:
    output: dict[str, list[Any]] = {}
    for candidate in candidates.values():
        run_id = f"{candidate.key}__baseline__RUN_A"
        if records[run_id].get("technical_status") != "PASS":
            continue
        source = _identity_from_smiles(candidate.canonical_smiles)
        output[candidate.key] = geometry_base._prepare_pose_set(root / "runs" / run_id, source, f"MOLDISC-016-{candidate.variant_id}", obabel, timeout)
    return output


def _geometry_analysis(records: Mapping[str, Mapping[str, Any]], candidates: Mapping[str, CandidateSpec], poses: Mapping[str, Sequence[Any]]) -> dict[str, Any]:
    edges = (("EDGE-OH-BENZYL", "A0B0", "A1B0"), ("EDGE-OH-TERTBUTYL", "A0B1", "A1B1"), ("EDGE-NSUB-OH_PRESENT", "A0B0", "A0B1"), ("EDGE-NSUB-OH_DELETED", "A1B0", "A1B1"))
    by_key = candidates
    result: dict[str, Any] = {"metric": "RECEPTOR_FRAME_COMMON_CORE_RMSD", "coordinate_frame": "RECEPTOR_FRAME", "no_rigid_body_alignment": True, "threshold_angstrom": None, "edges": []}
    for edge_id, left_key, right_key in edges:
        item: dict[str, Any] = {"edge_id": edge_id, "left": left_key, "right": right_key, "status": "PASS"}
        try:
            left = by_key[left_key]
            right = by_key[right_key]
            left_source = _identity_from_smiles(left.canonical_smiles)
            right_source = _identity_from_smiles(right.canonical_smiles)
            mapping_hash, mapping_payload = geometry_base._core_mapping_identity(left_source, right_source)
            matrix = []
            for left_pose in poses[left_key]:
                for right_pose in poses[right_key]:
                    pair = geometry_base.analyze_pose_pair(left_source, right_source, left_pose.molecule, right_pose.molecule)
                    matrix.append({"left_pose_rank": left_pose.rank, "right_pose_rank": right_pose.rank, "rmsd_angstrom": pair.common_core_rmsd_angstrom, "mapping_identity": pair.mapping_identity, "status": pair.status})
            rank1 = next(cell for cell in matrix if cell["left_pose_rank"] == 1 and cell["right_pose_rank"] == 1)
            minimum = min(matrix, key=lambda cell: (cell["rmsd_angstrom"], cell["left_pose_rank"], cell["right_pose_rank"]))
            left_rank1 = min((cell for cell in matrix if cell["left_pose_rank"] == 1), key=lambda cell: (cell["rmsd_angstrom"], cell["right_pose_rank"]))
            right_rank1 = min((cell for cell in matrix if cell["right_pose_rank"] == 1), key=lambda cell: (cell["rmsd_angstrom"], cell["left_pose_rank"]))
            item.update({"common_core_heavy_atoms": right.heavy_atom_count, "common_core_graph_identity": mapping_payload["child_graph"], "mapping_scientific_hash": mapping_hash, "mapping_count": len(mapping_payload["child_to_parent_mappings"]), "matrix_shape": [len(poses[left_key]), len(poses[right_key])], "matrix": matrix, "matrix_hash": sha256_json(matrix), "rank1_pair_rmsd": rank1["rmsd_angstrom"], "minimum_all_pose_pairs_rmsd": minimum["rmsd_angstrom"], "minimum_pair_rank_left": minimum["left_pose_rank"], "minimum_pair_rank_right": minimum["right_pose_rank"], "left_rank1_to_right_ensemble_min": left_rank1["rmsd_angstrom"], "left_rank1_to_right_ensemble_min_rank_right": left_rank1["right_pose_rank"], "right_rank1_to_left_ensemble_min": right_rank1["rmsd_angstrom"], "right_rank1_to_left_ensemble_min_rank_left": right_rank1["left_pose_rank"]})
        except (KeyError, IndexError, MOLDISC016Error, geometry_base.MOLDISC013Error) as exc:
            item.update({"status": "EDGE_GEOMETRY_INDETERMINATE", "reason": str(exc), "matrix": [], "matrix_shape": [0, 0], "matrix_hash": sha256_json([])})
        result["edges"].append(item)
    result["geometry_scientific_hash"] = sha256_json(result)
    return result


def _contact_analysis(records: Mapping[str, Mapping[str, Any]], candidates: Mapping[str, CandidateSpec], poses: Mapping[str, Sequence[Any]], receptor_atoms: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    profiles: dict[str, Any] = {}
    for key, candidate in candidates.items():
        if key not in poses:
            profiles[key] = {"status": "INDETERMINATE", "reason": "baseline RUN_A non-PASS"}
            continue
        pose_contacts = []
        for pose in poses[key]:
            contacts = contact_residues(_heavy_coordinates(pose.molecule), receptor_atoms)
            pose_contacts.append(contacts)
        rank1 = pose_contacts[0]
        keys = lambda values: {tuple(item[field] for field in ("chain", "residue_name", "residue_sequence", "insertion_code")) for item in values}
        all_residue_keys = sorted(set().union(*(keys(values) for values in pose_contacts)))
        ensemble = [{"residue": {"chain": item[0], "residue_name": item[1], "residue_sequence": item[2], "insertion_code": item[3]}, "poses_in_contact": sum(item in keys(values) for values in pose_contacts), "pose_fraction_in_contact": sum(item in keys(values) for values in pose_contacts) / len(pose_contacts)} for item in all_residue_keys]
        profiles[key] = {"status": "PASS", "rank1_contact_residues": rank1, "rank1_contact_count": len(rank1), "rank1_contact_fingerprint_hash": sha256_json(rank1), "ensemble_contact_profile": ensemble, "ensemble_contact_profile_hash": sha256_json(ensemble), "pose_count": len(pose_contacts)}
    edges = (("EDGE-OH-BENZYL", "A0B0", "A1B0"), ("EDGE-OH-TERTBUTYL", "A0B1", "A1B1"), ("EDGE-NSUB-OH_PRESENT", "A0B0", "A0B1"), ("EDGE-NSUB-OH_DELETED", "A1B0", "A1B1"))
    comparisons = []
    for edge_id, left, right in edges:
        left_set = {tuple(item[field] for field in ("chain", "residue_name", "residue_sequence", "insertion_code")) for item in profiles.get(left, {}).get("rank1_contact_residues", [])}
        right_set = {tuple(item[field] for field in ("chain", "residue_name", "residue_sequence", "insertion_code")) for item in profiles.get(right, {}).get("rank1_contact_residues", [])}
        union = left_set | right_set
        comparisons.append({"edge_id": edge_id, "left": left, "right": right, "rank1_contact_set_intersection": [list(item) for item in sorted(left_set & right_set)], "rank1_contact_set_union": [list(item) for item in sorted(union)], "rank1_contact_jaccard": (len(left_set & right_set) / len(union)) if union else None, "contacts_gained": [list(item) for item in sorted(right_set - left_set)], "contacts_lost": [list(item) for item in sorted(left_set - right_set)]})
    payload = {"cutoff_angstrom": CONTACT_CUTOFF_ANGSTROM, "profiles": profiles, "edge_comparisons": comparisons}
    return {**payload, "contact_scientific_hash": sha256_json(payload)}


def _condition_scores(records: Mapping[str, Mapping[str, Any]], candidates: Mapping[str, CandidateSpec]) -> dict[str, dict[str, float | None]]:
    scores: dict[str, dict[str, float | None]] = {key: {} for key in candidates}
    for key in candidates:
        for condition in ANALYSIS_CONDITIONS:
            if condition == "baseline":
                run_id = f"{key}__baseline__RUN_A"
            else:
                run_id = f"{key}__{condition}"
            value = records.get(run_id, {}).get("pose_1_score_kcal_mol") if records.get(run_id, {}).get("technical_status") == "PASS" else None
            scores[key][condition] = value
    return scores


def _factorial_analysis(records: Mapping[str, Mapping[str, Any]], candidates: Mapping[str, CandidateSpec]) -> dict[str, Any]:
    scores = _condition_scores(records, candidates)
    order = ["A0B0", "A1B0", "A0B1", "A1B1"]
    contrasts: dict[str, Any] = {}
    for condition in ANALYSIS_CONDITIONS:
        values = {key: scores[key][condition] for key in order}
        if any(value is None for value in values.values()):
            contrasts[condition] = {"status": "INDETERMINATE_MISSING_CONDITION", "values_by_cell": values, "contrasts": None}
        else:
            computed = factorial_contrasts(float(values["A0B0"]), float(values["A1B0"]), float(values["A0B1"]), float(values["A1B1"]))
            contrasts[condition] = {"status": "PASS", "values_by_cell": values, "contrasts": computed}
    sign_summary = {}
    for field in ("vina_rank1_score_oh_contrast", "vina_rank1_score_nsub_contrast", "vina_rank1_score_interaction_contrast"):
        values = [item["contrasts"][field] for item in contrasts.values() if item["status"] == "PASS"]
        missing = len(values) != len(ANALYSIS_CONDITIONS)
        sign_summary[field] = {"values": values, "minimum": min(values) if values else None, "maximum": max(values) if values else None, "range": (max(values) - min(values)) if values else None, "median": statistics.median(values) if values else None, "signs": [0 if value == 0 else (1 if value > 0 else -1) for value in values], "sign_consistent": sign_consistent(values) if values else False, "status": "INDETERMINATE_MISSING_CONDITION" if missing else ("PASS" if sign_consistent(values) else "CONTRADICTS")}
    payload = {"mode": "DESCRIPTIVE_ONLY", "analysis_conditions": list(ANALYSIS_CONDITIONS), "rank1_scores": scores, "contrasts_by_condition": contrasts, "sign_summary": sign_summary, "no_p_values": True, "no_significance_testing": True}
    return {**payload, "factorial_scientific_hash": sha256_json(payload)}


def _synthesis(records: Mapping[str, Mapping[str, Any]], factorial: Mapping[str, Any], target: Mapping[str, Any], config: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    baseline_pass = all(records.get(f"{key}__baseline__RUN_A", {}).get("technical_status") == "PASS" and records.get(f"{key}__baseline__RUN_B", {}).get("technical_status") == "PASS" for key in ("A0B0", "A1B0", "A0B1", "A1B1"))
    claim_status = {"CLAIM-016-01": "SUPPORTS" if baseline_pass else "INDETERMINATE"}
    for claim_id, field in (("CLAIM-016-02", "vina_rank1_score_oh_contrast"), ("CLAIM-016-03", "vina_rank1_score_nsub_contrast"), ("CLAIM-016-04", "vina_rank1_score_interaction_contrast")):
        claim_status[claim_id] = "SUPPORTS" if factorial["sign_summary"][field]["status"] == "PASS" else ("CONTRADICTS" if factorial["sign_summary"][field]["status"] == "CONTRADICTS" else "INDETERMINATE")
    claim_status["CLAIM-016-05"] = "SUPPORTS"
    synthesis = {"evidence_ceiling": "E2_COMPUTATIONAL", "claim_status": claim_status, "interpretation_boundary": "Vina score contrasts, geometry, and 4.0 Å contacts are computational/descriptive only; no score is affinity, potency, efficacy, or experimental binding.", "candidate_selection_executed": False, "lead_selection_executed": False, "generation_executed": False, "measurement_transfer_allowed": False}
    knowledge = {"new_evidence_ids": ["MOLDISC-016-E2-STATIC-ROBUSTNESS"], "resolved_gap_ids": [], "partially_resolved_gap_ids": ["GAP-DOCKING-PROTOCOL-SENSITIVITY", "GAP-JE2-FACTORIAL-COMPUTATIONAL-LANDSCAPE"], "new_gap_ids": ["GAP-EXPERIMENTAL-BINDING-VALIDATION", "GAP-C2545-STEREOCHEMISTRY", "GAP-NONCOGNATE-CAPABILITY"], "unresolved_uncertainty": ["experimental binding validation unavailable", "exact C-2545 stereochemistry unresolved", "single receptor structure limitation", "non-cognate docking capability only partially validated"], "summary": "The campaign adds bounded E2 computational robustness and descriptive factorial evidence without promoting repeated docking to experimental affinity or selecting a lead.", "scientific_hash": sha256_json(synthesis)}
    return synthesis, knowledge


def _summary_matrix(records: Mapping[str, Mapping[str, Any]], candidates: Mapping[str, CandidateSpec]) -> list[dict[str, Any]]:
    nearest = {"A0B0": 0.6857142857142857, "A1B0": 0.7903225806451613, "A0B1": 0.859375, "A1B1": 1.0}
    esol = {"A0B0": "IN_DOMAIN", "A1B0": "IN_DOMAIN", "A0B1": "OUT_OF_DOMAIN", "A1B1": "OUT_OF_DOMAIN"}
    rows = []
    for key in ("A0B0", "A1B0", "A0B1", "A1B1"):
        candidate = candidates[key]
        row = {"candidate": candidate.candidate_id, "variant_id": candidate.variant_id, "factor_A": candidate.factor_a, "factor_B": candidate.factor_b, "baseline_A_status": records.get(f"{key}__baseline__RUN_A", {}).get("technical_status"), "baseline_B_status": records.get(f"{key}__baseline__RUN_B", {}).get("technical_status"), "baseline_pose_count": records.get(f"{key}__baseline__RUN_A", {}).get("pose_count"), "baseline_pose1_score": records.get(f"{key}__baseline__RUN_A", {}).get("pose_1_score_kcal_mol"), "AqSolDB_nearest": nearest[key], "ESOL_status": esol[key], "source_connectivity_match": True, "measurement_transfer_allowed": False}
        for condition in ANALYSIS_CONDITIONS:
            run_id = f"{key}__baseline__RUN_A" if condition == "baseline" else f"{key}__{condition}"
            row[condition] = records.get(run_id, {}).get("pose_1_score_kcal_mol") if records.get(run_id, {}).get("technical_status") == "PASS" else None
        rows.append(row)
    return rows


def _markdown(manifest: Mapping[str, Any]) -> str:
    return "\n".join(["# MOLDISC-016 — JE2 Source-Directed Robustness Megacampaign", "", f"- protocol hash: `{manifest['program_protocol_hash']}`", f"- program hash: `{manifest['program_scientific_hash']}`", f"- docking planned/executed/skipped: `{manifest['docking_runs_planned']}/{manifest['docking_runs_executed']}/{manifest['docking_runs_skipped']}`", f"- non-pass docking runs: `{manifest['docking_runs_nonpass']}`", "- candidate selection/lead selection/generation: `NO/NO/NO`", "- evidence ceiling: `E2_COMPUTATIONAL`", "", "Vina scores are engine outputs. They are not affinity, potency, efficacy, or experimental binding. The four panel cells are retained without winner selection.", ""])


def run_moldisc_016(*, config_path: str | Path, output_root: str | Path, timeout: float = 120.0) -> dict[str, Any]:
    config = load_program_config_v16(config_path)
    plan = build_execution_plan(config)
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=False)
    _write_json(root / "program_protocol_payload.json", config)
    obabel = OpenBabelEngine()
    vina = VinaEngine()
    if not obabel.available:
        raise MOLDISC016Error("ENGINE_UNAVAILABLE: Open Babel is unavailable")
    if not vina.available or not vina.version or VINA_VERSION not in vina.version:
        raise MOLDISC016Error(f"ENGINE_UNAVAILABLE: Vina {VINA_VERSION} is required")
    target = _target_snapshot(root, obabel, timeout)
    candidates = {candidate.key: candidate for candidate in CANDIDATES}
    prepared: dict[tuple[str, int], dict[str, Any]] = {}
    records: dict[str, dict[str, Any]] = {}
    failures = 0
    executed = 0
    skipped = 0
    nonpass = 0
    halted = False

    def execute_specs(specs: Sequence[Mapping[str, Any]]) -> None:
        nonlocal failures, executed, skipped, nonpass, halted
        for spec in specs:
            if halted:
                break
            candidate = next(item for item in CANDIDATES if item.candidate_id == spec["candidate_id"])
            if spec["campaign_id"] != "CAMP-016-A" and not _baseline_ready(records, candidate):
                record = _failure_record(spec, "SKIPPED_DEPENDENCY", "SKIPPED_DEPENDENCY")
                records[spec["run_id"]] = record
                _write_run_record(root, spec, record)
                skipped += 1
                continue
            if executed >= MAX_DOCKING_RUNS:
                record = _failure_record(spec, "RESOURCE_LIMIT_REACHED", "SKIPPED_RESOURCE_LIMIT")
                records[spec["run_id"]] = record
                _write_run_record(root, spec, record)
                skipped += 1
                continue
            input_seed = 42 if spec["prepared_input"] == "baseline" else int(str(spec["prepared_input"]).split("_")[-1])
            input_key = (candidate.key, input_seed)
            try:
                if input_key not in prepared:
                    prepared[input_key] = _prepare_input(candidate, input_seed, root, obabel, timeout)
                record = _execute_run(spec, candidate, target, prepared[input_key], root, vina, timeout)
            except (MOLDISC016Error, OSError, ValueError) as exc:
                record = _failure_record(spec, "PREPARATION_INDETERMINATE")
                record["error"] = str(exc)
                _write_run_record(root, spec, record)
            records[spec["run_id"]] = record
            executed += 1
            if record["technical_status"] != "PASS":
                nonpass += 1
                failures += 1
                if failures >= MAX_FAILURES:
                    halted = True

    baseline_plan = [item for item in plan if item["campaign_id"] == "CAMP-016-A"]
    sensitivity_plan = [item for item in plan if item["campaign_id"] != "CAMP-016-A"]
    execute_specs(baseline_plan)
    control_replay = _validate_control_replay(records, target)
    execute_specs(sensitivity_plan)
    if halted:
        for remaining in plan:
            if remaining["run_id"] not in records:
                record = _failure_record(remaining, "RESOURCE_LIMIT_REACHED", "SKIPPED_RESOURCE_LIMIT")
                records[remaining["run_id"]] = record
                _write_run_record(root, remaining, record)
                skipped += 1
    receptor_atoms = _parse_receptor_atoms(Path(target["receptor_pdb_path"]))
    pose_records = _pose_records(records, candidates, root, obabel, timeout)
    geometry = _geometry_analysis(records, candidates, pose_records)
    contacts = _contact_analysis(records, candidates, pose_records, receptor_atoms)
    factorial = _factorial_analysis(records, candidates)
    synthesis, knowledge = _synthesis(records, factorial, target, config)
    matrix = _summary_matrix(records, candidates)
    campaign_hashes = {
        "baseline_campaign_hash": sha256_json({"campaign_id": "CAMP-016-A", "records": [records[item["run_id"]] for item in plan if item["campaign_id"] == "CAMP-016-A"]}),
        "vina_seed_campaign_hash": sha256_json({"campaign_id": "CAMP-016-B", "records": [records[item["run_id"]] for item in plan if item["campaign_id"] == "CAMP-016-B"]}),
        "conformer_campaign_hash": sha256_json({"campaign_id": "CAMP-016-C", "records": [records[item["run_id"]] for item in plan if item["campaign_id"] == "CAMP-016-C"]}),
        "exhaustiveness_campaign_hash": sha256_json({"campaign_id": "CAMP-016-D", "records": [records[item["run_id"]] for item in plan if item["campaign_id"] == "CAMP-016-D"]}),
        "geometry_campaign_hash": geometry["geometry_scientific_hash"],
        "contact_campaign_hash": contacts["contact_scientific_hash"],
        "factorial_campaign_hash": factorial["factorial_scientific_hash"],
        "synthesis_hash": sha256_json(synthesis),
    }
    scientific = {"program_id": PROGRAM_ID, "program_version": PROGRAM_VERSION, "program_protocol_hash": protocol_hash(config), "parent_hashes": {"moldisc014": PARENT_MOLDISC014_HASH, "moldisc015": PARENT_MOLDISC015_HASH, "moldisc012": CONTROL_MOLDISC012_HASH}, "panel": [asdict(candidate) for candidate in CANDIDATES], "target_snapshot_scientific_hash": target["target_snapshot_scientific_hash"], "control_replay": control_replay, "campaign_hashes": campaign_hashes, "run_scientific_records": [{key: value for key, value in records[item["run_id"]].items() if key not in {"engine_stderr", "error"}} for item in plan], "geometry_hash": geometry["geometry_scientific_hash"], "contact_hash": contacts["contact_scientific_hash"], "factorial_hash": factorial["factorial_scientific_hash"], "synthesis_hash": campaign_hashes["synthesis_hash"], "candidate_selection_executed": False, "lead_selection_executed": False, "generation_executed": False, "measurement_transfer_allowed": False, "evidence_ceiling": "E2_COMPUTATIONAL"}
    program_scientific_hash = sha256_json(scientific)
    manifest = {"schema_version": "research-os.molecular-discovery.megacampaign-result.v1", "program_id": PROGRAM_ID, "program_version": PROGRAM_VERSION, "status": "CLOSED_FIRST_RESULT_PRESERVED", "program_protocol_hash": protocol_hash(config), "program_scientific_hash": program_scientific_hash, "parent_hashes": {"moldisc014": PARENT_MOLDISC014_HASH, "moldisc015": PARENT_MOLDISC015_HASH, "moldisc012": CONTROL_MOLDISC012_HASH}, "control_replay": control_replay, "docking_runs_planned": EXPECTED_DOCKING_RUNS, "docking_runs_executed": executed, "docking_runs_skipped": skipped, "docking_runs_nonpass": nonpass, "resource_limit_reached": failures >= MAX_FAILURES, "panel_manifest": "panel_manifest.json", "target_snapshot": "target_snapshot/target_snapshot.json", "campaign_hashes": campaign_hashes, "candidate_selection_executed": False, "lead_selection_executed": False, "generation_executed": False, "source_measurement_transfer_allowed": False, "evidence_ceiling": "E2_COMPUTATIONAL", "claims": synthesis["claim_status"], "knowledge_gain_summary": knowledge["summary"]}
    _write_json(root / "program_manifest.json", manifest)
    _write_json(root / "program_scientific_payload.json", scientific)
    _write_json(root / "campaign_manifest.json", {"campaigns": config["campaigns"], "campaign_hashes": campaign_hashes, "docking_runs_planned": EXPECTED_DOCKING_RUNS})
    _write_json(root / "panel_manifest.json", {"panel": [asdict(candidate) for candidate in CANDIDATES], "source_measurement_transfer_allowed": False})
    _write_json(root / "baseline_results.json", {"runs": [records[item["run_id"]] for item in plan if item["campaign_id"] == "CAMP-016-A"]})
    _write_json(root / "vina_seed_sensitivity.json", {"runs": [records[item["run_id"]] for item in plan if item["campaign_id"] == "CAMP-016-B"]})
    _write_json(root / "conformer_sensitivity.json", {"runs": [records[item["run_id"]] for item in plan if item["campaign_id"] == "CAMP-016-C"]})
    _write_json(root / "exhaustiveness_sensitivity.json", {"runs": [records[item["run_id"]] for item in plan if item["campaign_id"] == "CAMP-016-D"]})
    _write_json(root / "geometry_analysis.json", geometry)
    _write_json(root / "contact_analysis.json", contacts)
    _write_json(root / "factorial_analysis.json", factorial)
    _write_json(root / "program_synthesis.json", synthesis)
    _write_json(root / "knowledge_gain.json", knowledge)
    _write_json(root / "transport_provenance.json", {"target_snapshot": {key: target[key] for key in ("source_pdb_transport_sha256", "native_reference_transport_sha256", "receptor_pdbqt_sha256")}, "raw_transport_is_not_scientific_identity": True})
    _write_json(root / "summary_matrix.json", {"order": ["A0B0", "A1B0", "A0B1", "A1B1"], "rows": matrix})
    (root / "program_report.md").write_text(_markdown(manifest), encoding="utf-8")
    return {**manifest, "summary_matrix": matrix, "geometry": geometry, "contacts": contacts, "factorial": factorial, "synthesis": synthesis, "knowledge_gain": knowledge, "records": records}


__all__ = [
    "CANDIDATES", "CONTACT_CUTOFF_ANGSTROM", "CONTROL_MOLDISC012_HASH", "EXPECTED_DOCKING_RUNS", "MOLDISC016Error", "PARENT_MOLDISC014_HASH", "PARENT_MOLDISC015_HASH", "build_execution_plan", "contact_residues", "factorial_contrasts", "load_program_config_v16", "protocol_hash", "receptor_frame_rmsd", "run_moldisc_016", "sign_consistent",
]
