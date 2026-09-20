"""MOLDISC-012: frozen non-cognate docking of STEP2-DEMETHYL-01 in 1KZK."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from rdkit import Chem
from rdkit.Chem import AllChem, inchi

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking import redocking as base
from research_os.docking.astex20 import FROZEN_PROSPECTIVE_CASES
from research_os.docking.capability import capability_metadata, load_profile
from research_os.docking.schema import DockingRequest, GridBox
from research_os.engines.openbabel import OpenBabelEngine
from research_os.engines.vina import VinaEngine


PROGRAM_ID = "MOLDISC-012"
PARENT_MOLDISC011_HASH = "8cb29619a82ca4680424c1b37c9bdce37b83e6cc8d570788435e1e9a62b159ff"
OPERATIONAL_MOLDISC010_HASH = "360ef9eb66981287781a971a7e09aebbe2749be765af5b4c6dcb33e3839eb48b"
CANDIDATE_VARIANT_ID = "STEP2-DEMETHYL-01"
CANDIDATE_ID = "MOLDISC-011-JE2-286E6F2BE8"
CANDIDATE_SMILES = "CC1(C)SCN(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2cccc(O)c2)[C@@H]1C(=O)NCc1ccccc1"
CANDIDATE_INCHIKEY = "DRIAWXDDGSORDT-KKUQBAQOSA-N"
TARGET_CASE_ID = "ATX-007"
DOCKING_CONTEXT = "NON_COGNATE_HOLO_CROSSDOCKING"
RMSD_BOUNDARY = "NOT_APPLICABLE_DIFFERENT_LIGAND_GRAPH"
FROZEN_CAPABILITY_PROFILE_HASH = "b8c5c799b2035bae2796de714cc55dc4e607420e13b309b7f33792ebaf5597bb"
FROZEN_CAPABILITY_PROFILE_ID = "research-os.docking.capability-profile.v1+b8c5c799b2035bae"
FROZEN_CAPABILITY_PROFILE_PATH = Path(__file__).resolve().parents[3] / "configs" / "docking-capability-profile-snapshots" / f"{FROZEN_CAPABILITY_PROFILE_HASH}.json"


class MOLDISC012Error(RuntimeError):
    """Fail-closed error for frozen MOLDISC-012 protocol drift."""


def _load_frozen_capability_profile():
    try:
        profile = load_profile(FROZEN_CAPABILITY_PROFILE_PATH)
    except (OSError, ValueError) as exc:
        raise MOLDISC012Error("historical docking capability profile is unavailable or invalid") from exc
    if profile.profile_hash != FROZEN_CAPABILITY_PROFILE_HASH or profile.profile_id != FROZEN_CAPABILITY_PROFILE_ID:
        raise MOLDISC012Error("historical docking capability profile identity drifted")
    if tuple(profile.context_record(DOCKING_CONTEXT).get("evidence_source_ids", ())) != ("CROSSDOCK-001",):
        raise MOLDISC012Error("historical non-cognate capability evidence sources drifted")
    return profile


@dataclass(frozen=True)
class MOLDISC012Result:
    program_id: str
    config_hash: str
    candidate_variant_id: str
    candidate_id: str
    candidate_smiles: str
    candidate_inchikey: str
    technical_status: str
    pose_count: int
    pose_scores_kcal_mol: tuple[float, ...]
    source_pdb_transport_sha256: str
    native_reference_transport_sha256: str
    native_reference_structure_hash: str
    receptor_extracted_sha256: str
    starting_conformer_sha256: str
    receptor_pdbqt_sha256: str
    ligand_pdbqt_sha256: str
    receptor_scientific_identity: str
    ligand_scientific_identity: str
    vina_output_transport_sha256: str
    vina_output_scientific_hash: str
    grid: Mapping[str, Any]
    target: Mapping[str, Any]
    capability: Mapping[str, Any]
    engines: Mapping[str, Any]
    program_scientific_hash: str

    @property
    def vina_pose_1_score_kcal_mol(self) -> float:
        return self.pose_scores_kcal_mol[0]

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "pose_scores_kcal_mol": list(self.pose_scores_kcal_mol),
            "grid": dict(self.grid),
            "target": dict(self.target),
            "capability": dict(self.capability),
            "engines": dict(self.engines),
            "vina_pose_1_score_kcal_mol": self.vina_pose_1_score_kcal_mol,
            "rmsd_to_native_je2": RMSD_BOUNDARY,
        }


def load_program_config_v12(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("program_id") != PROGRAM_ID or config.get("program_version") != "1.0":
        raise MOLDISC012Error("MOLDISC-012 requires frozen program_id/version 1.0")

    parent = config.get("parent_program") or {}
    if (
        parent.get("program_id") != "MOLDISC-011"
        or parent.get("program_scientific_hash") != PARENT_MOLDISC011_HASH
        or parent.get("selected_variant_id") != CANDIDATE_VARIANT_ID
        or parent.get("selected_candidate_id") != CANDIDATE_ID
        or parent.get("selection_used_esol") is not False
        or parent.get("docking_executed") is not False
    ):
        raise MOLDISC012Error("MOLDISC-012 upstream MOLDISC-011 identity drifted")

    operational = config.get("operational_moldisc010") or {}
    if (
        operational.get("program_scientific_hash") != OPERATIONAL_MOLDISC010_HASH
        or operational.get("technical_status") != "PASS"
        or operational.get("docking_context") != DOCKING_CONTEXT
        or operational.get("capability") != "PARTIALLY_VALIDATED"
        or operational.get("evidence_level") != "E2_COMPUTATIONAL"
        or operational.get("score_used_for_candidate_selection") is not False
        or operational.get("score_used_for_protocol_selection") is not False
        or operational.get("score_used_as_success_threshold") is not False
    ):
        raise MOLDISC012Error("MOLDISC-010 operational evidence boundary drifted")

    candidate = config.get("candidate") or {}
    if (
        candidate.get("variant_id") != CANDIDATE_VARIANT_ID
        or candidate.get("candidate_id") != CANDIDATE_ID
        or candidate.get("canonical_smiles") != CANDIDATE_SMILES
        or candidate.get("inchikey") != CANDIDATE_INCHIKEY
    ):
        raise MOLDISC012Error("MOLDISC-012 candidate identity drifted")

    target = config.get("target") or {}
    if (
        target.get("case_id") != TARGET_CASE_ID
        or target.get("pdb_id") != "1KZK"
        or target.get("native_chem_comp_id") != "JE2"
        or target.get("ligand_author_chain") != "A"
        or tuple(target.get("receptor_author_chains") or ()) != ("A", "B")
    ):
        raise MOLDISC012Error("MOLDISC-012 target identity drifted")

    docking = config.get("docking") or {}
    expected = {
        "docking_context": DOCKING_CONTEXT,
        "capability_classification": "PARTIALLY_VALIDATED",
        "evidence_level": "E2_COMPUTATIONAL",
        "vina_version_required": "1.2.7",
        "seed": base.VINA_SEED,
        "cpu": base.VINA_CPU,
        "exhaustiveness": base.VINA_EXHAUSTIVENESS,
        "num_modes": base.VINA_NUM_MODES,
        "scoring_function": "vina",
    }
    for key, value in expected.items():
        if docking.get(key) != value:
            raise MOLDISC012Error(f"MOLDISC-012 frozen docking field {key!r} drifted")
    if (docking.get("receptor_preparation") or {}).get("engine") != "Open Babel":
        raise MOLDISC012Error("MOLDISC-012 receptor preparation engine drifted")
    if (docking.get("ligand_preparation") or {}).get("engine") != "Open Babel":
        raise MOLDISC012Error("MOLDISC-012 ligand preparation engine drifted")

    endpoint = config.get("primary_endpoint") or {}
    if endpoint.get("scientific_success_threshold") is not None:
        raise MOLDISC012Error("MOLDISC-012 cannot define a favorable-score threshold")
    if endpoint.get("rmsd_to_native_je2") != RMSD_BOUNDARY:
        raise MOLDISC012Error("MOLDISC-012 must not define native-JE2 RMSD")
    return config


def _target_case() -> base.RedockingCase:
    matches = [case for case in FROZEN_PROSPECTIVE_CASES if case.case_id == TARGET_CASE_ID]
    if len(matches) != 1:
        raise MOLDISC012Error("frozen REDOCK-003 ATX-007 case is unavailable")
    case = matches[0]
    if (
        case.pdb_id != "1KZK"
        or case.ligand_id != "JE2"
        or case.ligand_author_chain != "A"
        or tuple(case.receptor_author_chains) != ("A", "B")
    ):
        raise MOLDISC012Error("frozen REDOCK-003 ATX-007 case content drifted")
    return case


def _candidate_identity() -> tuple[Chem.Mol, str, str]:
    molecule = Chem.MolFromSmiles(CANDIDATE_SMILES)
    if molecule is None:
        raise MOLDISC012Error("frozen STEP2-DEMETHYL-01 SMILES is not parseable")
    canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    key = inchi.MolToInchiKey(molecule)
    if canonical != CANDIDATE_SMILES or key != CANDIDATE_INCHIKEY:
        raise MOLDISC012Error("active RDKit candidate identity differs from frozen STEP2-DEMETHYL-01")
    return molecule, canonical, key


def _write_candidate_conformer(path: Path) -> dict[str, Any]:
    molecule, canonical, key = _candidate_identity()
    prepared = Chem.AddHs(Chem.Mol(molecule))
    prepared.RemoveAllConformers()
    params = AllChem.ETKDGv3()
    params.randomSeed = base.VINA_SEED
    if AllChem.EmbedMolecule(prepared, params) != 0:
        raise MOLDISC012Error("RDKit ETKDGv3 failed for STEP2-DEMETHYL-01")
    uff_optimized = False
    if AllChem.UFFHasAllMoleculeParams(prepared):
        AllChem.UFFOptimizeMolecule(prepared, maxIters=1000)
        uff_optimized = True
    writer = Chem.SDWriter(str(path))
    writer.write(prepared)
    writer.close()
    if not path.is_file() or path.stat().st_size <= 0:
        raise MOLDISC012Error("STEP2-DEMETHYL-01 starting conformer was not written")
    return {
        "canonical_smiles": canonical,
        "inchikey": key,
        "sha256": sha256_file(path),
        "heavy_atoms": prepared.GetNumHeavyAtoms(),
        "random_seed": base.VINA_SEED,
        "uff_optimized": uff_optimized,
    }


def _reference_structure_identity(molecule: Chem.Mol) -> dict[str, Any]:
    if molecule.GetNumConformers() != 1:
        raise MOLDISC012Error("JE2 native reference requires exactly one conformer")
    heavy = Chem.RemoveHs(Chem.Mol(molecule), sanitize=True)
    canonical = Chem.MolToSmiles(heavy, canonical=True, isomericSmiles=True)
    conf = molecule.GetConformer()
    atoms = []
    for atom in molecule.GetAtoms():
        if atom.GetAtomicNum() == 1:
            continue
        point = conf.GetAtomPosition(atom.GetIdx())
        atoms.append({"element": atom.GetSymbol(), "x": round(float(point.x), 6), "y": round(float(point.y), 6), "z": round(float(point.z), 6)})
    payload = {"canonical_smiles": canonical, "heavy_atom_count": len(atoms), "atoms_in_sdf_order": atoms}
    return {**payload, "structure_hash": sha256_json(payload)}


def _require_prepared(path: Path, label: str) -> str:
    if not path.is_file() or path.stat().st_size <= 0:
        raise MOLDISC012Error(f"{label} PDBQT is missing or empty")
    text = path.read_text(encoding="utf-8", errors="replace")
    if not any(line.startswith(("ATOM", "HETATM")) for line in text.splitlines()):
        raise MOLDISC012Error(f"{label} PDBQT contains no atom records")
    return sha256_file(path)


def _pdbqt_atoms(text: str, label: str) -> list[dict[str, Any]]:
    atoms: list[dict[str, Any]] = []
    for line in text.splitlines():
        record = line[0:6].strip()
        if record not in {"ATOM", "HETATM"}:
            continue
        if len(line) < 78:
            raise MOLDISC012Error(f"{label} PDBQT contains a truncated atom record")
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
            raise MOLDISC012Error(f"{label} PDBQT contains a malformed atom record") from exc
    if not atoms:
        raise MOLDISC012Error(f"{label} PDBQT contains no atom records")
    return atoms


def _pdbqt_scientific_identity(path: Path, label: str) -> str:
    return sha256_json({"schema": "moldisc-012.pdbqt-scientific-identity.v1", "atoms_in_file_order": _pdbqt_atoms(path.read_text(encoding="utf-8", errors="replace"), label)})


def _vina_scientific_identity(models: Sequence[str], scores: Sequence[float]) -> str:
    if len(models) != len(scores):
        raise MOLDISC012Error("Vina scientific output pose/model count is inconsistent")
    poses = []
    for index, (model, score) in enumerate(zip(models, scores), start=1):
        poses.append({"pose_index": index, "score_kcal_mol": score, "atoms": _pdbqt_atoms(model, f"Vina pose {index}")})
    return sha256_json({"schema": "moldisc-012.vina-scientific-output.v1", "poses_in_order": poses})


def _scientific_payload(
    *,
    config_hash: str,
    candidate_identity: Mapping[str, Any],
    native_reference_structure_hash: str,
    receptor_extracted_sha256: str,
    starting_conformer: Mapping[str, Any],
    receptor_scientific_identity: str,
    ligand_scientific_identity: str,
    vina_output_scientific_hash: str,
    grid: Mapping[str, Any],
    pose_scores: Sequence[float],
    capability: Mapping[str, Any],
    vina_version: str | None,
    openbabel_version: str | None,
) -> dict[str, Any]:
    return {
        "program_id": PROGRAM_ID,
        "config_hash": config_hash,
        "parent": {
            "moldisc011_program_scientific_hash": PARENT_MOLDISC011_HASH,
            "moldisc010_operational_program_scientific_hash": OPERATIONAL_MOLDISC010_HASH,
            "moldisc010_score_used_for_candidate_selection": False,
            "moldisc010_score_used_for_protocol_selection": False,
            "moldisc010_score_used_as_success_threshold": False,
        },
        "candidate": dict(candidate_identity),
        "target": {
            "case_id": TARGET_CASE_ID,
            "pdb_id": "1KZK",
            "native_ligand": "JE2",
            "native_reference_structure_hash": native_reference_structure_hash,
            "receptor_extracted_sha256": receptor_extracted_sha256,
        },
        "starting_conformer": dict(starting_conformer),
        "prepared_inputs": {
            "receptor_scientific_identity": receptor_scientific_identity,
            "ligand_scientific_identity": ligand_scientific_identity,
        },
        "grid": dict(grid),
        "docking": {
            "context": DOCKING_CONTEXT,
            "vina_version": vina_version,
            "openbabel_version": openbabel_version,
            "seed": base.VINA_SEED,
            "cpu": base.VINA_CPU,
            "exhaustiveness": base.VINA_EXHAUSTIVENESS,
            "num_modes": base.VINA_NUM_MODES,
            "pose_scores_kcal_mol": list(pose_scores),
            "vina_output_scientific_hash": vina_output_scientific_hash,
            "rmsd_to_native_je2": RMSD_BOUNDARY,
            "capability": dict(capability),
            "endpoint": "TECHNICAL_COMPLETION_ONLY",
        },
    }


def run_moldisc_012(
    *,
    config_path: str | Path,
    output_root: str | Path,
    vina: VinaEngine | None = None,
    obabel: OpenBabelEngine | None = None,
    timeout: float = 120.0,
) -> MOLDISC012Result:
    frozen_profile = _load_frozen_capability_profile()
    config = load_program_config_v12(config_path)
    config_hash = sha256_json(config)
    case = _target_case()
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=False)

    source_pdb = root / "1KZK.pdb"
    source_pdb_sha256 = base._download(f"https://files.rcsb.org/download/{case.pdb_id}.pdb", source_pdb, timeout=timeout)
    extraction = base.extract_case_from_pdb(source_pdb.read_text(encoding="utf-8", errors="replace"), case)
    receptor_pdb = root / "receptor_extracted.pdb"
    receptor_pdb.write_text(extraction.receptor_pdb, encoding="utf-8")
    receptor_extracted_sha256 = sha256_file(receptor_pdb)

    native_reference = root / "je2_native_reference.sdf"
    native_reference_transport_sha256 = base._download(base._instance_sdf_url(case, extraction.ligand_auth_seq_id), native_reference, timeout=timeout)
    native = base.load_single_sdf(native_reference)
    if native.GetNumHeavyAtoms() != extraction.ligand_heavy_atoms:
        raise MOLDISC012Error("1KZK JE2 reference/PDB heavy-atom identity mismatch")
    reference_identity = _reference_structure_identity(native)
    grid = base.derive_redocking_grid(native)
    if grid.status != "PASS":
        raise MOLDISC012Error(f"frozen JE2-derived grid is not executable: {grid.reason}")

    starting_sdf = root / "step2_demethyl01_starting.sdf"
    starting_conformer = _write_candidate_conformer(starting_sdf)
    openbabel = obabel or OpenBabelEngine()
    vina_engine = vina or VinaEngine()
    if not openbabel.available:
        raise MOLDISC012Error("Open Babel is unavailable")
    if not vina_engine.available:
        raise MOLDISC012Error("AutoDock Vina is unavailable")
    if not vina_engine.version or "1.2.7" not in vina_engine.version:
        raise MOLDISC012Error(f"Vina version drifted from 1.2.7: {vina_engine.version!r}")

    receptor_pdbqt = root / "receptor.pdbqt"
    ligand_pdbqt = root / "step2_demethyl01_ligand.pdbqt"
    receptor_prep = openbabel.convert(receptor_pdb, receptor_pdbqt, options=("-h", "--partialcharge", "gasteiger", "-xr"), timeout=timeout, protocol_id="moldisc012.receptor-openbabel.v1")
    ligand_prep = openbabel.convert(starting_sdf, ligand_pdbqt, options=("-h", "--partialcharge", "gasteiger"), timeout=timeout, protocol_id="moldisc012.ligand-openbabel.v1")
    if receptor_prep.returncode != 0:
        raise MOLDISC012Error(f"Open Babel receptor preparation failed: {receptor_prep.stderr}")
    if ligand_prep.returncode != 0:
        raise MOLDISC012Error(f"Open Babel ligand preparation failed: {ligand_prep.stderr}")
    receptor_pdbqt_sha256 = _require_prepared(receptor_pdbqt, "receptor")
    ligand_pdbqt_sha256 = _require_prepared(ligand_pdbqt, "ligand")
    receptor_scientific_identity = _pdbqt_scientific_identity(receptor_pdbqt, "receptor")
    ligand_scientific_identity = _pdbqt_scientific_identity(ligand_pdbqt, "ligand")

    vina_output = root / "step2_demethyl01_vina_poses.pdbqt"
    request = DockingRequest(
        receptor_path=str(receptor_pdbqt),
        ligand_path=str(ligand_pdbqt),
        grid=GridBox(grid.center_x, grid.center_y, grid.center_z, grid.size_x, grid.size_y, grid.size_z),
        exhaustiveness=base.VINA_EXHAUSTIVENESS,
        cpu=base.VINA_CPU,
        seed=base.VINA_SEED,
        output_path=str(vina_output),
        target_id="1KZK:JE2-known-pocket:STEP2-DEMETHYL-01",
        role=DOCKING_CONTEXT,
        protocol_id="research-os.moldisc-012.1kzk-step2-demethyl01-crossdock.v1",
        timeout=900.0,
        num_modes=base.VINA_NUM_MODES,
    )
    docking = vina_engine.run(request)
    if docking.returncode != 0 or not vina_output.is_file():
        raise MOLDISC012Error(f"Vina execution failed: {docking.stderr}")
    output_text = vina_output.read_text(encoding="utf-8", errors="replace")
    models = base.split_vina_pdbqt_models(output_text)
    scores = [float(value) for value in base.parse_vina_pose_scores(output_text)]
    if not models or not scores or len(scores) != len(models):
        raise MOLDISC012Error("Vina completed but produced an incomplete scored pose set")
    if any(not math.isfinite(score) for score in scores):
        raise MOLDISC012Error("Vina emitted a non-finite score")
    if all(abs(score) < 1e-12 for score in scores):
        raise MOLDISC012Error("Vina emitted only zero-valued scores; rejecting invalid evidence")
    vina_output_transport_sha256 = sha256_file(vina_output)
    vina_output_scientific_hash = _vina_scientific_identity(models, scores)

    capability = capability_metadata(DOCKING_CONTEXT, profile=frozen_profile)
    if capability["capability_status"] != "PARTIALLY_VALIDATED" or capability["evidence_level"] != "E2_COMPUTATIONAL":
        raise MOLDISC012Error("non-cognate docking capability classification drifted")

    candidate_identity = {
        "variant_id": CANDIDATE_VARIANT_ID,
        "candidate_id": CANDIDATE_ID,
        "canonical_smiles": CANDIDATE_SMILES,
        "inchikey": CANDIDATE_INCHIKEY,
        "generation_evidence_level": "E0_HEURISTIC",
        "parent_program": "MOLDISC-011",
    }
    target_identity = {
        "case_id": TARGET_CASE_ID,
        "pdb_id": "1KZK",
        "native_ligand": "JE2",
        "ligand_author_chain": "A",
        "receptor_author_chains": ["A", "B"],
    }
    scientific = _scientific_payload(
        config_hash=config_hash,
        candidate_identity=candidate_identity,
        native_reference_structure_hash=str(reference_identity["structure_hash"]),
        receptor_extracted_sha256=receptor_extracted_sha256,
        starting_conformer=starting_conformer,
        receptor_scientific_identity=receptor_scientific_identity,
        ligand_scientific_identity=ligand_scientific_identity,
        vina_output_scientific_hash=vina_output_scientific_hash,
        grid=grid.to_dict(),
        pose_scores=scores,
        capability=capability,
        vina_version=vina_engine.version,
        openbabel_version=openbabel.version,
    )
    result = MOLDISC012Result(
        program_id=PROGRAM_ID,
        config_hash=config_hash,
        candidate_variant_id=CANDIDATE_VARIANT_ID,
        candidate_id=CANDIDATE_ID,
        candidate_smiles=CANDIDATE_SMILES,
        candidate_inchikey=CANDIDATE_INCHIKEY,
        technical_status="PASS",
        pose_count=len(models),
        pose_scores_kcal_mol=tuple(scores),
        source_pdb_transport_sha256=source_pdb_sha256,
        native_reference_transport_sha256=native_reference_transport_sha256,
        native_reference_structure_hash=str(reference_identity["structure_hash"]),
        receptor_extracted_sha256=receptor_extracted_sha256,
        starting_conformer_sha256=str(starting_conformer["sha256"]),
        receptor_pdbqt_sha256=receptor_pdbqt_sha256,
        ligand_pdbqt_sha256=ligand_pdbqt_sha256,
        receptor_scientific_identity=receptor_scientific_identity,
        ligand_scientific_identity=ligand_scientific_identity,
        vina_output_transport_sha256=vina_output_transport_sha256,
        vina_output_scientific_hash=vina_output_scientific_hash,
        grid=grid.to_dict(),
        target=target_identity,
        capability=capability,
        engines={"vina_version": vina_engine.version, "openbabel_version": openbabel.version, "seed": base.VINA_SEED, "cpu": base.VINA_CPU, "exhaustiveness": base.VINA_EXHAUSTIVENESS, "num_modes": base.VINA_NUM_MODES},
        program_scientific_hash=sha256_json(scientific),
    )
    (root / "program_manifest.json").write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (root / "scientific_payload.json").write_text(json.dumps(scientific, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (root / "transport_provenance.json").write_text(json.dumps({
        "transport_only": True,
        "source_pdb_transport_sha256": source_pdb_sha256,
        "native_reference_transport_sha256": native_reference_transport_sha256,
        "receptor_pdbqt_sha256": receptor_pdbqt_sha256,
        "ligand_pdbqt_sha256": ligand_pdbqt_sha256,
        "vina_output_transport_sha256": vina_output_transport_sha256,
        "native_reference_structure_hash": reference_identity["structure_hash"],
        "vina_output_scientific_hash": vina_output_scientific_hash,
    }, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (root / "program_report.md").write_text(_markdown(config, result), encoding="utf-8")
    return result


def _markdown(config: Mapping[str, Any], result: MOLDISC012Result) -> str:
    return "\n".join([
        "# MOLDISC-012 — STEP2-DEMETHYL-01 non-cognate docking in 1KZK",
        "",
        f"- candidate: {result.candidate_id}",
        f"- target: {config['target']['case_id']} / PDB {config['target']['pdb_id']}",
        f"- context: {DOCKING_CONTEXT}",
        f"- capability: {result.capability['capability_status']} / {result.capability['evidence_level']}",
        f"- technical status: {result.technical_status}",
        f"- returned poses: {result.pose_count}",
        f"- ordered Vina pose scores: {list(result.pose_scores_kcal_mol)}",
        f"- program scientific hash: {result.program_scientific_hash}",
        "",
        "## Interpretation boundary",
        "",
        "Candidate selection was completed upstream in MOLDISC-011. The MOLDISC-010 score was not used for candidate selection, protocol selection, or success thresholding.",
        "",
        "The endpoint is reproducible technical completion. This is bounded E2 computational docking output, not measured affinity, free energy, potency, efficacy, safety, or experimental structural truth.",
        "",
        f"RMSD to native JE2: {RMSD_BOUNDARY}.",
        "",
    ])


__all__ = [
    "CANDIDATE_ID",
    "CANDIDATE_INCHIKEY",
    "CANDIDATE_SMILES",
    "CANDIDATE_VARIANT_ID",
    "DOCKING_CONTEXT",
    "MOLDISC012Error",
    "MOLDISC012Result",
    "OPERATIONAL_MOLDISC010_HASH",
    "PARENT_MOLDISC011_HASH",
    "PROGRAM_ID",
    "RMSD_BOUNDARY",
    "load_program_config_v12",
    "run_moldisc_012",
]
