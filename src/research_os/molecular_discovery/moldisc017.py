"""MOLDISC-017: bounded receptor-state challenge of the frozen JE2 panel.

This module is deliberately specific to the MOLDISC-017 protocol.  R0 is an
imported MOLDISC-016 result; only the predeclared R1/R2 redocking and
cross-docking runs can invoke Vina.  The module never generates or selects a
molecule and does not interpret a Vina score as affinity.
"""

from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path
import re
import statistics
from typing import Any, Mapping, Sequence

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, rdFMCS, inchi, rdMolDescriptors

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking import redocking as base
from research_os.docking.schema import DockingRequest, GridBox
from research_os.engines.openbabel import OpenBabelEngine
from research_os.engines.vina import VinaEngine
from research_os.molecular_discovery import moldisc016


PROGRAM_ID = "MOLDISC-017"
PROGRAM_VERSION = "1.0"
PARENT_MOLDISC016_HASH = "68472cbc795ccb9cbbaef083bdc44819218c2b3f29b50ff7481ff99097687095"
PARENT_MOLDISC016_PROTOCOL_HASH = "67a127a651df771f7789cd8f4e4933575f81d7ee91d0dae2219921c6a2dc3e70"
PARENT_MOLDISC015_HASH = "8e22c0565f2d78dc16468c8edb8f8f0b90a4007e50ced99e00e3d7a0b0f63e5d"
PARENT_MOLDISC014_HASH = "f940d95189616131829a22f9e68a53a960eddf8fd05f5fd7ebac43ece85481ed"
R0_PDB = "1KZK"
R1_PDB = "1MSM"
R2_PDB = "1MSN"
K57_WT_PDB = "1MRW"
K57_MUTANT_PDB = "1MRX"
JE2_INCHIKEY = "CUFQBQOBLVLKRF-RZDMPUFOSA-N"
K57_INCHIKEY = "CGFVYUGIPISJQG-ACIOBRDBSA-N"
K57_FORMULA = "C28H37N3O5S"
VINA_VERSION = "1.2.7"
VINA_SEED = 42
VINA_CPU = 1
VINA_EXHAUSTIVENESS = 16
VINA_NUM_MODES = 20
ETKDG_SEEDS = (42, 1337, 2025)
EXPECTED_NEW_DOCKING_RUNS = 36
CONTACT_CUTOFF_ANGSTROM = 4.0
MCS_EXPECTED = {"OH_BENZYL": 38, "OH_TERTBUTYL": 35, "NSUB_OH_PRESENT": 33, "NSUB_OH_DELETED": 32}
MCS_EDGES = (
    ("OH_BENZYL", "A0B0", "A1B0"),
    ("OH_TERTBUTYL", "A0B1", "A1B1"),
    ("NSUB_OH_PRESENT", "A0B0", "A0B1"),
    ("NSUB_OH_DELETED", "A1B0", "A1B1"),
)
RECEPTOR_MUTATION_SITES = (82, 84)
_AA3 = {"ALA":"A","ARG":"R","ASN":"N","ASP":"D","CYS":"C","GLN":"Q","GLU":"E","GLY":"G","HIS":"H","ILE":"I","LEU":"L","LYS":"K","MET":"M","PHE":"F","PRO":"P","SER":"S","THR":"T","TRP":"W","TYR":"Y","VAL":"V"}

CANDIDATES = moldisc016.CANDIDATES


class MOLDISC017Error(RuntimeError):
    """Fail-closed MOLDISC-017 protocol, source, or execution error."""


def _load_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MOLDISC017Error(f"could not load JSON: {path}") from exc
    if not isinstance(value, dict):
        raise MOLDISC017Error("configuration must be a JSON object")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def _candidate_from_config(item: Mapping[str, Any]) -> moldisc016.CandidateSpec:
    return moldisc016.CandidateSpec(
        str(item["variant_id"]), str(item["candidate_id"]), str(item["factor_a"]),
        str(item["factor_b"]), str(item["label"]), str(item["canonical_smiles"]),
        str(item["inchikey"]), int(item["heavy_atom_count"]),
    )


def load_program_config_v17(path: str | Path) -> dict[str, Any]:
    config = _load_json(path)
    if config.get("program_id") != PROGRAM_ID or config.get("program_version") != PROGRAM_VERSION:
        raise MOLDISC017Error("MOLDISC-017 program identity/version drifted")
    parents = config.get("parents") or {}
    p16 = parents.get("moldisc016") or {}
    if p16.get("program_scientific_hash") != PARENT_MOLDISC016_HASH or p16.get("protocol_hash") != PARENT_MOLDISC016_PROTOCOL_HASH or p16.get("measurement_transfer_allowed") is not False:
        raise MOLDISC017Error("MOLDISC-016 parent boundary drifted")
    if (parents.get("moldisc015") or {}).get("program_scientific_hash") != PARENT_MOLDISC015_HASH or (parents.get("moldisc015") or {}).get("measurement_transfer_allowed") is not False:
        raise MOLDISC017Error("MOLDISC-015 parent boundary drifted")
    if (parents.get("moldisc014") or {}).get("program_scientific_hash") != PARENT_MOLDISC014_HASH:
        raise MOLDISC017Error("MOLDISC-014 parent hash drifted")
    panel = tuple(_candidate_from_config(item) for item in config.get("panel") or ())
    if panel != CANDIDATES or len(panel) != 4:
        raise MOLDISC017Error("the frozen MOLDISC-016 four-member panel drifted")
    bounds = config.get("resource_bounds") or {}
    if bounds.get("max_campaigns") != 9 or bounds.get("max_candidates") != 4 or bounds.get("max_docking_runs") != 40 or bounds.get("planned_new_docking_runs") != 36 or bounds.get("max_failures") != 12:
        raise MOLDISC017Error("resource bounds drifted")
    target = config.get("target_panel") or {}
    for key, pdb, label in (("R1", R1_PDB, "R1_MATCHED_BACKGROUND"), ("R2", R2_PDB, "R2_V82F_I84V")):
        item = target.get(key) or {}
        if item.get("pdb_id") != pdb or item.get("native_ligand") != "JE2" or item.get("native_ligand_inchikey") != JE2_INCHIKEY or tuple(item.get("receptor_author_chains") or ()) != ("A", "B") or item.get("label") != label or item.get("resolution_angstrom") != 2.0 or item.get("ligand_author_chain") != "B" or item.get("ligand_auth_seq_id") != 1001 or not item.get("grid_hash"):
            raise MOLDISC017Error(f"{key} source boundary drifted")
    if target.get("R0", {}).get("rerun") is not False or target.get("R0", {}).get("pdb_id") != R0_PDB:
        raise MOLDISC017Error("R0 must be imported and not rerun")
    context = config.get("native_context_only") or {}
    if context.get("docking_allowed") is not False or context.get("experimental_activity_transfer_allowed") is not False:
        raise MOLDISC017Error("K57 context boundary drifted")
    for key, pdb in (("K57_WT", K57_WT_PDB), ("K57_MUTANT", K57_MUTANT_PDB)):
        item = context.get(key) or {}
        if item.get("pdb_id") != pdb or item.get("ligand") != "K57" or item.get("expected_inchikey") != K57_INCHIKEY or item.get("formula") != K57_FORMULA or item.get("ligand_auth_seq_id") != 1001:
            raise MOLDISC017Error(f"{key} context identity drifted")
    docking = config.get("docking_protocol") or {}
    expected_docking = {"rdkit_conformer_engine":"ETKDGv3","etkdg_seeds":[42,1337,2025],"vina_seed":42,"cpu":1,"exhaustiveness":16,"num_modes":20,"scoring_function":"vina","vina_version":"1.2.7","retry_count":0,"no_vina_seed_grid":True,"no_vina_exhaustiveness_grid":True}
    for key, value in expected_docking.items():
        if docking.get(key) != value:
            raise MOLDISC017Error(f"docking field {key!r} drifted")
    campaigns = config.get("campaigns") or []
    expected_ids = [f"CAMP-017-{letter}" for letter in "ABCDEFGHI"]
    if len(campaigns) != 9 or [item.get("campaign_id") for item in campaigns] != expected_ids or sum(int(item.get("planned_runs", -1)) for item in campaigns) != EXPECTED_NEW_DOCKING_RUNS:
        raise MOLDISC017Error("campaign identity or run count drifted")
    if (config.get("strict_mcs") or {}).get("expected_heavy_atoms") != MCS_EXPECTED:
        raise MOLDISC017Error("strict MCS frozen sizes drifted")
    boundaries = config.get("boundaries") or {}
    for key in ("generation_executed","candidate_selection_executed","lead_selection_executed","measurement_transfer_allowed","universal_metric_created","winner_created","adaptive_execution","new_molecules_generated"):
        if boundaries.get(key) is not False:
            raise MOLDISC017Error(f"boundary {key!r} must be false")
    claims = config.get("claims") or []
    if [item.get("claim_id") for item in claims] != [f"CLAIM-017-0{i}" for i in range(1, 8)]:
        raise MOLDISC017Error("claim set/order drifted")
    campaign_dir = Path(path).parent
    for filename in config.get("campaign_files") or ():
        campaign = _load_json(campaign_dir / filename)
        if campaign.get("campaign_id") not in set(expected_ids):
            raise MOLDISC017Error(f"campaign file identity drifted: {filename}")
    return config


def protocol_hash(config: Mapping[str, Any]) -> str:
    return sha256_json(dict(config))


def build_execution_plan(config: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    candidates = tuple(_candidate_from_config(item) for item in (config or {}).get("panel", ())) if config else CANDIDATES
    plan: list[dict[str, Any]] = []
    for receptor in ("R1", "R2"):
        for replicate in ("RUN_A", "RUN_B"):
            plan.append({"campaign_id":"CAMP-017-B","campaign_name":"JE2_NATIVE_REDOCK_DIAGNOSTIC","receptor":receptor,"ligand":"JE2","condition_key":"native_redock","run_id":f"{receptor}__native_redock__{replicate}","replicate":replicate,"vina_seed":42,"etkdg_seed":None,"exhaustiveness":16})
    for receptor, campaign, name in (("R1","CAMP-017-C","R1_PANEL_CROSSDOCK"),("R2","CAMP-017-D","R2_PANEL_CROSSDOCK")):
        for candidate in candidates:
            for seed, reps in ((42,("RUN_A","RUN_B")),(1337,("RUN_A",)),(2025,("RUN_A",))):
                for replicate in reps:
                    plan.append({"campaign_id":campaign,"campaign_name":name,"receptor":receptor,"ligand":"PANEL","candidate_id":candidate.candidate_id,"variant_id":candidate.variant_id,"candidate_key":candidate.key,"condition_key":f"etkdg_{seed}","run_id":f"{receptor}__{candidate.key}__etkdg_{seed}__{replicate}","replicate":replicate,"vina_seed":42,"etkdg_seed":seed,"exhaustiveness":16})
    if len(plan) != EXPECTED_NEW_DOCKING_RUNS or len({item["run_id"] for item in plan}) != EXPECTED_NEW_DOCKING_RUNS:
        raise MOLDISC017Error("execution plan is not exactly 36 unique new docking runs")
    return plan


def factorial_contrasts(y00: float, y10: float, y01: float, y11: float) -> dict[str, float]:
    return {"oh": 0.5 * ((y10 - y00) + (y11 - y01)), "nsub": 0.5 * ((y01 - y00) + (y11 - y10)), "interaction": (y11 - y01) - (y10 - y00)}


def sign_consistent(values: Sequence[float]) -> bool:
    if not values:
        return False
    signs = {0 if value == 0 else (1 if value > 0 else -1) for value in values}
    return len(signs) == 1


def strict_mcs(left: Chem.Mol, right: Chem.Mol, expected_name: str | None = None) -> dict[str, Any]:
    if left is None or right is None:
        raise MOLDISC017Error("strict MCS requires two chemical originals")
    result = rdFMCS.FindMCS([Chem.RemoveHs(Chem.Mol(left)), Chem.RemoveHs(Chem.Mol(right))], atomCompare=rdFMCS.AtomCompare.CompareElements, bondCompare=rdFMCS.BondCompare.CompareOrder, matchValences=True, ringMatchesRingOnly=True, completeRingsOnly=True, timeout=60)
    payload = {"rule_id":"STRICT_MAXIMUM_COMMON_HEAVY_ATOM_SUBSTRUCTURE","num_atoms":int(result.numAtoms),"num_bonds":int(result.numBonds),"smarts":result.smartsString,"atom_compare":"element identity","bond_compare":"bond order","matchValences":True,"ringMatchesRingOnly":True,"completeRingsOnly":True}
    if expected_name is not None and payload["num_atoms"] != MCS_EXPECTED[expected_name]:
        raise MOLDISC017Error(f"strict MCS {expected_name} expected {MCS_EXPECTED[expected_name]} heavy atoms, got {payload['num_atoms']}")
    return payload


def strict_mcs_manifest() -> dict[str, Any]:
    molecules = {candidate.key: Chem.MolFromSmiles(candidate.canonical_smiles) for candidate in CANDIDATES}
    result = {name: strict_mcs(molecules[left], molecules[right], name) for name, left, right in MCS_EDGES}
    return {"rule_id":"STRICT_MAXIMUM_COMMON_HEAVY_ATOM_SUBSTRUCTURE","edges":result,"expected_heavy_atoms":dict(MCS_EXPECTED),"scientific_hash":sha256_json(result)}


def _pdb_resolution(text: str) -> float:
    match = re.search(r"^REMARK\s+2\s+RESOLUTION\.\s+([0-9.]+)\s+ANGSTROMS", text, re.MULTILINE)
    if not match:
        raise MOLDISC017Error("PDB resolution is unavailable")
    return float(match.group(1))


def _mutations(text: str, chains: Sequence[str]) -> list[str]:
    values: list[str] = []
    wanted = set(chains)
    for line in text.splitlines():
        if not line.startswith("SEQADV"):
            continue
        fields = line.split()
        if len(fields) < 9 or fields[3] not in wanted:
            continue
        new = _AA3.get(fields[2])
        old = _AA3.get(fields[7])
        if new and old:
            values.append(f"{old}{fields[4]}{new}")
    return sorted(set(values), key=lambda item: (int(re.findall(r"\d+", item)[0]), item))


def _atom_chains(text: str) -> tuple[str, ...]:
    return tuple(sorted({line[21].strip() for line in text.splitlines() if line.startswith("ATOM") and line[21].strip()}))


def _ccd_identity(pdb_id: str, ligand: str, root: Path, timeout: float) -> tuple[dict[str, Any], str]:
    path = root / f"ccd-{ligand}.json"
    transport = base._download(f"https://data.rcsb.org/rest/v1/core/chemcomp/{ligand}", path, timeout=timeout)
    payload = _load_json(path)
    chem = payload.get("chem_comp") or {}
    descriptor = payload.get("rcsb_chem_comp_descriptor") or {}
    return {"component_id":ligand,"formula":chem.get("formula"),"inchikey":descriptor.get("InChIKey"),"canonical_smiles":descriptor.get("SMILES")}, transport


def _state_case(pdb_id: str, ligand: str, chain: str) -> base.RedockingCase:
    return base.RedockingCase(f"MOLDISC017-{pdb_id}", pdb_id, ligand, chain, ("A", "B"), "HIV-1 protease", 2.0, f"https://www.rcsb.org/structure/{pdb_id}")


def _prepare_receptor(path: Path, output: Path, obabel: OpenBabelEngine, timeout: float) -> str:
    result = obabel.convert(path, output, options=("-h", "--partialcharge", "gasteiger", "-xr"), timeout=timeout, protocol_id="moldisc017.receptor-openbabel.v1")
    if result.returncode != 0 or not output.is_file():
        raise MOLDISC017Error(f"receptor preparation failed: {result.stderr[-1000:]}")
    return sha256_file(output)


def run_source_audit(root: Path, *, timeout: float = 120.0, prepare_receptors: bool = True) -> dict[str, Any]:
    source_root = root / "source_audit"
    source_root.mkdir(parents=True, exist_ok=True)
    obabel = OpenBabelEngine()
    states: dict[str, Any] = {}
    fixtures = {
        "R1": (R1_PDB, "JE2", "B", ["Q7K", "L33I", "L63I"], JE2_INCHIKEY, None),
        "R2": (R2_PDB, "JE2", "B", ["Q7K", "L33I", "L63I", "V82F", "I84V"], JE2_INCHIKEY, None),
        "K57_WT": (K57_WT_PDB, "K57", "A", ["Q7K", "L33I", "L63I"], K57_INCHIKEY, K57_FORMULA),
        "K57_MUTANT": (K57_MUTANT_PDB, "K57", "B", ["Q7K", "L33I", "L63I", "V82F", "I84V"], K57_INCHIKEY, K57_FORMULA),
    }
    for label, (pdb_id, ligand, ligand_chain, expected_mutations, expected_key, expected_formula) in fixtures.items():
        case_dir = source_root / label
        case_dir.mkdir(parents=True, exist_ok=True)
        raw = case_dir / f"{pdb_id}.pdb"
        raw_sha = base._download(f"https://files.rcsb.org/download/{pdb_id}.pdb", raw, timeout=timeout)
        text = raw.read_text(encoding="utf-8", errors="replace")
        if _pdb_resolution(text) != 2.0 or not set(("A", "B")).issubset(_atom_chains(text)):
            raise MOLDISC017Error(f"source audit failed for {label}: chains/resolution")
        mutations = _mutations(text, ("A", "B"))
        if mutations != sorted(expected_mutations, key=lambda item: (int(re.findall(r"\d+", item)[0]), item)):
            raise MOLDISC017Error(f"source audit failed for {label}: mutation map {mutations}")
        extraction = base.extract_case_from_pdb(text, _state_case(pdb_id, ligand, ligand_chain))
        receptor_pdb = case_dir / "receptor_extracted.pdb"
        receptor_pdb.write_text(extraction.receptor_pdb, encoding="utf-8")
        native_sdf = case_dir / f"{ligand}_native.sdf"
        native_sha = base._download(base._instance_sdf_url(_state_case(pdb_id, ligand, ligand_chain), extraction.ligand_auth_seq_id), native_sdf, timeout=timeout)
        native = base.load_single_sdf(native_sdf)
        formula = rdMolDescriptors.CalcMolFormula(native)
        ccd, ccd_sha = _ccd_identity(pdb_id, ligand, case_dir, timeout)
        if ccd.get("inchikey") != expected_key or (expected_formula is not None and ccd.get("formula", "").replace(" ", "") != expected_formula):
            raise MOLDISC017Error(f"source audit failed for {label}: CCD identity {ccd}")
        grid = base.derive_redocking_grid(native) if ligand == "JE2" else None
        expected_grid = (("5967ad06319d2d02646f96bf9ed70769eb345d76e1e50e2ab29aedb348ed0766" if label == "R1" else "ddcc2e6bb18e78e0517380a168496db1f5fab16407861189c2f3f89842fcf40a") if ligand == "JE2" else None)
        if expected_grid and grid and grid.grid_hash != expected_grid:
            raise MOLDISC017Error(f"source audit failed for {label}: grid hash drifted")
        receptor_pdbqt = case_dir / "receptor.pdbqt"
        receptor_sha = _prepare_receptor(receptor_pdb, receptor_pdbqt, obabel, timeout) if prepare_receptors and ligand == "JE2" else None
        payload = {"label":label,"pdb_id":pdb_id,"raw_pdb_transport_sha256":raw_sha,"receptor_author_chains":["A","B"],"ligand":ligand,"ligand_author_chain":ligand_chain,"ligand_auth_seq_id":extraction.ligand_auth_seq_id,"native_sdf_transport_sha256":native_sha,"native_sdf_sha256":sha256_file(native_sdf),"native_sdf_rdkit_inchikey":inchi.MolToInchiKey(native),"ccd_transport_sha256":ccd_sha,"ccd_identity":ccd,"resolution_angstrom":_pdb_resolution(text),"mutations":mutations,"receptor_pdb_sha256":sha256_file(receptor_pdb),"receptor_pdbqt_sha256":receptor_sha,"grid":grid.to_dict() if grid else None,"context_only":ligand == "K57","docking_allowed":ligand == "JE2"}
        payload["state_hash"] = sha256_json({key:value for key,value in payload.items() if key not in {"state_hash"}})
        _write_json(case_dir / "source_state.json", payload)
        states[label] = {**payload,"receptor_pdb_path":str(receptor_pdb),"receptor_pdbqt_path":str(receptor_pdbqt) if receptor_sha else None,"native_sdf_path":str(native_sdf)}
    audit_payload = {"schema":"moldisc-017.source-audit.v1","states":states,"k57_docking_allowed":False,"experimental_activity_transfer_allowed":False}
    result = {**audit_payload,"source_audit_hash":sha256_json(audit_payload)}
    _write_json(source_root / "source-audit.json", result)
    return result


def _prepare_conformer(molecule: Chem.Mol, seed: int, path: Path) -> dict[str, Any]:
    prepared = Chem.AddHs(Chem.Mol(molecule))
    prepared.RemoveAllConformers()
    params = AllChem.ETKDGv3()
    params.randomSeed = int(seed)
    if AllChem.EmbedMolecule(prepared, params) != 0:
        raise MOLDISC017Error(f"ETKDGv3 failed for seed {seed}")
    uff = False
    if AllChem.UFFHasAllMoleculeParams(prepared):
        AllChem.UFFOptimizeMolecule(prepared, maxIters=1000)
        uff = True
    writer = Chem.SDWriter(str(path))
    writer.write(prepared)
    writer.close()
    return {"etkdg_seed":seed,"uff_optimized":uff,"sha256":sha256_file(path),"inchikey":inchi.MolToInchiKey(molecule)}


def _prepare_ligand(candidate: moldisc016.CandidateSpec, seed: int, root: Path, obabel: OpenBabelEngine, timeout: float) -> dict[str, Any]:
    directory = root / "prepared" / candidate.key / f"etkdg_{seed}"
    directory.mkdir(parents=True, exist_ok=False)
    sdf = directory / "starting_conformer.sdf"
    conformer = _prepare_conformer(Chem.MolFromSmiles(candidate.canonical_smiles), seed, sdf)
    pdbqt = directory / "ligand.pdbqt"
    result = obabel.convert(sdf, pdbqt, options=("-h", "--partialcharge", "gasteiger"), timeout=timeout, protocol_id="moldisc017.ligand-openbabel.v1")
    if result.returncode != 0 or not pdbqt.is_file():
        raise MOLDISC017Error(f"ligand preparation failed: {result.stderr[-1000:]}")
    return {**conformer,"sdf_path":str(sdf),"pdbqt_path":str(pdbqt),"pdbqt_sha256":sha256_file(pdbqt),"ligand_scientific_identity":moldisc016._pdbqt_scientific_identity(pdbqt, f"{candidate.key} ligand")}


def _run_vina(spec: Mapping[str, Any], *, root: Path, receptor: Mapping[str, Any], ligand_path: Path, vina: VinaEngine) -> dict[str, Any]:
    run_root = root / "runs" / str(spec["run_id"])
    run_root.mkdir(parents=True, exist_ok=False)
    _write_json(run_root / "protocol_parameters.json", dict(spec))
    output = run_root / "vina_poses.pdbqt"
    grid = receptor["grid"]
    request = DockingRequest(receptor_path=str(receptor["receptor_pdbqt_path"]), ligand_path=str(ligand_path), grid=GridBox(grid["center_x"],grid["center_y"],grid["center_z"],grid["size_x"],grid["size_y"],grid["size_z"]), exhaustiveness=VINA_EXHAUSTIVENESS, cpu=VINA_CPU, seed=VINA_SEED, output_path=str(output), target_id=f"MOLDISC017:{spec['receptor']}:{spec.get('candidate_id', 'JE2')}", role="NON_COGNATE_HOLO_CROSSDOCKING", protocol_id="research-os.moldisc-017.receptor-state.v1", timeout=1200.0, num_modes=VINA_NUM_MODES)
    result = vina.run(request)
    record = {**dict(spec),"vina_version":vina.version,"output_path":str(output),"engine_returncode":result.returncode,"technical_status":"PASS" if result.returncode == 0 and output.is_file() else "NONPASS","generation_executed":False,"candidate_selection_executed":False}
    if record["technical_status"] != "PASS":
        record.update({"first_loss":"DOCKING_FAIL","pose_count":0,"pose_scores_kcal_mol":[],"pose_1_score_kcal_mol":None,"error":result.stderr[-4000:]})
    else:
        text = output.read_text(encoding="utf-8", errors="replace")
        models = base.split_vina_pdbqt_models(text)
        scores = [float(value) for value in base.parse_vina_pose_scores(text)]
        if len(models) != len(scores) or not models or len(models) > VINA_NUM_MODES or any(not math.isfinite(value) for value in scores):
            record.update({"technical_status":"NONPASS","first_loss":"NO_VALID_POSES","pose_count":0,"pose_scores_kcal_mol":[],"pose_1_score_kcal_mol":None})
        else:
            record.update({"first_loss":None,"pose_count":len(models),"pose_scores_kcal_mol":scores,"pose_1_score_kcal_mol":scores[0],"vina_output_scientific_hash":moldisc016._vina_scientific_identity(models,scores),"vina_output_transport_sha256":sha256_file(output)})
    _write_json(run_root / "run_manifest.json", record)
    return record


def _failure_record(spec: Mapping[str, Any], reason: str, status: str = "SKIPPED_DEPENDENCY") -> dict[str, Any]:
    return {**dict(spec),"technical_status":status,"first_loss":reason,"pose_count":0,"pose_scores_kcal_mol":[],"pose_1_score_kcal_mol":None,"generation_executed":False,"candidate_selection_executed":False}


def _load_r0_import(artifact: str | Path | None, root: Path) -> dict[str, Any]:
    validation = _load_json(Path("validation/moldisc-016-first-run-v1.json"))
    if validation.get("program_identity", {}).get("program_scientific_hash") != PARENT_MOLDISC016_HASH:
        raise MOLDISC017Error("MOLDISC-016 imported validation hash drifted")
    source = Path(artifact) if artifact else None
    summary = {row["cell"]: row for row in validation.get("summary_matrix", {}).get("rows", [])}
    records: dict[str, Any] = {}
    if source and source.is_dir():
        for candidate in CANDIDATES:
            for seed in ETKDG_SEEDS:
                run_id = f"{candidate.key}__baseline__RUN_A" if seed == 42 else f"{candidate.key}__etkdg_seed_{seed}"
                directory = source / "runs" / run_id
                manifest = directory / "run_manifest.json"
                pose = directory / f"{candidate.key}_vina_poses.pdbqt"
                if manifest.is_file() and pose.is_file():
                    record = _load_json(manifest)
                    record["output_path"] = str(pose)
                    records[f"R0__{candidate.key}__etkdg_{seed}__RUN_A"] = record
                    continue
                source = None
                break
            if source is None:
                break
    for candidate in CANDIDATES:
        row = summary.get(candidate.key, {})
        for seed, field in ((42,"vina_seed_42"),(1337,"etkdg_1337"),(2025,"etkdg_2025")):
            key = f"R0__{candidate.key}__etkdg_{seed}__RUN_A"
            records.setdefault(key, {"receptor":"R0","candidate_key":candidate.key,"candidate_id":candidate.candidate_id,"condition_key":f"etkdg_{seed}","etkdg_seed":seed,"technical_status":"IMPORTED_SCORE_ONLY","pose_1_score_kcal_mol":row.get(field),"pose_count":row.get("baseline_pose_count"),"output_path":None,"imported_from":"validation/moldisc-016-first-run-v1.json"})
    receptor_pdb = (Path(artifact) / "target_snapshot" / "receptor_extracted.pdb") if artifact else None
    payload = {"source_artifact":str(artifact) if artifact else None,"source_artifact_available":bool(artifact and Path(artifact).is_dir()),"records":records,"receptor_pdb_path":str(receptor_pdb) if receptor_pdb and receptor_pdb.is_file() else None,"parent_validation_hash":sha256_file(Path("validation/moldisc-016-first-run-v1.json"))}
    _write_json(root / "r0_import.json", payload)
    return payload


def _load_pose_models(record: Mapping[str, Any], obabel: OpenBabelEngine, root: Path) -> list[Chem.Mol]:
    output = record.get("output_path")
    if not output or not Path(output).is_file():
        return []
    source = Path(output)
    text = source.read_text(encoding="utf-8", errors="replace")
    models = base.split_vina_pdbqt_models(text)
    result: list[Chem.Mol] = []
    directory = root / "converted-poses" / source.parent.name
    directory.mkdir(parents=True, exist_ok=True)
    for index, model in enumerate(models, start=1):
        pdbqt = directory / f"pose-{index:02d}.pdbqt"
        sdf = directory / f"pose-{index:02d}.sdf"
        if not sdf.is_file():
            pdbqt.write_text(model, encoding="utf-8")
            conversion = obabel.convert(pdbqt, sdf, timeout=120.0, protocol_id="moldisc017.pose-openbabel.v1")
            if conversion.returncode != 0 or not sdf.is_file():
                continue
        try:
            result.append(base.load_single_sdf(sdf))
        except (OSError, ValueError):
            continue
    return result


def _heavy_coords(molecule: Chem.Mol) -> list[tuple[float, float, float]]:
    if molecule.GetNumConformers() != 1:
        raise MOLDISC017Error("pose must have exactly one conformer")
    conf = molecule.GetConformer()
    return [(float(conf.GetAtomPosition(index).x),float(conf.GetAtomPosition(index).y),float(conf.GetAtomPosition(index).z)) for index, atom in enumerate(molecule.GetAtoms()) if atom.GetAtomicNum() != 1]


def _rmsd_pairs(left: Sequence[Sequence[float]], right: Sequence[Sequence[float]], pairs: Sequence[tuple[int,int]] | None = None) -> float:
    pairs = pairs or [(index,index) for index in range(min(len(left),len(right)))]
    if not pairs:
        raise MOLDISC017Error("RMSD mapping is empty")
    return math.sqrt(sum(sum((float(left[i][axis])-float(right[j][axis]))**2 for axis in range(3)) for i,j in pairs)/len(pairs))


def _receptor_atoms(path: Path) -> list[dict[str, Any]]:
    values = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("ATOM"):
            continue
        element = (line[76:78].strip() or line[12:16].strip()[:1]).upper()
        if element in {"H","D"}:
            continue
        values.append({"chain":line[21].strip(),"residue_name":line[17:20].strip(),"residue_sequence":line[22:26].strip(),"insertion_code":line[26].strip(),"atom_name":line[12:16].strip(),"x":float(line[30:38]),"y":float(line[38:46]),"z":float(line[46:54])})
    if not values:
        raise MOLDISC017Error(f"receptor has no heavy atoms: {path}")
    return values


def _kabsch_from_pdbs(reference: Path, moving: Path) -> dict[str, Any]:
    def cas(path: Path) -> dict[tuple[str,str,str,str], tuple[float,float,float]]:
        out = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("ATOM") and line[12:16].strip() == "CA" and line[21].strip() in {"A","B"} and line[22:26].strip() not in {"82","84"}:
                key=(line[21].strip(),line[22:26].strip(),line[26].strip(),line[17:20].strip())
                out[key]=(float(line[30:38]),float(line[38:46]),float(line[46:54]))
        return out
    ref, mov = cas(reference), cas(moving)
    if set(ref) != set(mov) or len(ref) < 3:
        common = sorted(set(ref) & set(mov))
        if len(common) < 3:
            raise MOLDISC017Error("receptor alignment lacks matched C-alpha atoms")
    keys = sorted(set(ref) & set(mov))
    p = np.asarray([mov[key] for key in keys], dtype=float)
    q = np.asarray([ref[key] for key in keys], dtype=float)
    pc, qc = p.mean(axis=0), q.mean(axis=0)
    covariance = (p-pc).T @ (q-qc)
    u, _, vt = np.linalg.svd(covariance)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1,:] *= -1
        rotation = vt.T @ u.T
    translation = qc - rotation @ pc
    transformed = (rotation @ p.T).T + translation
    rmsd = float(np.sqrt(np.mean(np.sum((transformed-q)**2, axis=1))))
    payload = {"algorithm":"KABSCH","chain_mapping":{"A":"A","B":"B"},"atom_selection":"C-alpha; author residue number; residue identity; excluding 82 and 84","atom_count":len(keys),"keys_hash":sha256_json(keys),"receptor_backbone_rmsd_angstrom":rmsd,"rotation":rotation.round(12).tolist(),"translation":translation.round(12).tolist()}
    payload["alignment_hash"] = sha256_json({key:value for key,value in payload.items() if key != "alignment_hash"})
    return payload


def kabsch_align(reference: Sequence[Sequence[float]], moving: Sequence[Sequence[float]]) -> dict[str, Any]:
    """Public small synthetic-testable Kabsch implementation."""
    p, q = np.asarray(moving, dtype=float), np.asarray(reference, dtype=float)
    if p.shape != q.shape or p.ndim != 2 or p.shape[1] != 3 or len(p) < 3:
        raise MOLDISC017Error("Kabsch requires equal Nx3 arrays with N>=3")
    pc, qc = p.mean(axis=0), q.mean(axis=0)
    u, _, vt = np.linalg.svd((p-pc).T @ (q-qc))
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1,:] *= -1
        rotation = vt.T @ u.T
    translation = qc - rotation @ pc
    return {"rotation":rotation.tolist(),"translation":translation.tolist(),"rmsd_angstrom":float(np.sqrt(np.mean(np.sum(((rotation @ p.T).T+translation-q)**2,axis=1)))),"atom_count":len(p)}


def _apply_transform(molecule: Chem.Mol, alignment: Mapping[str, Any]) -> list[tuple[float,float,float]]:
    rotation=np.asarray(alignment["rotation"],dtype=float); translation=np.asarray(alignment["translation"],dtype=float)
    coords=np.asarray(_heavy_coords(molecule),dtype=float)
    return ((rotation @ coords.T).T+translation).tolist()


def _score_matrix(records: Mapping[str, Mapping[str, Any]], receptor: str) -> dict[str, dict[str, float | None]]:
    result = {candidate.key:{} for candidate in CANDIDATES}
    for candidate in CANDIDATES:
        for seed in ETKDG_SEEDS:
            run_id = f"{receptor}__{candidate.key}__etkdg_{seed}__RUN_A"
            record = records.get(run_id, {})
            result[candidate.key][str(seed)] = record.get("pose_1_score_kcal_mol") if record.get("technical_status") == "PASS" else None
    return result


def _r0_score_matrix(r0: Mapping[str, Any]) -> dict[str, dict[str, float | None]]:
    result={candidate.key:{} for candidate in CANDIDATES}
    for candidate in CANDIDATES:
        for seed in ETKDG_SEEDS:
            result[candidate.key][str(seed)] = r0["records"].get(f"R0__{candidate.key}__etkdg_{seed}__RUN_A",{}).get("pose_1_score_kcal_mol")
    return result


def _factorial_matrix(scores: Mapping[str, Mapping[str, float | None]], receptor: str) -> dict[str, Any]:
    by_seed: dict[str, Any] = {}
    for seed in map(str, ETKDG_SEEDS):
        values={key:scores[key].get(seed) for key in ("A0B0","A1B0","A0B1","A1B1")}
        if any(value is None for value in values.values()):
            by_seed[seed]={"status":"INDETERMINATE_MISSING_CONDITION","values_by_cell":values,"contrasts":None}
        else:
            by_seed[seed]={"status":"PASS","values_by_cell":values,"contrasts":factorial_contrasts(float(values["A0B0"]),float(values["A1B0"]),float(values["A0B1"]),float(values["A1B1"]))}
    summary={}
    for field in ("oh","nsub","interaction"):
        values=[item["contrasts"][field] for item in by_seed.values() if item["status"]=="PASS"]
        summary[field]={"values":values,"minimum":min(values) if values else None,"maximum":max(values) if values else None,"range":max(values)-min(values) if values else None,"median":statistics.median(values) if values else None,"signs":[0 if x==0 else (1 if x>0 else -1) for x in values],"sign_consistent":sign_consistent(values),"status":"PASS" if len(values)==3 and sign_consistent(values) else ("CONTRADICTS" if len(values)==3 else "INDETERMINATE")}
    payload={"receptor":receptor,"conditions":[str(seed) for seed in ETKDG_SEEDS],"scores":scores,"contrasts_by_seed":by_seed,"sign_summary":summary,"mode":"DESCRIPTIVE_ONLY"}
    return {**payload,"factorial_scientific_hash":sha256_json(payload)}


def _mutation_shifts(factorials: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    result={}
    for field in ("oh","nsub","interaction"):
        values=[]
        for seed in map(str, ETKDG_SEEDS):
            r1=factorials["R1"]["contrasts_by_seed"].get(seed,{}).get("contrasts")
            r2=factorials["R2"]["contrasts_by_seed"].get(seed,{}).get("contrasts")
            if r1 and r2: values.append(r2[field]-r1[field])
        result[field]={"values":values,"minimum":min(values) if values else None,"maximum":max(values) if values else None,"range":max(values)-min(values) if values else None,"median":statistics.median(values) if values else None,"signs":[0 if x==0 else (1 if x>0 else -1) for x in values],"sign_consistent":sign_consistent(values),"status":"PASS" if len(values)==3 and sign_consistent(values) else ("CONTRADICTS" if len(values)==3 else "INDETERMINATE")}
    return {"mutation_shift_definition":"R2-R1","by_contrast":result,"scientific_hash":sha256_json(result)}


def _contact_profile(molecules: Sequence[Chem.Mol], receptor_atoms: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    residues=sorted({(a["chain"],a["residue_name"],a["residue_sequence"],a["insertion_code"]) for a in receptor_atoms})
    pose_sets=[]
    for molecule in molecules:
        coords=_heavy_coords(molecule); found=set()
        for atom in receptor_atoms:
            xyz=(atom["x"],atom["y"],atom["z"])
            if any(sum((point[i]-xyz[i])**2 for i in range(3)) <= CONTACT_CUTOFF_ANGSTROM**2 for point in coords):
                found.add((atom["chain"],atom["residue_name"],atom["residue_sequence"],atom["insertion_code"]))
        pose_sets.append(found)
    rank1=sorted(pose_sets[0]) if pose_sets else []
    return {"rank1_contact_residues":[{"chain":x[0],"residue_name":x[1],"residue_sequence":x[2],"insertion_code":x[3]} for x in rank1],"rank1_contact_fingerprint_hash":sha256_json(rank1),"ensemble_contact_profile":[{"residue":list(residue),"poses_in_contact":sum(residue in current for current in pose_sets),"pose_fraction_in_contact":sum(residue in current for current in pose_sets)/len(pose_sets) if pose_sets else None} for residue in residues if any(residue in current for current in pose_sets)],"pose_count":len(pose_sets)}


def _mutation_site_profile(molecules: Sequence[Chem.Mol], receptor_atoms: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result={}
    for chain in ("A","B"):
        for sequence in RECEPTOR_MUTATION_SITES:
            atoms=[atom for atom in receptor_atoms if atom["chain"]==chain and atom["residue_sequence"].strip()==str(sequence)]
            distances=[]; contacts=0
            for molecule in molecules:
                ligand=_heavy_coords(molecule)
                distance=min((math.sqrt(sum((point[i]-atom[axis])**2 for i,axis in enumerate(("x","y","z")))) for point in ligand for atom in atoms),default=None)
                distances.append(distance)
                contacts += int(distance is not None and distance <= CONTACT_CUTOFF_ANGSTROM)
            result[f"{chain}:{sequence}"]={"residue_identity":sorted({atom["residue_name"] for atom in atoms}),"contact_present_rank1":bool(distances and distances[0] is not None and distances[0] <= CONTACT_CUTOFF_ANGSTROM),"minimum_distance_rank1_angstrom":distances[0] if distances else None,"pose_fraction_in_contact":contacts/len(molecules) if molecules else None}
    return result


def _compare_sets(left: set[str], right: set[str]) -> dict[str, Any]:
    union=left|right; intersection=left&right
    return {"intersection":sorted(intersection),"union":sorted(union),"jaccard":len(intersection)/len(union) if union else None,"gained":sorted(right-left),"lost":sorted(left-right)}


def _geometry_analysis(records: Mapping[str, Mapping[str, Any]], source: Mapping[str, Any], r0: Mapping[str, Any], root: Path, obabel: OpenBabelEngine) -> dict[str, Any]:
    originals={candidate.key:Chem.MolFromSmiles(candidate.canonical_smiles) for candidate in CANDIDATES}
    mcs=strict_mcs_manifest()
    pose_cache: dict[str,list[Chem.Mol]]={}
    def poses(run_id: str) -> list[Chem.Mol]:
        if run_id not in pose_cache: pose_cache[run_id]=_load_pose_models(records.get(run_id,{}) or r0["records"].get(run_id,{}),obabel,root)
        return pose_cache[run_id]
    edge_results={}
    for receptor in ("R0","R1","R2"):
        edge_results[receptor]={}
        for name,left,right in MCS_EDGES:
            left_id=(f"R0__{left}__etkdg_42__RUN_A" if receptor=="R0" else f"{receptor}__{left}__etkdg_42__RUN_A")
            right_id=(f"R0__{right}__etkdg_42__RUN_A" if receptor=="R0" else f"{receptor}__{right}__etkdg_42__RUN_A")
            lp,rp=poses(left_id),poses(right_id)
            if not lp or not rp:
                edge_results[receptor][name]={"status":"INDETERMINATE","reason":"imported or crossdock pose ensemble unavailable","rank1_rmsd_angstrom":None}
                continue
            pattern=Chem.MolFromSmarts(mcs["edges"][name]["smarts"])
            left_match=Chem.RemoveHs(originals[left]).GetSubstructMatch(pattern); right_match=Chem.RemoveHs(originals[right]).GetSubstructMatch(pattern)
            pairs=list(zip(left_match,right_match))
            value=_rmsd_pairs(_heavy_coords(lp[0]),_heavy_coords(rp[0]),pairs)
            edge_results[receptor][name]={"status":"PASS","common_core_heavy_atoms":len(pairs),"rank1_rmsd_angstrom":value,"expected_heavy_atoms":MCS_EXPECTED[name]}
    alignment=_kabsch_from_pdbs(Path(source["states"]["R1"]["receptor_pdb_path"]),Path(source["states"]["R2"]["receptor_pdb_path"]))
    cross={}
    for candidate in CANDIDATES:
        r1=poses(f"R1__{candidate.key}__etkdg_42__RUN_A"); r2=poses(f"R2__{candidate.key}__etkdg_42__RUN_A")
        if not r1 or not r2: cross[candidate.key]={"status":"INDETERMINATE"}; continue
        r2coords=_apply_transform(r2[0],alignment); pairs=[(i,i) for i in range(min(len(_heavy_coords(r1[0])),len(r2coords)))]
        cross[candidate.key]={"status":"PASS","rank1_R1_to_rank1_R2_aligned_rmsd_angstrom":_rmsd_pairs(_heavy_coords(r1[0]),r2coords,pairs),"minimum_R1_rank1_to_R2_ensemble_angstrom":min(_rmsd_pairs(_heavy_coords(r1[0]),_apply_transform(m,alignment),pairs) for m in r2),"minimum_R2_rank1_to_R1_ensemble_angstrom":min(_rmsd_pairs(_heavy_coords(r1m),r2coords,pairs) for r1m in r1)}
    native_je2_r1=base.load_single_sdf(source["states"]["R1"]["native_sdf_path"]); native_je2_r2=base.load_single_sdf(source["states"]["R2"]["native_sdf_path"])
    je2_rmsd=_rmsd_pairs(_heavy_coords(native_je2_r1),_apply_transform(native_je2_r2,alignment))
    k57_wt=base.load_single_sdf(source["states"]["K57_WT"]["native_sdf_path"]); k57_mut=base.load_single_sdf(source["states"]["K57_MUTANT"]["native_sdf_path"])
    k57_alignment=_kabsch_from_pdbs(Path(source["states"]["K57_WT"]["receptor_pdb_path"]),Path(source["states"]["K57_MUTANT"]["receptor_pdb_path"]))
    payload={"metric":"STRICT_MCS_RECEPTOR_FRAME_AND_ALIGNED_CROSS_RECEPTOR_RMSD","no_rigid_body_alignment_within_receptor":True,"strict_mcs":mcs,"same_receptor_edges":edge_results,"r1_r2_receptor_alignment":alignment,"cross_receptor_rank1_endpoints":cross,"native_je2_r1_r2_aligned_rmsd_angstrom":je2_rmsd,"native_k57_wt_mutant_aligned_rmsd_angstrom":_rmsd_pairs(_heavy_coords(k57_wt),_apply_transform(k57_mut,k57_alignment))}
    return {**payload,"geometry_scientific_hash":sha256_json(payload)}


def _contact_analysis(records: Mapping[str, Mapping[str, Any]], source: Mapping[str, Any], root: Path, obabel: OpenBabelEngine) -> dict[str, Any]:
    profiles={}
    mutation_profiles={}
    cache={}
    for receptor in ("R1","R2"):
        receptor_atoms=_receptor_atoms(Path(source["states"][receptor]["receptor_pdb_path"]))
        for candidate in CANDIDATES:
            run_id=f"{receptor}__{candidate.key}__etkdg_42__RUN_A"
            molecules=cache.setdefault(run_id,_load_pose_models(records.get(run_id,{}),obabel,root))
            profiles[f"{receptor}:{candidate.key}"]=_contact_profile(molecules,receptor_atoms) if molecules else {"status":"INDETERMINATE"}
            mutation_profiles[f"{receptor}:{candidate.key}"]=_mutation_site_profile(molecules,receptor_atoms) if molecules else {}
    changes={}
    for candidate in CANDIDATES:
        r1=profiles.get(f"R1:{candidate.key}",{}); r2=profiles.get(f"R2:{candidate.key}",{})
        left={f"{x['chain']}:{x['residue_sequence']}" for x in r1.get("rank1_contact_residues",[])}; right={f"{x['chain']}:{x['residue_sequence']}" for x in r2.get("rank1_contact_residues",[])}
        changes[candidate.key]=_compare_sets(left,right)
    payload={"cutoff_angstrom":CONTACT_CUTOFF_ANGSTROM,"rank1_and_ensemble_profiles":profiles,"mutation_site_profiles":mutation_profiles,"r1_r2_contact_changes":changes,"energy_or_interaction_classification":False}
    return {**payload,"contact_scientific_hash":sha256_json(payload)}


def _claim_synthesis(source: Mapping[str, Any], records: Mapping[str, Mapping[str, Any]], factorials: Mapping[str, Mapping[str, Any]], shifts: Mapping[str, Any], geometry: Mapping[str, Any], r0: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    new_records=[record for record in records.values() if record.get("campaign_id") in {"CAMP-017-B","CAMP-017-C","CAMP-017-D"}]
    claim={"CLAIM-017-01":"SUPPORTS" if len(new_records)==36 and all(record.get("technical_status") in {"PASS","NONPASS","SKIPPED_DEPENDENCY"} for record in new_records) and source.get("source_audit_hash") else "INDETERMINATE","CLAIM-017-02":"SUPPORTS" if all(factorials[x]["sign_summary"]["oh"]["status"]=="PASS" for x in ("R0","R1","R2")) else ("CONTRADICTS" if all(factorials[x]["sign_summary"]["oh"]["status"]=="CONTRADICTS" for x in ("R0","R1","R2")) else "INDETERMINATE"),"CLAIM-017-03":"SUPPORTS" if all(factorials[x]["sign_summary"]["nsub"]["status"]=="PASS" for x in ("R0","R1","R2")) else ("CONTRADICTS" if all(factorials[x]["sign_summary"]["nsub"]["status"]=="CONTRADICTS" for x in ("R0","R1","R2")) else "INDETERMINATE"),"CLAIM-017-04":"SUPPORTS" if all(factorials[x]["sign_summary"]["interaction"]["status"]=="PASS" for x in ("R0","R1","R2")) else ("CONTRADICTS" if all(factorials[x]["sign_summary"]["interaction"]["status"]=="CONTRADICTS" for x in ("R0","R1","R2")) else "INDETERMINATE"),"CLAIM-017-05":"SUPPORTS" if shifts["by_contrast"]["nsub"]["status"]=="PASS" else ("CONTRADICTS" if shifts["by_contrast"]["nsub"]["status"]=="CONTRADICTS" else "INDETERMINATE"),"CLAIM-017-06":"SUPPORTS" if all(item.get("common_core_heavy_atoms",item.get("num_atoms"))==MCS_EXPECTED[name] for name in MCS_EXPECTED for item in [geometry["strict_mcs"]["edges"][name]]) else "INDETERMINATE","CLAIM-017-07":"SUPPORTS"}
    synthesis={"evidence_ceiling":"E2_COMPUTATIONAL","claim_status":claim,"source_measurement_transfer_allowed":False,"generation_executed":False,"candidate_selection_executed":False,"lead_selection_executed":False,"universal_metric_created":False,"winner_created":False,"interpretation_boundary":"Docking scores, redocking RMSD, aligned geometry, strict-MCS geometry, and 4.0 Å contacts are descriptive computational endpoints only; no affinity, potency, resistance, efficacy, or clinical claim is made."}
    knowledge={"new_evidence_ids":["MOLDISC-017-E2-RECEPTOR-STATE-PANEL"],"resolved_gap_ids":["GAP-SINGLE-RECEPTOR-STRUCTURE-LIMITATION"],"partially_resolved_gap_ids":["GAP-DOCKING-PROTOCOL-SENSITIVITY","GAP-NONCOGNATE-CAPABILITY"],"new_gap_ids":["GAP-EXPERIMENTAL-RESISTANCE-VALIDATION","GAP-EXPERIMENTAL-BINDING-VALIDATION"],"unresolved_uncertainty":["computational receptor-state differences are not experimental resistance measurements","K57 quartet is structural context only","non-cognate capability remains computational"],"summary":"MOLDISC-017 adds a bounded matched JE2 receptor-state challenge and descriptive mutation-site geometry while retaining the MOLDISC-016 four-member panel and all evidence boundaries.","scientific_hash":sha256_json(synthesis)}
    return synthesis,knowledge


def run_moldisc_017(*, config_path: str | Path, output_root: str | Path, timeout: float = 120.0, moldisc016_artifact: str | Path | None = None, source_audit_only: bool = False) -> dict[str, Any]:
    config=load_program_config_v17(config_path)
    plan=build_execution_plan(config)
    root=Path(output_root); root.mkdir(parents=True,exist_ok=False)
    _write_json(root/"program_protocol_payload.json",config)
    source=run_source_audit(root,timeout=timeout,prepare_receptors=not source_audit_only)
    strict_mcs_manifest()
    if source_audit_only:
        return {"program_id":PROGRAM_ID,"program_protocol_hash":protocol_hash(config),"source_audit_hash":source["source_audit_hash"],"source_audit_only":True}
    r0=_load_r0_import(moldisc016_artifact,root)
    if not r0.get("source_artifact_available"):
        raise MOLDISC017Error("R0 imported MOLDISC-016 artifact is required for full execution; no R0 rerun is permitted")
    obabel=OpenBabelEngine(); vina=VinaEngine()
    if not obabel.available or not vina.available or not vina.version or VINA_VERSION not in vina.version:
        raise MOLDISC017Error(f"ENGINE_UNAVAILABLE: Open Babel and Vina {VINA_VERSION} are required")
    receptors={label:state for label,state in source["states"].items() if label in {"R1","R2"}}
    prepared={}
    for candidate in CANDIDATES:
        for seed in ETKDG_SEEDS:
            prepared[(candidate.key,seed)]=_prepare_ligand(candidate,seed,root,obabel,timeout)
    native_prepared={}
    for receptor in ("R1","R2"):
        directory=root/"prepared"/receptor; directory.mkdir(parents=True,exist_ok=True)
        sdf=Path(receptors[receptor]["native_sdf_path"]); pdbqt=directory/"native_je2.pdbqt"
        conversion=obabel.convert(sdf,pdbqt,options=("-h","--partialcharge","gasteiger"),timeout=timeout,protocol_id="moldisc017.native-openbabel.v1")
        if conversion.returncode != 0 or not pdbqt.is_file(): raise MOLDISC017Error(f"native ligand preparation failed for {receptor}")
        native_prepared[receptor]=pdbqt
    records={}; failures=0
    for spec in plan:
        try:
            if spec["campaign_id"]=="CAMP-017-B": ligand=native_prepared[spec["receptor"]]
            else: ligand=Path(prepared[(spec["candidate_key"],int(spec["etkdg_seed"]))]["pdbqt_path"])
            records[spec["run_id"]]=_run_vina(spec,root,receptors[spec["receptor"]],ligand,vina)
        except (OSError,ValueError,RuntimeError,MOLDISC017Error) as exc:
            records[spec["run_id"]]=_failure_record(spec,"EXECUTION_INDETERMINATE","NONPASS"); records[spec["run_id"]]["error"]=str(exc); _write_json(root/"runs"/spec["run_id"]/"run_manifest.json",records[spec["run_id"]])
        if records[spec["run_id"]].get("technical_status")!="PASS": failures+=1
    redock={}
    for receptor in ("R1","R2"):
        values=[]
        for replicate in ("RUN_A","RUN_B"):
            record=records[f"{receptor}__native_redock__{replicate}"]; poses=_load_pose_models(record,obabel,root)
            reference=base.load_single_sdf(receptors[receptor]["native_sdf_path"]); rmsds=[]
            for pose in poses:
                rms=base.symmetry_aware_heavy_atom_rmsd(reference,pose).rmsd_angstrom
                if rms is not None: rmsds.append(float(rms))
            values.append({"status":record.get("technical_status"),"rank1_rmsd_angstrom":rmsds[0] if rmsds else None,"minimum_rmsd_angstrom":min(rmsds) if rmsds else None,"minimum_rmsd_rank":(rmsds.index(min(rmsds))+1) if rmsds else None,"pose_count":len(poses),"classification":"NATIVE_POSE_RECOVERY_LIMITATION" if rmsds and rmsds[0]>2.0 else "DIAGNOSTIC"})
        redock[receptor]={"run_a":values[0],"run_b":values[1]}
    factorials={"R0":_factorial_matrix(_r0_score_matrix(r0),"R0"),"R1":_factorial_matrix(_score_matrix(records,"R1"),"R1"),"R2":_factorial_matrix(_score_matrix(records,"R2"),"R2")}
    shifts=_mutation_shifts(factorials)
    geometry=_geometry_analysis(records,source,r0,root,obabel)
    contacts=_contact_analysis(records,source,root,obabel)
    synthesis,knowledge=_claim_synthesis(source,records,factorials,shifts,geometry,r0)
    campaign_hashes={"source_audit_hash":source["source_audit_hash"],"redock_campaign_hash":sha256_json(redock),"r1_campaign_hash":sha256_json([records[x["run_id"]] for x in plan if x["campaign_id"]=="CAMP-017-C"]),"r2_campaign_hash":sha256_json([records[x["run_id"]] for x in plan if x["campaign_id"]=="CAMP-017-D"]),"geometry_campaign_hash":geometry["geometry_scientific_hash"],"contact_campaign_hash":contacts["contact_scientific_hash"],"factorial_campaign_hash":sha256_json(factorials),"crystal_context_hash":sha256_json({key:source["states"][key] for key in ("K57_WT","K57_MUTANT")}),"synthesis_hash":sha256_json(synthesis)}
    scientific={"program_id":PROGRAM_ID,"program_version":PROGRAM_VERSION,"program_protocol_hash":protocol_hash(config),"parent_hashes":{"moldisc016":PARENT_MOLDISC016_HASH,"moldisc015":PARENT_MOLDISC015_HASH,"moldisc014":PARENT_MOLDISC014_HASH},"source_audit_hash":source["source_audit_hash"],"redocking":redock,"factorials":factorials,"mutation_shifts":shifts,"geometry_hash":geometry["geometry_scientific_hash"],"contact_hash":contacts["contact_scientific_hash"],"campaign_hashes":campaign_hashes,"records":[{key:value for key,value in records[item["run_id"]].items() if key not in {"error"}} for item in plan],"generation_executed":False,"candidate_selection_executed":False,"lead_selection_executed":False,"source_measurement_transfer_allowed":False,"evidence_ceiling":"E2_COMPUTATIONAL"}
    program_scientific_hash=sha256_json(scientific)
    executed=sum(record.get("technical_status") in {"PASS","NONPASS"} for record in records.values()); nonpass=sum(record.get("technical_status")!="PASS" for record in records.values())
    manifest={"schema_version":"research-os.molecular-discovery.megacampaign-result.v1","program_id":PROGRAM_ID,"program_version":PROGRAM_VERSION,"status":"CLOSED_FIRST_RESULT_PRESERVED","program_protocol_hash":protocol_hash(config),"program_scientific_hash":program_scientific_hash,"parent_hashes":scientific["parent_hashes"],"docking_runs_planned":36,"docking_runs_executed":executed,"docking_runs_skipped":36-executed,"docking_runs_nonpass":nonpass,"source_audit_hash":source["source_audit_hash"],"campaign_hashes":campaign_hashes,"redocking":redock,"factorials":factorials,"mutation_shifts":shifts,"geometry":geometry,"contacts":contacts,"claims":synthesis["claim_status"],"knowledge_gain_summary":knowledge["summary"],"generation_executed":False,"candidate_selection_executed":False,"lead_selection_executed":False,"source_measurement_transfer_allowed":False,"new_molecules_generated":False}
    _write_json(root/"program_manifest.json",manifest); _write_json(root/"program_scientific_payload.json",scientific); _write_json(root/"redocking_analysis.json",redock); _write_json(root/"factorial_analysis.json",factorials); _write_json(root/"mutation_shifts.json",shifts); _write_json(root/"geometry_analysis.json",geometry); _write_json(root/"contact_analysis.json",contacts); _write_json(root/"program_synthesis.json",synthesis); _write_json(root/"knowledge_gain.json",knowledge)
    validation={"schema_version":"research-os.molecular-discovery.megacampaign-validation.v1","program_id":PROGRAM_ID,"program_version":PROGRAM_VERSION,"status":"CLOSED_FIRST_RESULT_PRESERVED","program_protocol_hash":protocol_hash(config),"program_scientific_hash":program_scientific_hash,"parent_moldisc016_hash":PARENT_MOLDISC016_HASH,"parent_moldisc015_hash":PARENT_MOLDISC015_HASH,"r0_import":{"source_artifact":r0.get("source_artifact"),"no_rerun":True,"imported_record_count":len(r0["records"]),"parent_validation_sha256":r0["parent_validation_hash"]},"source_audit":source,"redocking":redock,"docking_runs":{"planned":36,"executed":executed,"skipped":36-executed,"nonpass":nonpass},"factorials":factorials,"mutation_shifts":shifts,"strict_mcs":geometry["strict_mcs"],"geometry":geometry,"contacts":contacts,"claims":synthesis["claim_status"],"knowledge_gain":knowledge,"generation_executed":False,"candidate_selection_executed":False,"lead_selection_executed":False,"source_measurement_transfer_allowed":False,"negative_results":{"winner_created":False,"universal_metric_created":False,"experimental_activity_transferred":False,"k57_docking_executed":False},"hashes":campaign_hashes}
    _write_json(root/"moldisc-017-first-run-v1.json",validation)
    return {**manifest,"validation_file":str(root/"moldisc-017-first-run-v1.json")}
