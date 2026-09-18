"""MOLDISC-006: frozen non-cognate holo docking of the selected N-H analog."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping

from rdkit import Chem
from rdkit.Chem import AllChem

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking.astex20 import FROZEN_PROSPECTIVE_CASES
from research_os.docking.capability import capability_metadata
from research_os.docking import redocking as base
from research_os.docking.schema import DockingRequest, GridBox
from research_os.engines.vina import VinaEngine


PROGRAM_ID = "MOLDISC-006"
CANDIDATE_ID = "MOLDISC-005-NCT-84632F8200"
CANDIDATE_SMILES = "c1cncc(C2CCCN2)c1"
TARGET_CASE_ID = "ATX-014"
DOCKING_CONTEXT = "NON_COGNATE_HOLO_CROSSDOCKING"


class MOLDISC006Error(RuntimeError):
    """Fail-closed error for frozen non-cognate docking identity or execution drift."""


@dataclass(frozen=True)
class MOLDISC006Result:
    program_id: str
    config_hash: str
    candidate_id: str
    candidate_smiles: str
    candidate_inchikey: str
    technical_status: str
    pose_count: int
    vina_pose_1_score_kcal_mol: float | None
    best_affinity_kcal_mol: float | None
    source_pdb_sha256: str
    native_reference_sha256: str
    native_reference_structure_hash: str
    receptor_extracted_sha256: str
    receptor_holo_metadata: Mapping[str, Any]
    starting_conformer_sha256: str
    receptor_pdbqt_sha256: str
    ligand_pdbqt_sha256: str
    vina_output_sha256: str
    grid: Mapping[str, Any]
    capability: Mapping[str, Any]
    engine: Mapping[str, Any]
    preparation: Mapping[str, Any]
    program_scientific_hash: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["grid"] = dict(self.grid)
        value["receptor_holo_metadata"] = dict(self.receptor_holo_metadata)
        value["capability"] = dict(self.capability)
        value["engine"] = dict(self.engine)
        value["preparation"] = dict(self.preparation)
        return value


def load_program_config_v6(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("program_id") != PROGRAM_ID or config.get("program_version") != "1.2":
        raise MOLDISC006Error("MOLDISC-006 requires corrected frozen program_id/version 1.2")
    parent = config.get("parent_program") or {}
    if (
        parent.get("program_id") != "MOLDISC-005"
        or parent.get("program_scientific_hash")
        != "88e28697f8ce5ae14d0737089130c469275d28950c63e90053bc6fe6012dcac7"
        or parent.get("selected_candidate_id") != CANDIDATE_ID
        or parent.get("selected_variant_id") != "N-H"
    ):
        raise MOLDISC006Error("MOLDISC-006 parent selection identity drifted")
    candidate = config.get("candidate") or {}
    if candidate.get("candidate_id") != CANDIDATE_ID or candidate.get("canonical_smiles") != CANDIDATE_SMILES:
        raise MOLDISC006Error("MOLDISC-006 candidate identity drifted")
    target = config.get("target") or {}
    if (
        target.get("case_id") != TARGET_CASE_ID
        or target.get("pdb_id") != "1P2Y"
        or target.get("native_chem_comp_id") != "NCT"
        or tuple(target.get("receptor_author_chains") or ()) != ("A",)
    ):
        raise MOLDISC006Error("MOLDISC-006 1P2Y/NCT target identity drifted")
    docking = config.get("docking") or {}
    expected = {
        "docking_context": DOCKING_CONTEXT,
        "capability_classification": "PARTIALLY_VALIDATED",
        "vina_version_required": "1.2.7",
        "seed": base.VINA_SEED,
        "cpu": base.VINA_CPU,
        "exhaustiveness": base.VINA_EXHAUSTIVENESS,
        "num_modes": base.VINA_NUM_MODES,
    }
    for key, value in expected.items():
        if docking.get(key) != value:
            raise MOLDISC006Error(f"MOLDISC-006 frozen docking field {key!r} drifted")
    receptor_prep = docking.get("receptor_preparation") or {}
    if receptor_prep.get("selected_author_chains") != ["A"]:
        raise MOLDISC006Error("MOLDISC-006 receptor chain selection drifted")
    if receptor_prep.get("retained_cofactors") != ["HEM"]:
        raise MOLDISC006Error("MOLDISC-006 must retain the crystallographic HEM cofactor")
    if receptor_prep.get("engine") != "Meeko" or receptor_prep.get("engine_version_required") != "0.8.0":
        raise MOLDISC006Error("MOLDISC-006 v1.2 requires Meeko 0.8.0 receptor preparation")
    templates = receptor_prep.get("additional_residue_templates") or []
    if len(templates) != 1 or templates[0].get("resname") != "HEM":
        raise MOLDISC006Error("MOLDISC-006 v1.2 requires exactly one explicit HEM residue template")
    if templates[0].get("url") != "https://files.rcsb.org/ligands/download/HEM_ideal.sdf":
        raise MOLDISC006Error("MOLDISC-006 HEM template source drifted")
    ligand_prep = docking.get("ligand_preparation") or {}
    if ligand_prep.get("engine") != "Meeko" or ligand_prep.get("engine_version_required") != "0.8.0":
        raise MOLDISC006Error("MOLDISC-006 v1.2 requires Meeko 0.8.0 ligand preparation")
    primary = config.get("primary_endpoint") or {}
    if primary.get("rmsd_to_native_nct") != "NOT_APPLICABLE_DIFFERENT_LIGAND_GRAPH":
        raise MOLDISC006Error("MOLDISC-006 must not define an NCT RMSD endpoint for N-H")
    return config


def _target_case() -> base.RedockingCase:
    matches = [case for case in FROZEN_PROSPECTIVE_CASES if case.case_id == TARGET_CASE_ID]
    if len(matches) != 1:
        raise MOLDISC006Error("frozen REDOCK-003 ATX-014 case identity is unavailable")
    case = matches[0]
    if (
        case.pdb_id != "1P2Y"
        or case.ligand_id != "NCT"
        or case.ligand_author_chain != "A"
        or tuple(case.receptor_author_chains) != ("A",)
    ):
        raise MOLDISC006Error("frozen ATX-014 case content drifted")
    return case


def _extract_holo_receptor_with_heme(pdb_text: str) -> tuple[str, dict[str, Any]]:
    lines: list[str] = []
    protein_atoms = 0
    heme_atoms = 0
    heme_iron_atoms = 0
    for line in pdb_text.splitlines():
        if len(line) < 27 or not base._primary_altloc(line):
            continue
        record = line[:6].strip()
        chain = line[21].strip()
        if chain != "A":
            continue
        if record == "ATOM":
            lines.append(line)
            protein_atoms += 1
            continue
        if record == "HETATM" and line[17:20].strip() == "HEM":
            lines.append(line)
            heme_atoms += 1
            if base._element_from_pdb_line(line) == "FE":
                heme_iron_atoms += 1
    if protein_atoms < 1:
        raise MOLDISC006Error("1P2Y receptor chain A contains no protein ATOM records")
    if heme_atoms < 1 or heme_iron_atoms != 1:
        raise MOLDISC006Error(
            f"1P2Y holo receptor HEM identity is incomplete: heme_atoms={heme_atoms}, iron_atoms={heme_iron_atoms}"
        )
    return "\n".join(lines + ["TER", "END"]) + "\n", {
        "protein_atom_count": protein_atoms,
        "heme_atom_count": heme_atoms,
        "heme_iron_atom_count": heme_iron_atoms,
        "retained_cofactors": ["HEM"],
        "removed_hetero_components": "all HETATM except HEM",
    }


def _native_reference_structure_identity(molecule: Chem.Mol) -> dict[str, Any]:
    if molecule.GetNumConformers() != 1:
        raise MOLDISC006Error("NCT reference requires exactly one conformer")
    heavy = Chem.RemoveHs(Chem.Mol(molecule), sanitize=True)
    canonical = Chem.MolToSmiles(heavy, canonical=True, isomericSmiles=True)
    conf = molecule.GetConformer()
    coordinates = []
    elements = []
    for atom in molecule.GetAtoms():
        if atom.GetAtomicNum() == 1:
            continue
        point = conf.GetAtomPosition(atom.GetIdx())
        elements.append(atom.GetSymbol())
        coordinates.append([round(float(point.x), 6), round(float(point.y), 6), round(float(point.z), 6)])
    payload = {
        "canonical_smiles": canonical,
        "heavy_atom_count": len(elements),
        "elements_in_sdf_order": elements,
        "heavy_atom_coordinates_angstrom": coordinates,
    }
    return {**payload, "structure_hash": sha256_json(payload)}


def _meeko_version() -> str:
    try:
        import meeko
    except ImportError as exc:
        raise MOLDISC006Error("Meeko 0.8.0 is required for MOLDISC-006 v1.1") from exc
    version = str(getattr(meeko, "__version__", "unknown"))
    if version != "0.8.0":
        raise MOLDISC006Error(f"Meeko version drifted from 0.8.0: {version!r}")
    return version


def _find_cli(*names: str) -> str:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    raise MOLDISC006Error(f"required executable is unavailable: {', '.join(names)}")


def _run_cli(command: list[str], *, timeout: float) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _pdbqt_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise MOLDISC006Error(f"prepared PDBQT is missing or empty: {path}")
    atom_lines = [
        line for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.startswith(("ATOM", "HETATM"))
    ]
    if not atom_lines:
        raise MOLDISC006Error(f"prepared PDBQT contains no receptor/ligand atom records: {path}")
    heme_lines = [line for line in atom_lines if len(line) >= 20 and line[17:20].strip() == "HEM"]
    iron_lines = [
        line for line in heme_lines
        if line[12:16].strip().upper() == "FE" or line.rstrip().split()[-1].upper() == "FE"
    ]
    return {
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "atom_record_count": len(atom_lines),
        "heme_atom_record_count": len(heme_lines),
        "heme_iron_record_count": len(iron_lines),
    }


def _prepare_with_meeko(
    *,
    receptor_pdb: Path,
    ligand_sdf: Path,
    receptor_pdbqt: Path,
    ligand_pdbqt: Path,
    heme_template_sdf: Path,
    timeout: float,
) -> dict[str, Any]:
    version = _meeko_version()
    receptor_cli = _find_cli("mk_prepare_receptor.py", "mk_prepare_receptor")
    ligand_cli = _find_cli("mk_prepare_ligand.py", "mk_prepare_ligand")

    receptor_run = _run_cli(
        [
            receptor_cli,
            "--read_pdb",
            str(receptor_pdb),
            "--write_pdbqt",
            str(receptor_pdbqt),
            "--add_templates",
            f"HEM:{heme_template_sdf}",
        ],
        timeout=timeout,
    )
    if receptor_run["returncode"] != 0:
        raise MOLDISC006Error(
            "Meeko receptor preparation failed: "
            + str(receptor_run["stderr"])[-4000:]
        )
    receptor_meta = _pdbqt_metadata(receptor_pdbqt)
    if receptor_meta["heme_atom_record_count"] < 1 or receptor_meta["heme_iron_record_count"] != 1:
        raise MOLDISC006Error(
            "Meeko receptor PDBQT did not preserve exactly one HEM iron center"
        )

    ligand_run = _run_cli(
        [ligand_cli, "-i", str(ligand_sdf), "-o", str(ligand_pdbqt)],
        timeout=timeout,
    )
    if ligand_run["returncode"] != 0:
        raise MOLDISC006Error(
            "Meeko ligand preparation failed: "
            + str(ligand_run["stderr"])[-4000:]
        )
    ligand_meta = _pdbqt_metadata(ligand_pdbqt)

    return {
        "engine": "Meeko",
        "engine_version": version,
        "heme_template": {
            "path": str(heme_template_sdf),
            "sha256": sha256_file(heme_template_sdf),
        },
        "receptor": {**receptor_run, **receptor_meta},
        "ligand": {**ligand_run, **ligand_meta},
    }


def _candidate_identity() -> tuple[Chem.Mol, str, str]:
    from rdkit.Chem import inchi

    molecule = Chem.MolFromSmiles(CANDIDATE_SMILES)
    if molecule is None:
        raise MOLDISC006Error("selected N-H canonical SMILES is no longer parseable")
    canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    if canonical != CANDIDATE_SMILES:
        raise MOLDISC006Error(
            f"selected N-H canonical identity drifted: expected {CANDIDATE_SMILES!r}, got {canonical!r}"
        )
    return molecule, canonical, inchi.MolToInchiKey(molecule)


def _write_starting_conformer(output_path: Path) -> dict[str, Any]:
    molecule, canonical, inchikey = _candidate_identity()
    prepared = Chem.AddHs(Chem.Mol(molecule))
    prepared.RemoveAllConformers()
    params = AllChem.ETKDGv3()
    params.randomSeed = base.VINA_SEED
    status = AllChem.EmbedMolecule(prepared, params)
    if status != 0:
        raise MOLDISC006Error("RDKit ETKDGv3 failed for frozen N-H candidate")
    uff_optimized = False
    if AllChem.UFFHasAllMoleculeParams(prepared):
        AllChem.UFFOptimizeMolecule(prepared, maxIters=1000)
        uff_optimized = True
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = Chem.SDWriter(str(output_path))
    writer.write(prepared)
    writer.close()
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise MOLDISC006Error("N-H starting conformer SDF was not produced")
    return {
        "canonical_smiles": canonical,
        "inchikey": inchikey,
        "sha256": sha256_file(output_path),
        "random_seed": base.VINA_SEED,
        "uff_optimized": uff_optimized,
        "heavy_atoms": prepared.GetNumHeavyAtoms(),
    }


def _scientific_payload(
    *,
    config_hash: str,
    candidate_identity: Mapping[str, Any],
    source_pdb_sha256: str,
    native_reference_structure_hash: str,
    heme_template_sha256: str,
    receptor_extracted_sha256: str,
    receptor_holo_metadata: Mapping[str, Any],
    grid: Mapping[str, Any],
    starting_conformer: Mapping[str, Any],
    receptor_pdbqt_sha256: str,
    ligand_pdbqt_sha256: str,
    vina_output_sha256: str,
    pose_scores: list[float],
    capability: Mapping[str, Any],
    vina_version: str | None,
    meeko_version: str,
) -> dict[str, Any]:
    return {
        "program_id": PROGRAM_ID,
        "config_hash": config_hash,
        "candidate": dict(candidate_identity),
        "source": {
            "pdb_id": "1P2Y",
            "native_ligand": "NCT",
            "source_pdb_sha256": source_pdb_sha256,
            "native_reference_structure_hash": native_reference_structure_hash,
            "heme_template_sha256": heme_template_sha256,
            "receptor_extracted_sha256": receptor_extracted_sha256,
            "receptor_holo_metadata": dict(receptor_holo_metadata),
        },
        "grid": dict(grid),
        "starting_conformer": dict(starting_conformer),
        "prepared_inputs": {
            "receptor_pdbqt_sha256": receptor_pdbqt_sha256,
            "ligand_pdbqt_sha256": ligand_pdbqt_sha256,
        },
        "docking": {
            "context": DOCKING_CONTEXT,
            "vina_version": vina_version,
            "meeko_version": meeko_version,
            "seed": base.VINA_SEED,
            "cpu": base.VINA_CPU,
            "exhaustiveness": base.VINA_EXHAUSTIVENESS,
            "num_modes": base.VINA_NUM_MODES,
            "vina_output_sha256": vina_output_sha256,
            "pose_scores_kcal_mol": pose_scores,
            "capability": dict(capability),
            "rmsd_to_native_nct": "NOT_APPLICABLE_DIFFERENT_LIGAND_GRAPH",
        },
    }


def run_moldisc_006(
    *,
    config_path: str | Path,
    output_root: str | Path,
    vina: VinaEngine | None = None,
    timeout: float = 120.0,
) -> MOLDISC006Result:
    config = load_program_config_v6(config_path)
    config_hash = sha256_json(config)
    case = _target_case()
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=False)

    source_pdb = root / "1P2Y.pdb"
    source_pdb_sha256 = base._download(
        f"https://files.rcsb.org/download/{case.pdb_id}.pdb",
        source_pdb,
        timeout=timeout,
    )
    pdb_text = source_pdb.read_text(encoding="utf-8", errors="replace")
    extraction = base.extract_case_from_pdb(pdb_text, case)
    holo_receptor_text, receptor_holo_metadata = _extract_holo_receptor_with_heme(pdb_text)

    receptor_pdb = root / "receptor_extracted.pdb"
    receptor_pdb.write_text(holo_receptor_text, encoding="utf-8")
    receptor_extracted_sha256 = sha256_file(receptor_pdb)

    native_reference = root / "nct_native_reference.sdf"
    native_reference_sha256 = base._download(
        base._instance_sdf_url(case, extraction.ligand_auth_seq_id),
        native_reference,
        timeout=timeout,
    )
    native = base.load_single_sdf(native_reference)
    native_reference_structure = _native_reference_structure_identity(native)
    if native.GetNumHeavyAtoms() != extraction.ligand_heavy_atoms:
        raise MOLDISC006Error("1P2Y NCT reference/PDB heavy-atom identity mismatch")
    grid = base.derive_redocking_grid(native)
    if grid.status != "PASS":
        raise MOLDISC006Error(f"frozen native-ligand grid is not executable: {grid.reason}")

    heme_template_sdf = root / "HEM_ideal.sdf"
    heme_template_sha256 = base._download(
        "https://files.rcsb.org/ligands/download/HEM_ideal.sdf",
        heme_template_sdf,
        timeout=timeout,
    )
    heme_template_mol = Chem.SDMolSupplier(str(heme_template_sdf), removeHs=False)[0]
    if heme_template_mol is None:
        raise MOLDISC006Error("official RCSB HEM ideal SDF is not parseable by RDKit")
    if not any(atom.GetSymbol().upper() == "FE" for atom in heme_template_mol.GetAtoms()):
        raise MOLDISC006Error("official RCSB HEM ideal SDF contains no Fe atom")

    starting_sdf = root / "nh_starting_conformer.sdf"
    starting_conformer = _write_starting_conformer(starting_sdf)

    vina_engine = vina or VinaEngine()
    if not vina_engine.available:
        raise MOLDISC006Error("AutoDock Vina is unavailable")
    if not vina_engine.version or "1.2.7" not in vina_engine.version:
        raise MOLDISC006Error(f"Vina version drifted from 1.2.7: {vina_engine.version!r}")

    receptor_pdbqt = root / "receptor.pdbqt"
    ligand_pdbqt = root / "nh_ligand.pdbqt"
    preparation = _prepare_with_meeko(
        receptor_pdb=receptor_pdb,
        ligand_sdf=starting_sdf,
        receptor_pdbqt=receptor_pdbqt,
        ligand_pdbqt=ligand_pdbqt,
        heme_template_sdf=heme_template_sdf,
        timeout=timeout,
    )

    vina_output = root / "nh_vina_poses.pdbqt"
    request = DockingRequest(
        receptor_path=str(receptor_pdbqt),
        ligand_path=str(ligand_pdbqt),
        grid=GridBox(
            grid.center_x,
            grid.center_y,
            grid.center_z,
            grid.size_x,
            grid.size_y,
            grid.size_z,
        ),
        exhaustiveness=base.VINA_EXHAUSTIVENESS,
        cpu=base.VINA_CPU,
        seed=base.VINA_SEED,
        output_path=str(vina_output),
        target_id="1P2Y:CYP101A1:NCT-known-pocket:N-H",
        species="Pseudomonas putida",
        role="NON_COGNATE_HOLO_CROSSDOCKING",
        protocol_id="research-os.moldisc-006.1p2y-nh-crossdock.v1.2",
        timeout=900.0,
        num_modes=base.VINA_NUM_MODES,
    )
    docking = vina_engine.run(request)
    if docking.returncode != 0 or not vina_output.is_file():
        raise MOLDISC006Error(f"Vina execution failed: {docking.stderr}")

    pdbqt_text = vina_output.read_text(encoding="utf-8", errors="replace")
    models = base.split_vina_pdbqt_models(pdbqt_text)
    scores = base.parse_vina_pose_scores(pdbqt_text)
    if not models or not scores:
        raise MOLDISC006Error("Vina completed but produced no parseable scored poses")
    if len(scores) > len(models):
        raise MOLDISC006Error("Vina score/model count is inconsistent")
    if any(not math.isfinite(float(score)) for score in scores):
        raise MOLDISC006Error("Vina emitted a non-finite pose score")
    if all(abs(float(score)) < 1e-12 for score in scores):
        raise MOLDISC006Error("Vina emitted only zero-valued scores; refusing invalid docking evidence")

    capability = capability_metadata(DOCKING_CONTEXT)
    if capability["capability_status"] != "PARTIALLY_VALIDATED":
        raise MOLDISC006Error("non-cognate holo docking capability classification drifted")
    if capability["evidence_level"] != "E2_COMPUTATIONAL":
        raise MOLDISC006Error("non-cognate holo docking evidence level drifted")

    candidate_identity = {
        "candidate_id": CANDIDATE_ID,
        "canonical_smiles": starting_conformer["canonical_smiles"],
        "inchikey": starting_conformer["inchikey"],
        "generation_evidence_level": "E0_HEURISTIC",
        "parent_program": "MOLDISC-005",
    }
    receptor_pdbqt_sha256 = sha256_file(receptor_pdbqt)
    ligand_pdbqt_sha256 = sha256_file(ligand_pdbqt)
    vina_output_sha256 = sha256_file(vina_output)
    grid_payload = grid.to_dict()
    scientific = _scientific_payload(
        config_hash=config_hash,
        candidate_identity=candidate_identity,
        source_pdb_sha256=source_pdb_sha256,
        native_reference_structure_hash=str(native_reference_structure["structure_hash"]),
        heme_template_sha256=heme_template_sha256,
        receptor_extracted_sha256=receptor_extracted_sha256,
        receptor_holo_metadata=receptor_holo_metadata,
        grid=grid_payload,
        starting_conformer=starting_conformer,
        receptor_pdbqt_sha256=receptor_pdbqt_sha256,
        ligand_pdbqt_sha256=ligand_pdbqt_sha256,
        vina_output_sha256=vina_output_sha256,
        pose_scores=[float(score) for score in scores],
        capability=capability,
        vina_version=vina_engine.version,
        meeko_version=str(preparation["engine_version"]),
    )
    program_hash = sha256_json(scientific)
    result = MOLDISC006Result(
        program_id=PROGRAM_ID,
        config_hash=config_hash,
        candidate_id=CANDIDATE_ID,
        candidate_smiles=CANDIDATE_SMILES,
        candidate_inchikey=str(starting_conformer["inchikey"]),
        technical_status="PASS",
        pose_count=len(models),
        vina_pose_1_score_kcal_mol=float(scores[0]),
        best_affinity_kcal_mol=float(docking.best_affinity_kcal_mol) if docking.best_affinity_kcal_mol is not None else min(float(score) for score in scores),
        source_pdb_sha256=source_pdb_sha256,
        native_reference_sha256=native_reference_sha256,
        native_reference_structure_hash=str(native_reference_structure["structure_hash"]),
        receptor_extracted_sha256=receptor_extracted_sha256,
        receptor_holo_metadata=receptor_holo_metadata,
        starting_conformer_sha256=str(starting_conformer["sha256"]),
        receptor_pdbqt_sha256=receptor_pdbqt_sha256,
        ligand_pdbqt_sha256=ligand_pdbqt_sha256,
        vina_output_sha256=vina_output_sha256,
        grid=grid_payload,
        capability=capability,
        engine={
            "vina_version": vina_engine.version,
            "meeko_version": preparation["engine_version"],
            "seed": base.VINA_SEED,
            "cpu": base.VINA_CPU,
            "exhaustiveness": base.VINA_EXHAUSTIVENESS,
            "num_modes": base.VINA_NUM_MODES,
            "pose_scores_kcal_mol": [float(score) for score in scores],
            "rmsd_to_native_nct": "NOT_APPLICABLE_DIFFERENT_LIGAND_GRAPH",
        },
        preparation={
            "starting_conformer": starting_conformer,
            **preparation,
            "native_reference_transport_sha256": native_reference_sha256,
            "native_reference_structure": native_reference_structure,
        },
        program_scientific_hash=program_hash,
    )

    (root / "program_manifest.json").write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "transport_provenance.json").write_text(
        json.dumps(
            {
                "source_pdb_sha256": source_pdb_sha256,
                "native_reference_transport_sha256": native_reference_sha256,
                "native_reference_structure_hash": native_reference_structure["structure_hash"],
                "heme_template_transport_sha256": heme_template_sha256,
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "scientific_payload.json").write_text(
        json.dumps(scientific, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "program_report.md").write_text(_markdown(config, result), encoding="utf-8")
    return result


def _markdown(config: Mapping[str, Any], result: MOLDISC006Result) -> str:
    return "\n".join(
        [
            "# MOLDISC-006 — selected N-H non-cognate holo docking",
            "",
            f"- Candidate: {result.candidate_id}",
            f"- Target: PDB {config['target']['pdb_id']} / {config['target']['target']}",
            f"- Context: {DOCKING_CONTEXT}",
            f"- Capability: {result.capability['capability_status']} / {result.capability['evidence_level']}",
            f"- Technical status: {result.technical_status}",
            f"- Returned poses: {result.pose_count}",
            f"- Vina pose-1 score: {result.vina_pose_1_score_kcal_mol} kcal/mol",
            f"- Program scientific hash: {result.program_scientific_hash}",
            "",
            "## Interpretation boundary",
            "",
            "The score is a bounded E2 computational docking output. It is not measured affinity, potency, free energy, efficacy, safety, or experimental structural truth.",
            "",
            "RMSD to native NCT is not defined because N-H and NCT are different molecular graphs.",
            "",
        ]
    )


__all__ = [
    "CANDIDATE_ID",
    "CANDIDATE_SMILES",
    "DOCKING_CONTEXT",
    "MOLDISC006Error",
    "MOLDISC006Result",
    "PROGRAM_ID",
    "load_program_config_v6",
    "run_moldisc_006",
]
