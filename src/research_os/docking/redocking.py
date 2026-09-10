from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from pathlib import Path
import statistics
from typing import Iterable, Sequence

from rdkit import Chem
from rdkit.Chem import rdMolAlign

from research_os.core.hashing import sha256_file, sha256_json


PROTOCOL_ID = "research-os.redocking.v1"
POSE_SUCCESS_THRESHOLD_ANGSTROM = 2.0
BOX_PADDING_ANGSTROM = 6.0
BOX_MIN_SIDE_ANGSTROM = 20.0
BOX_MAX_SIDE_ANGSTROM = 30.0


@dataclass(frozen=True)
class RedockingCase:
    case_id: str
    pdb_id: str
    ligand_id: str
    author_chain: str
    target: str
    resolution_angstrom: float
    source_url: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


FROZEN_REDOCKING_CASES: tuple[RedockingCase, ...] = (
    RedockingCase("RDK-001", "1STP", "BTN", "A", "streptavidin", 2.60, "https://www.rcsb.org/structure/1STP"),
    RedockingCase("RDK-002", "3PTB", "BEN", "A", "beta-trypsin", 1.70, "https://www.rcsb.org/structure/3PTB"),
    RedockingCase("RDK-003", "1HVR", "XK2", "A", "HIV-1 protease", 1.80, "https://www.rcsb.org/structure/1HVR"),
    RedockingCase("RDK-004", "1M17", "AQ4", "A", "EGFR kinase domain", 2.60, "https://www.rcsb.org/structure/1M17"),
    RedockingCase("RDK-005", "1IEP", "STI", "A", "c-Abl kinase domain", 2.10, "https://www.rcsb.org/structure/1IEP"),
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
                        "unclamped_size": [
                            self.unclamped_size_x,
                            self.unclamped_size_y,
                            self.unclamped_size_z,
                        ],
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


def _heavy_atom_copy(mol: Chem.Mol) -> Chem.Mol:
    if mol is None:
        raise ValueError("molecule is required")
    try:
        heavy = Chem.RemoveHs(Chem.Mol(mol), sanitize=True)
    except Exception as exc:  # RDKit raises multiple exception types depending on parser state.
        raise ValueError("molecule could not be sanitized for RMSD evaluation") from exc
    if heavy.GetNumAtoms() == 0:
        raise ValueError("molecule contains no heavy atoms")
    if heavy.GetNumConformers() != 1:
        raise ValueError("exactly one conformer is required per pose")
    return heavy


def _graph_identity(mol: Chem.Mol) -> str:
    heavy = _heavy_atom_copy(mol)
    return Chem.MolToSmiles(heavy, canonical=True, isomericSmiles=True)


def symmetry_aware_heavy_atom_rmsd(reference: Chem.Mol, predicted: Chem.Mol) -> PoseRmsdResult:
    """Return graph-validated, symmetry-aware heavy-atom pose RMSD.

    Raw atom index correspondence is never assumed. Molecules must have the same
    canonical heavy-atom graph and one conformer each. RDKit's GetBestRMS then
    evaluates symmetry-equivalent mappings while optimally aligning the probe.
    """

    try:
        ref = _heavy_atom_copy(reference)
        pred = _heavy_atom_copy(predicted)
        ref_identity = Chem.MolToSmiles(ref, canonical=True, isomericSmiles=True)
        pred_identity = Chem.MolToSmiles(pred, canonical=True, isomericSmiles=True)
    except ValueError as exc:
        return PoseRmsdResult("INDETERMINATE", None, 0, 0, None, None, reason=str(exc))

    if ref.GetNumAtoms() != pred.GetNumAtoms():
        return PoseRmsdResult(
            "INDETERMINATE",
            None,
            ref.GetNumAtoms(),
            pred.GetNumAtoms(),
            ref_identity,
            pred_identity,
            reason="heavy-atom counts differ",
        )
    if ref_identity != pred_identity:
        return PoseRmsdResult(
            "INDETERMINATE",
            None,
            ref.GetNumAtoms(),
            pred.GetNumAtoms(),
            ref_identity,
            pred_identity,
            reason="reference and predicted heavy-atom graphs differ",
        )

    try:
        rmsd = float(rdMolAlign.GetBestRMS(pred, ref))
    except (RuntimeError, ValueError) as exc:
        return PoseRmsdResult(
            "INDETERMINATE",
            None,
            ref.GetNumAtoms(),
            pred.GetNumAtoms(),
            ref_identity,
            pred_identity,
            reason=f"symmetry-aware atom mapping failed: {exc}",
        )
    if not math.isfinite(rmsd):
        return PoseRmsdResult(
            "INDETERMINATE",
            None,
            ref.GetNumAtoms(),
            pred.GetNumAtoms(),
            ref_identity,
            pred_identity,
            reason="RMSD is non-finite",
        )
    return PoseRmsdResult(
        "PASS",
        rmsd,
        ref.GetNumAtoms(),
        pred.GetNumAtoms(),
        ref_identity,
        pred_identity,
    )


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
        return RedockingGrid(
            *center,
            *sizes,
            *required,
            status="OUT_OF_DOMAIN",
            reason="native-ligand box rule requires a side larger than 30 Å",
        )

    sizes = [max(side, BOX_MIN_SIDE_ANGSTROM) for side in required]
    return RedockingGrid(*center, *sizes, *required, status="PASS")


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
        results.append(
            PoseRmsdResult(
                raw.status,
                raw.rmsd_angstrom,
                raw.reference_heavy_atoms,
                raw.predicted_heavy_atoms,
                raw.reference_identity,
                raw.predicted_identity,
                reference_sha256=reference_hash,
                predicted_sha256=predicted_hash,
                reason=raw.reason,
            )
        )
    return results


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
        "pose_1_rmsd_angstrom": {
            "mean_over_passing_cases": statistics.fmean(pose_1_values) if pose_1_values else None,
            "median_over_passing_cases": statistics.median(pose_1_values) if pose_1_values else None,
            "values": [item.pose_1_rmsd_angstrom for item in results],
        },
        "pose_1_rmsd_le_2_angstrom": {
            "count": successes,
            "fraction_all_frozen_cases": successes / len(results),
            "denominator": len(results),
        },
        "cases": [item.to_dict() for item in results],
        "interpretation": (
            "pose reproduction for the frozen benchmark only; docking scores and RMSD do not establish "
            "binding affinity, biological activity, safety, efficacy, or clinical performance"
        ),
        "summary_hash": sha256_json([item.to_dict() for item in results]),
    }
