"""MOLDISC-006: frozen non-cognate holo docking of the selected N-H analog."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping

from rdkit import Chem
from rdkit.Chem import AllChem

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking.astex20 import FROZEN_PROSPECTIVE_CASES
from research_os.docking.capability import capability_metadata
from research_os.docking import redocking as base
from research_os.docking.schema import DockingRequest, GridBox
from research_os.engines.openbabel import OpenBabelEngine
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
    if config.get("program_id") != PROGRAM_ID or config.get("program_version") != "1.0":
        raise MOLDISC006Error("MOLDISC-006 requires frozen program_id/version 1.0")
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
    native_reference_sha256: str,
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
    openbabel_version: str | None,
) -> dict[str, Any]:
    return {
        "program_id": PROGRAM_ID,
        "config_hash": config_hash,
        "candidate": dict(candidate_identity),
        "source": {
            "pdb_id": "1P2Y",
            "native_ligand": "NCT",
            "source_pdb_sha256": source_pdb_sha256,
            "native_reference_sha256": native_reference_sha256,
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
            "openbabel_version": openbabel_version,
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
    obabel: OpenBabelEngine | None = None,
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
    if native.GetNumHeavyAtoms() != extraction.ligand_heavy_atoms:
        raise MOLDISC006Error("1P2Y NCT reference/PDB heavy-atom identity mismatch")
    grid = base.derive_redocking_grid(native)
    if grid.status != "PASS":
        raise MOLDISC006Error(f"frozen native-ligand grid is not executable: {grid.reason}")

    starting_sdf = root / "nh_starting_conformer.sdf"
    starting_conformer = _write_starting_conformer(starting_sdf)

    openbabel = obabel or OpenBabelEngine()
    vina_engine = vina or VinaEngine()
    if not openbabel.available:
        raise MOLDISC006Error("Open Babel is unavailable")
    if not vina_engine.available:
        raise MOLDISC006Error("AutoDock Vina is unavailable")
    if not vina_engine.version or "1.2.7" not in vina_engine.version:
        raise MOLDISC006Error(f"Vina version drifted from 1.2.7: {vina_engine.version!r}")

    receptor_pdbqt = root / "receptor.pdbqt"
    ligand_pdbqt = root / "nh_ligand.pdbqt"
    receptor_prep = openbabel.convert(
        receptor_pdb,
        receptor_pdbqt,
        options=("-h", "--partialcharge", "gasteiger", "-xr"),
        timeout=timeout,
        protocol_id="moldisc006.1p2y.receptor-openbabel.v1",
    )
    ligand_prep = openbabel.convert(
        starting_sdf,
        ligand_pdbqt,
        options=("-h", "--partialcharge", "gasteiger"),
        timeout=timeout,
        protocol_id="moldisc006.nh.ligand-openbabel.v1",
    )
    if receptor_prep.returncode != 0 or not receptor_pdbqt.is_file():
        raise MOLDISC006Error(f"1P2Y receptor preparation failed: {receptor_prep.stderr}")
    if ligand_prep.returncode != 0 or not ligand_pdbqt.is_file():
        raise MOLDISC006Error(f"N-H ligand preparation failed: {ligand_prep.stderr}")

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
        protocol_id="research-os.moldisc-006.1p2y-nh-crossdock.v1",
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
        native_reference_sha256=native_reference_sha256,
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
        openbabel_version=openbabel.version,
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
            "openbabel_version": openbabel.version,
            "seed": base.VINA_SEED,
            "cpu": base.VINA_CPU,
            "exhaustiveness": base.VINA_EXHAUSTIVENESS,
            "num_modes": base.VINA_NUM_MODES,
            "pose_scores_kcal_mol": [float(score) for score in scores],
            "rmsd_to_native_nct": "NOT_APPLICABLE_DIFFERENT_LIGAND_GRAPH",
        },
        preparation={
            "starting_conformer": starting_conformer,
            "receptor": asdict(receptor_prep),
            "ligand": asdict(ligand_prep),
        },
        program_scientific_hash=program_hash,
    )

    (root / "program_manifest.json").write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
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
