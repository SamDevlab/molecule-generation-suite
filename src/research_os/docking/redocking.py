from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import statistics
from typing import Sequence
from urllib.error import URLError
from urllib.request import Request, urlopen

from rdkit import Chem
from rdkit.Chem import AllChem, rdMolAlign

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking.schema import DockingRequest, GridBox
from research_os.engines.openbabel import OpenBabelEngine
from research_os.engines.vina import VinaEngine


PROTOCOL_ID = "research-os.redocking.v1.1"
POSE_SUCCESS_THRESHOLD_ANGSTROM = 2.0
BOX_PADDING_ANGSTROM = 6.0
BOX_MIN_SIDE_ANGSTROM = 20.0
BOX_MAX_SIDE_ANGSTROM = 30.0
VINA_SEED = 42
VINA_CPU = 1
VINA_EXHAUSTIVENESS = 16
VINA_NUM_MODES = 20


@dataclass(frozen=True)
class RedockingCase:
    case_id: str
    pdb_id: str
    ligand_id: str
    ligand_author_chain: str
    receptor_author_chains: tuple[str, ...]
    target: str
    resolution_angstrom: float
    source_url: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


FROZEN_REDOCKING_CASES: tuple[RedockingCase, ...] = (
    RedockingCase("RDK-001", "1STP", "BTN", "A", ("A",), "streptavidin", 2.60, "https://www.rcsb.org/structure/1STP"),
    RedockingCase("RDK-002", "3PTB", "BEN", "A", ("A",), "beta-trypsin", 1.70, "https://www.rcsb.org/structure/3PTB"),
    RedockingCase("RDK-003", "1HVR", "XK2", "A", ("A", "B"), "HIV-1 protease", 1.80, "https://www.rcsb.org/structure/1HVR"),
    RedockingCase("RDK-004", "1M17", "AQ4", "A", ("A",), "EGFR kinase domain", 2.60, "https://www.rcsb.org/structure/1M17"),
    RedockingCase("RDK-005", "1IEP", "STI", "A", ("A",), "c-Abl kinase domain", 2.10, "https://www.rcsb.org/structure/1IEP"),
)


@dataclass(frozen=True)
class RedockingGrid:
    center_x: float
    center_y: float
    center_z: float
    size_x: float
    size_y: float
    size_z: float
    unclamped_size_x: float
    unclamped_size_y: float
    unclamped_size_z: float
    status: str
    reason: str | None = None
    grid_hash: str | None = None

    def __post_init__(self) -> None:
        if self.grid_hash is None:
            object.__setattr__(
                self,
                "grid_hash",
                sha256_json(
                    {
                        "protocol_id": PROTOCOL_ID,
                        "center": [self.center_x, self.center_y, self.center_z],
                        "size": [self.size_x, self.size_y, self.size_z],
                        "unclamped_size": [self.unclamped_size_x, self.unclamped_size_y, self.unclamped_size_z],
                        "status": self.status,
                        "reason": self.reason,
                    }
                ),
            )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PoseRmsdResult:
    status: str
    rmsd_angstrom: float | None
    reference_heavy_atoms: int
    predicted_heavy_atoms: int
    reference_identity: str | None
    predicted_identity: str | None
    reference_sha256: str | None = None
    predicted_sha256: str | None = None
    reason: str | None = None

    @property
    def rmsd_le_2_angstrom(self) -> bool | None:
        if self.rmsd_angstrom is None:
            return None
        return self.rmsd_angstrom <= POSE_SUCCESS_THRESHOLD_ANGSTROM

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["rmsd_le_2_angstrom"] = self.rmsd_le_2_angstrom
        return value


@dataclass(frozen=True)
class RedockingCaseResult:
    case_id: str
    status: str
    pose_1_rmsd_angstrom: float | None
    minimum_rmsd_angstrom: float | None
    pose_count: int
    vina_pose_1_score_kcal_mol: float | None = None
    first_loss: str | None = None

    @property
    def pose_1_success(self) -> bool:
        return bool(
            self.status == "PASS"
            and self.pose_1_rmsd_angstrom is not None
            and self.pose_1_rmsd_angstrom <= POSE_SUCCESS_THRESHOLD_ANGSTROM
        )

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["pose_1_success"] = self.pose_1_success
        return value


@dataclass(frozen=True)
class PdbExtraction:
    receptor_pdb: str
    ligand_pdb: str
    ligand_auth_seq_id: int
    ligand_insertion_code: str
    ligand_heavy_atoms: int
    receptor_atom_count: int


def _heavy_atom_copy(mol: Chem.Mol) -> Chem.Mol:
    """Return a coordinate-preserving molecule with every hydrogen atom removed.

    RDKit ``RemoveHs`` intentionally keeps some unusual/valence-sensitive H atoms.
    PDBQT -> SDF round-tripping can create exactly those cases, so the redocking
    endpoint removes atomic-number-1 nodes explicitly. This is an evaluator
    normalization only; it does not alter docking coordinates or ranks.
    """

    if mol is None:
        raise ValueError("molecule is required")
    try:
        rw = Chem.RWMol(Chem.Mol(mol))
        for index in reversed(range(rw.GetNumAtoms())):
            if rw.GetAtomWithIdx(index).GetAtomicNum() == 1:
                rw.RemoveAtom(index)
        heavy = rw.GetMol()
    except Exception as exc:
        raise ValueError("molecule could not be normalized for RMSD evaluation") from exc
    if heavy.GetNumAtoms() == 0:
        raise ValueError("molecule contains no heavy atoms")
    if heavy.GetNumConformers() != 1:
        raise ValueError("exactly one conformer is required per pose")
    return heavy


def _connectivity_graph(mol: Chem.Mol) -> Chem.Mol:
    """Normalize to an element-labeled heavy-atom connectivity graph.

    Vina PDBQT does not preserve SDF bond orders/protonation annotations. The RMSD
    correspondence therefore uses elemental connectivity, while still requiring an
    exact graph match. Formal charge, aromatic flags, radicals, stereochemistry,
    explicit hydrogen counts and bond orders are deliberately excluded from the
    correspondence identity; atomic elements and adjacency remain mandatory.
    """

    heavy = _heavy_atom_copy(mol)
    rw = Chem.RWMol(heavy)
    for atom in rw.GetAtoms():
        atom.SetIsAromatic(False)
        atom.SetChiralTag(Chem.ChiralType.CHI_UNSPECIFIED)
        atom.SetFormalCharge(0)
        atom.SetNumExplicitHs(0)
        atom.SetNumRadicalElectrons(0)
        atom.SetNoImplicit(True)
    for bond in rw.GetBonds():
        bond.SetIsAromatic(False)
        bond.SetStereo(Chem.BondStereo.STEREONONE)
        bond.SetBondType(Chem.BondType.SINGLE)
    graph = rw.GetMol()
    Chem.RemoveStereochemistry(graph)
    return graph


def symmetry_aware_heavy_atom_rmsd(reference: Chem.Mol, predicted: Chem.Mol) -> PoseRmsdResult:
    """Return connectivity-validated, symmetry-aware heavy-atom pose RMSD.

    Atom-index correspondence is never assumed. Bond-order/aromatic/protonation
    annotations are normalized because PDBQT cannot preserve them faithfully.
    Element-labeled heavy-atom connectivity remains mandatory; coordinate-only
    fallback is forbidden.
    """

    try:
        ref = _connectivity_graph(reference)
        pred = _connectivity_graph(predicted)
        ref_identity = Chem.MolToSmiles(ref, canonical=True, isomericSmiles=False)
        pred_identity = Chem.MolToSmiles(pred, canonical=True, isomericSmiles=False)
    except ValueError as exc:
        return PoseRmsdResult("INDETERMINATE", None, 0, 0, None, None, reason=str(exc))

    if ref.GetNumAtoms() != pred.GetNumAtoms():
        return PoseRmsdResult("INDETERMINATE", None, ref.GetNumAtoms(), pred.GetNumAtoms(), ref_identity, pred_identity, reason="heavy-atom counts differ")
    if ref.GetNumBonds() != pred.GetNumBonds() or ref_identity != pred_identity:
        return PoseRmsdResult("INDETERMINATE", None, ref.GetNumAtoms(), pred.GetNumAtoms(), ref_identity, pred_identity, reason="reference and predicted heavy-atom graphs differ")

    try:
        rmsd = float(rdMolAlign.GetBestRMS(pred, ref))
    except (RuntimeError, ValueError) as exc:
        return PoseRmsdResult("INDETERMINATE", None, ref.GetNumAtoms(), pred.GetNumAtoms(), ref_identity, pred_identity, reason=f"symmetry-aware atom mapping failed: {exc}")
    if not math.isfinite(rmsd):
        return PoseRmsdResult("INDETERMINATE", None, ref.GetNumAtoms(), pred.GetNumAtoms(), ref_identity, pred_identity, reason="RMSD is non-finite")
    return PoseRmsdResult("PASS", rmsd, ref.GetNumAtoms(), pred.GetNumAtoms(), ref_identity, pred_identity)


def derive_redocking_grid(reference: Chem.Mol) -> RedockingGrid:
    heavy = _heavy_atom_copy(reference)
    conf = heavy.GetConformer()
    coords = [conf.GetAtomPosition(index) for index in range(heavy.GetNumAtoms())]
    mins = [min(getattr(point, axis) for point in coords) for axis in ("x", "y", "z")]
    maxs = [max(getattr(point, axis) for point in coords) for axis in ("x", "y", "z")]
    center = [(low + high) / 2.0 for low, high in zip(mins, maxs)]
    spans = [high - low for low, high in zip(mins, maxs)]
    required = [span + 2.0 * BOX_PADDING_ANGSTROM for span in spans]

    if any(side > BOX_MAX_SIDE_ANGSTROM for side in required):
        sizes = [min(max(side, BOX_MIN_SIDE_ANGSTROM), BOX_MAX_SIDE_ANGSTROM) for side in required]
        return RedockingGrid(*center, *sizes, *required, status="OUT_OF_DOMAIN", reason="native-ligand box rule requires a side larger than 30 Å")

    sizes = [max(side, BOX_MIN_SIDE_ANGSTROM) for side in required]
    return RedockingGrid(*center, *sizes, *required, status="PASS")


def _primary_altloc(line: str) -> bool:
    return len(line) <= 16 or line[16] in {" ", "A"}


def _element_from_pdb_line(line: str) -> str:
    element = line[76:78].strip() if len(line) >= 78 else ""
    if element:
        return element.upper()
    atom_name = line[12:16].strip()
    return re.sub(r"[^A-Za-z]", "", atom_name)[:1].upper()


def extract_case_from_pdb(pdb_text: str, case: RedockingCase) -> PdbExtraction:
    receptor_lines: list[str] = []
    ligand_by_residue: dict[tuple[int, str], list[str]] = {}

    for line in pdb_text.splitlines():
        if len(line) < 27 or not _primary_altloc(line):
            continue
        record = line[:6].strip()
        chain = line[21].strip()
        if record == "ATOM" and chain in case.receptor_author_chains:
            receptor_lines.append(line)
            continue
        if record != "HETATM":
            continue
        residue = line[17:20].strip()
        if residue != case.ligand_id or chain != case.ligand_author_chain:
            continue
        try:
            seq = int(line[22:26].strip())
        except ValueError:
            continue
        insertion = line[26].strip()
        ligand_by_residue.setdefault((seq, insertion), []).append(line)

    if not receptor_lines:
        raise ValueError("frozen receptor chain selection contains no ATOM records")
    if len(ligand_by_residue) != 1:
        raise ValueError(f"expected exactly one {case.ligand_id} instance on author chain {case.ligand_author_chain}, found {len(ligand_by_residue)}")

    (seq, insertion), ligand_lines = next(iter(ligand_by_residue.items()))
    heavy = sum(_element_from_pdb_line(line) not in {"H", "D"} for line in ligand_lines)
    if heavy < 1:
        raise ValueError("native ligand instance contains no heavy atoms")
    receptor_pdb = "\n".join(receptor_lines + ["TER", "END"]) + "\n"
    ligand_pdb = "\n".join(ligand_lines + ["END"]) + "\n"
    return PdbExtraction(receptor_pdb, ligand_pdb, seq, insertion, heavy, len(receptor_lines))


def _download(url: str, destination: Path, *, timeout: float = 60.0) -> str:
    request = Request(url, headers={"User-Agent": "Research-OS/5.1 REDOCK-001"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except (OSError, URLError) as exc:
        raise RuntimeError(f"download failed for {url}: {exc}") from exc
    if not payload:
        raise RuntimeError(f"download returned empty content for {url}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _instance_sdf_url(case: RedockingCase, auth_seq_id: int) -> str:
    return f"https://models.rcsb.org/v1/{case.pdb_id.lower()}/ligand?auth_asym_id={case.ligand_author_chain}&auth_seq_id={auth_seq_id}&encoding=sdf"


def load_single_sdf(path: str | Path) -> Chem.Mol:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    supplier = Chem.SDMolSupplier(str(source), removeHs=False, sanitize=True)
    molecules = [mol for mol in supplier if mol is not None]
    if len(molecules) != 1:
        raise ValueError(f"expected exactly one molecule in {source}, found {len(molecules)}")
    if molecules[0].GetNumConformers() != 1:
        raise ValueError("reference SDF must contain exactly one conformer")
    return molecules[0]


def load_pose_sdf(path: str | Path) -> list[Chem.Mol]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    supplier = Chem.SDMolSupplier(str(source), removeHs=False, sanitize=True)
    molecules = [mol for mol in supplier if mol is not None]
    if not molecules:
        raise ValueError(f"no parseable poses in {source}")
    for mol in molecules:
        if mol.GetNumConformers() != 1:
            raise ValueError("each predicted SDF pose must contain exactly one conformer")
    return molecules


def evaluate_pose_files(reference_sdf: str | Path, predicted_sdf: str | Path) -> list[PoseRmsdResult]:
    reference = load_single_sdf(reference_sdf)
    reference_hash = sha256_file(reference_sdf)
    predicted_hash = sha256_file(predicted_sdf)
    results: list[PoseRmsdResult] = []
    for pose in load_pose_sdf(predicted_sdf):
        raw = symmetry_aware_heavy_atom_rmsd(reference, pose)
        results.append(PoseRmsdResult(raw.status, raw.rmsd_angstrom, raw.reference_heavy_atoms, raw.predicted_heavy_atoms, raw.reference_identity, raw.predicted_identity, reference_sha256=reference_hash, predicted_sha256=predicted_hash, reason=raw.reason))
    return results


def generate_independent_conformer(reference: Chem.Mol, output_path: str | Path) -> dict[str, object]:
    base = Chem.RemoveHs(Chem.Mol(reference), sanitize=True)
    start = Chem.AddHs(base)
    start.RemoveAllConformers()
    params = AllChem.ETKDGv3()
    params.randomSeed = VINA_SEED
    status = AllChem.EmbedMolecule(start, params)
    if status != 0:
        raise RuntimeError("RDKit ETKDG failed to generate an independent starting conformer")
    uff_optimized = False
    if AllChem.UFFHasAllMoleculeParams(start):
        AllChem.UFFOptimizeMolecule(start, maxIters=1000)
        uff_optimized = True
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = Chem.SDWriter(str(output))
    writer.write(start)
    writer.close()
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("independent conformer SDF was not produced")
    return {"sha256": sha256_file(output), "uff_optimized": uff_optimized, "random_seed": VINA_SEED, "heavy_atoms": start.GetNumHeavyAtoms()}


def split_vina_pdbqt_models(text: str) -> list[str]:
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


def parse_vina_pose_scores(pdbqt_text: str) -> list[float]:
    scores: list[float] = []
    for line in pdbqt_text.splitlines():
        match = re.match(r"^REMARK\s+VINA\s+RESULT:\s+(-?\d+(?:\.\d+)?)", line)
        if match:
            scores.append(float(match.group(1)))
    return scores


def _case_failure(case: RedockingCase, status: str, first_loss: str, provenance: dict[str, object], *, pose_count: int = 0) -> dict[str, object]:
    result = RedockingCaseResult(case.case_id, status, None, None, pose_count, first_loss=first_loss)
    return {"case": case.to_dict(), "result": result.to_dict(), "provenance": provenance, "poses": []}


def run_redocking_case(case: RedockingCase, workdir: str | Path, *, vina: VinaEngine | None = None, obabel: OpenBabelEngine | None = None) -> dict[str, object]:
    case_dir = Path(workdir) / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    provenance: dict[str, object] = {"protocol_id": PROTOCOL_ID}

    raw_url = f"https://files.rcsb.org/download/{case.pdb_id}.pdb"
    raw_path = case_dir / f"{case.pdb_id}.pdb"
    try:
        provenance["raw_pdb"] = {"url": raw_url, "sha256": _download(raw_url, raw_path)}
        pdb_text = raw_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        provenance["error"] = str(exc)
        return _case_failure(case, "INDETERMINATE", "RCSB_DOWNLOAD_FAILED", provenance)

    try:
        extraction = extract_case_from_pdb(pdb_text, case)
    except Exception as exc:
        provenance["error"] = str(exc)
        return _case_failure(case, "INDETERMINATE", "PDB_EXTRACTION_FAILED", provenance)

    receptor_pdb = case_dir / "receptor_extracted.pdb"
    ligand_pdb = case_dir / "native_ligand_extracted.pdb"
    receptor_pdb.write_text(extraction.receptor_pdb, encoding="utf-8")
    ligand_pdb.write_text(extraction.ligand_pdb, encoding="utf-8")
    provenance["extraction"] = {
        "ligand_auth_seq_id": extraction.ligand_auth_seq_id,
        "ligand_insertion_code": extraction.ligand_insertion_code,
        "ligand_heavy_atoms_from_pdb": extraction.ligand_heavy_atoms,
        "receptor_atom_count": extraction.receptor_atom_count,
        "receptor_sha256": sha256_file(receptor_pdb),
        "native_ligand_pdb_sha256": sha256_file(ligand_pdb),
    }

    reference_url = _instance_sdf_url(case, extraction.ligand_auth_seq_id)
    reference_sdf = case_dir / "native_reference.sdf"
    try:
        reference_hash = _download(reference_url, reference_sdf)
        reference = load_single_sdf(reference_sdf)
    except Exception as exc:
        provenance["reference"] = {"url": reference_url, "error": str(exc)}
        return _case_failure(case, "INDETERMINATE", "REFERENCE_FETCH_OR_PARSE_FAILED", provenance)
    provenance["reference"] = {"url": reference_url, "sha256": reference_hash, "heavy_atoms": reference.GetNumHeavyAtoms()}
    if reference.GetNumHeavyAtoms() != extraction.ligand_heavy_atoms:
        provenance["reference"]["pdb_heavy_atoms"] = extraction.ligand_heavy_atoms
        return _case_failure(case, "INDETERMINATE", "REFERENCE_INSTANCE_MISMATCH", provenance)

    try:
        grid = derive_redocking_grid(reference)
    except Exception as exc:
        provenance["error"] = str(exc)
        return _case_failure(case, "INDETERMINATE", "GRID_DERIVATION_FAILED", provenance)
    provenance["grid"] = grid.to_dict()
    if grid.status != "PASS":
        return _case_failure(case, "OUT_OF_DOMAIN", "BOX_OUT_OF_DOMAIN", provenance)

    starting_sdf = case_dir / "starting_conformer.sdf"
    try:
        provenance["starting_conformer"] = generate_independent_conformer(reference, starting_sdf)
    except Exception as exc:
        provenance["error"] = str(exc)
        return _case_failure(case, "INDETERMINATE", "CONFORMER_GENERATION_FAILED", provenance)

    openbabel = obabel or OpenBabelEngine()
    vina_engine = vina or VinaEngine()
    provenance["engines"] = {
        "openbabel": {"path": openbabel.executable, "version": openbabel.version},
        "vina": {"path": vina_engine.executable, "version": vina_engine.version},
    }
    if not openbabel.available:
        return _case_failure(case, "INDETERMINATE", "OPENBABEL_UNAVAILABLE", provenance)
    if not vina_engine.available:
        return _case_failure(case, "INDETERMINATE", "VINA_UNAVAILABLE", provenance)
    if not vina_engine.version or "1.2.7" not in vina_engine.version:
        return _case_failure(case, "INDETERMINATE", "VINA_VERSION_MISMATCH", provenance)

    receptor_pdbqt = case_dir / "receptor.pdbqt"
    ligand_pdbqt = case_dir / "ligand.pdbqt"
    try:
        receptor_prep = openbabel.convert(receptor_pdb, receptor_pdbqt, options=("-h", "--partialcharge", "gasteiger", "-xr"), timeout=120.0, protocol_id="redocking.v1.1.receptor-openbabel")
        ligand_prep = openbabel.convert(starting_sdf, ligand_pdbqt, options=("-h", "--partialcharge", "gasteiger"), timeout=120.0, protocol_id="redocking.v1.1.ligand-openbabel")
    except Exception as exc:
        provenance["error"] = str(exc)
        return _case_failure(case, "INDETERMINATE", "PDBQT_PREPARATION_FAILED", provenance)
    provenance["preparation"] = {"receptor": asdict(receptor_prep), "ligand": asdict(ligand_prep)}
    if receptor_prep.returncode != 0 or not receptor_prep.output_sha256:
        return _case_failure(case, "INDETERMINATE", "RECEPTOR_PREPARATION_FAILED", provenance)
    if ligand_prep.returncode != 0 or not ligand_prep.output_sha256:
        return _case_failure(case, "INDETERMINATE", "LIGAND_PREPARATION_FAILED", provenance)

    vina_output = case_dir / "vina_poses.pdbqt"
    request = DockingRequest(
        receptor_path=str(receptor_pdbqt),
        ligand_path=str(ligand_pdbqt),
        grid=GridBox(grid.center_x, grid.center_y, grid.center_z, grid.size_x, grid.size_y, grid.size_z),
        exhaustiveness=VINA_EXHAUSTIVENESS,
        cpu=VINA_CPU,
        seed=VINA_SEED,
        output_path=str(vina_output),
        target_id=case.pdb_id,
        protocol_id=PROTOCOL_ID,
        timeout=900.0,
        num_modes=VINA_NUM_MODES,
    )
    try:
        docking = vina_engine.run(request)
    except Exception as exc:
        provenance["error"] = str(exc)
        return _case_failure(case, "FAIL", "DOCKING_FAILED", provenance)
    provenance["docking"] = docking.to_dict()
    if docking.returncode != 0 or not vina_output.is_file():
        return _case_failure(case, "FAIL", "DOCKING_FAILED", provenance)

    pdbqt_text = vina_output.read_text(encoding="utf-8", errors="replace")
    model_blocks = split_vina_pdbqt_models(pdbqt_text)
    scores = parse_vina_pose_scores(pdbqt_text)
    if not model_blocks:
        return _case_failure(case, "FAIL", "NO_DOCKED_POSES", provenance)

    pose_results: list[dict[str, object]] = []
    valid_rmsd: list[float] = []
    for index, block in enumerate(model_blocks, start=1):
        pose_pdbqt = case_dir / f"pose_{index:02d}.pdbqt"
        pose_sdf = case_dir / f"pose_{index:02d}.sdf"
        pose_pdbqt.write_text(block, encoding="utf-8")
        try:
            conversion = openbabel.convert(pose_pdbqt, pose_sdf, timeout=60.0, protocol_id="redocking.v1.1.pose-openbabel")
            if conversion.returncode != 0 or not pose_sdf.is_file():
                raise RuntimeError("Open Babel pose conversion failed")
            rmsd_result = evaluate_pose_files(reference_sdf, pose_sdf)[0]
        except Exception as exc:
            pose_results.append({"rank": index, "score_kcal_mol": scores[index - 1] if index <= len(scores) else None, "status": "INDETERMINATE", "rmsd_angstrom": None, "reason": str(exc), "pdbqt_sha256": sha256_file(pose_pdbqt), "sdf_sha256": sha256_file(pose_sdf) if pose_sdf.is_file() else None})
            continue
        pose_results.append({"rank": index, "score_kcal_mol": scores[index - 1] if index <= len(scores) else None, **rmsd_result.to_dict(), "pdbqt_sha256": sha256_file(pose_pdbqt), "sdf_sha256": sha256_file(pose_sdf)})
        if rmsd_result.rmsd_angstrom is not None:
            valid_rmsd.append(float(rmsd_result.rmsd_angstrom))

    pose_1 = pose_results[0]
    pose_1_rmsd = pose_1.get("rmsd_angstrom")
    if not isinstance(pose_1_rmsd, (int, float)) or not math.isfinite(float(pose_1_rmsd)):
        result = RedockingCaseResult(case.case_id, "INDETERMINATE", None, min(valid_rmsd) if valid_rmsd else None, len(model_blocks), scores[0] if scores else None, "POSE_1_RMSD_INDETERMINATE")
        return {"case": case.to_dict(), "result": result.to_dict(), "provenance": provenance, "poses": pose_results}

    result = RedockingCaseResult(case.case_id, "PASS", float(pose_1_rmsd), min(valid_rmsd) if valid_rmsd else float(pose_1_rmsd), len(model_blocks), scores[0] if scores else None)
    return {"case": case.to_dict(), "result": result.to_dict(), "provenance": provenance, "poses": pose_results}


def summarize_redocking_results(results: Sequence[RedockingCaseResult]) -> dict[str, object]:
    if not results:
        raise ValueError("at least one redocking case result is required")
    case_ids = [item.case_id for item in results]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("redocking case ids must be unique")

    passing = [item for item in results if item.status == "PASS" and item.pose_1_rmsd_angstrom is not None]
    pose_1_values = [float(item.pose_1_rmsd_angstrom) for item in passing]
    successes = sum(item.pose_1_success for item in results)
    statuses: dict[str, int] = {}
    for item in results:
        statuses[item.status] = statuses.get(item.status, 0) + 1

    return {
        "protocol_id": PROTOCOL_ID,
        "total_cases": len(results),
        "passing_rmsd_cases": len(passing),
        "status_counts": dict(sorted(statuses.items())),
        "pose_1_rmsd_angstrom": {"mean_over_passing_cases": statistics.fmean(pose_1_values) if pose_1_values else None, "median_over_passing_cases": statistics.median(pose_1_values) if pose_1_values else None, "values": [item.pose_1_rmsd_angstrom for item in results]},
        "pose_1_rmsd_le_2_angstrom": {"count": successes, "fraction_all_frozen_cases": successes / len(results), "denominator": len(results)},
        "cases": [item.to_dict() for item in results],
        "interpretation": "pose reproduction for the frozen benchmark only; docking scores and RMSD do not establish binding affinity, biological activity, safety, efficacy, or clinical performance",
        "summary_hash": sha256_json([item.to_dict() for item in results]),
    }


def run_frozen_redocking_benchmark(workdir: str | Path) -> dict[str, object]:
    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    vina = VinaEngine()
    obabel = OpenBabelEngine()
    records = [run_redocking_case(case, root, vina=vina, obabel=obabel) for case in FROZEN_REDOCKING_CASES]
    result_objects = [
        RedockingCaseResult(
            case_id=str(record["result"]["case_id"]),
            status=str(record["result"]["status"]),
            pose_1_rmsd_angstrom=record["result"].get("pose_1_rmsd_angstrom"),
            minimum_rmsd_angstrom=record["result"].get("minimum_rmsd_angstrom"),
            pose_count=int(record["result"].get("pose_count", 0)),
            vina_pose_1_score_kcal_mol=record["result"].get("vina_pose_1_score_kcal_mol"),
            first_loss=record["result"].get("first_loss"),
        )
        for record in records
    ]
    summary = summarize_redocking_results(result_objects)
    scientific_payload = {"protocol_id": PROTOCOL_ID, "frozen_cases": [case.to_dict() for case in FROZEN_REDOCKING_CASES], "records": records, "summary": summary}
    scientific_result_hash = sha256_json(scientific_payload)
    environment = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "vina_version": vina.version,
        "openbabel_version": obabel.version,
        "vina_executable": vina.executable,
        "openbabel_executable": obabel.executable,
    }
    execution_hash = sha256_json({"scientific_result_hash": scientific_result_hash, "environment": environment})
    report = {**scientific_payload, "scientific_result_hash": scientific_result_hash, "execution_hash": execution_hash, "environment": environment}
    output = root / "redocking-result.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return report
