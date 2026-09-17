"""Frozen APODOCK-001 v1.0.2 same-frame analysis evaluator.

This module is deliberately separate from the historical REDOCK evaluators.
It consumes only a sealed prospective run and the local v1.0.2 input bundle.
The predicted ligand is never fitted to the reference: only graph-isomorphic
atom correspondence is enumerated, and Cartesian distances are measured in the
receptor frame returned by Vina.

No function in this module invokes Vina.  Open Babel is used only by the
explicit pose-representation adapter, which writes derived analysis artifacts
without modifying the raw PDBQT output.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import re
import statistics
from typing import Any, Mapping, Protocol, Sequence

from rdkit import Chem

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking import redocking as _legacy_redocking
from research_os.docking.apodock001 import matched_global_ca_pairs
from research_os.docking.apodock001_input_bundle import verify_frozen_input_bundle
from research_os.docking.apodock001_protocol import load_and_validate_v102
from research_os.docking.crossdock_alignment import (
    kabsch_source_to_target,
    parse_protein_chain,
)
from research_os.docking.redocking_v12 import _same_frame_rmsd_for_mapping
from research_os.engines.openbabel import OpenBabelEngine


ANALYSIS_SCHEMA_VERSION = "research-os.apodock001.analysis.v1"
EVALUATOR_SEMANTICS_VERSION = "1.0.2"
POSE_SUCCESS_THRESHOLD_ANGSTROM = 2.0
SYMMETRY_MAX_MATCHES = 10000
MAX_ANALYZED_POSES = 20
EXPECTED_CASE_IDS = tuple(f"APD-{index:03d}" for index in range(1, 11))
POSE_CONVERSION_ADAPTER_ID = "research-os.apodock001.openbabel-pose-adapter.v1"

FIRST_LOSS_STAGES = (
    "RAW_OUTPUT_MISSING",
    "EXECUTION_FAILED",
    "PDBQT_PARSE_FAILED",
    "SCORE_PARSE_FAILED",
    "POSE_CONVERSION_FAILED",
    "GRAPH_MISMATCH",
    "SYMMETRY_CAP_REACHED",
    "REFERENCE_TRANSFORM_MISMATCH",
    "REFERENCE_COORDINATES_INCOMPLETE",
)

_ANALYSIS_ENGINE_PAYLOAD = {
    "schema_version": ANALYSIS_SCHEMA_VERSION,
    "evaluator_semantics_version": EVALUATOR_SEMANTICS_VERSION,
    "metric": "same-frame symmetry-aware heavy-atom RMSD",
    "correspondence_policy": "element-labeled connectivity graph isomorphism",
    "symmetry_max_matches": SYMMETRY_MAX_MATCHES,
    "primary_pose_selection": "first pose in raw Vina output order",
    "secondary_pose_selection": "minimum RMSD among first 20 raw poses",
    "threshold_angstrom": POSE_SUCCESS_THRESHOLD_ANGSTROM,
    "no_predicted_to_reference_fit": True,
    "raw_seal_required": True,
}
ANALYSIS_ENGINE_ID = (
    "research-os.apodock001.analysis.v1+"
    f"{sha256_json(_ANALYSIS_ENGINE_PAYLOAD)[:16]}"
)


class APODOCK001AnalysisError(RuntimeError):
    """Base error for fail-closed analysis infrastructure."""


class AnalysisGateError(APODOCK001AnalysisError):
    """Raised when a run is not eligible for analysis."""


class PoseRepresentationAdapter(Protocol):
    """Convert one derived PDBQT pose into one derived analysis molecule."""

    adapter_id: str

    def convert(self, input_path: Path, output_path: Path) -> Mapping[str, Any] | None:
        """Convert without modifying ``input_path``."""


@dataclass(frozen=True)
class SameFrameRmsdResult:
    status: str
    rmsd_angstrom: float | None
    reference_heavy_atoms: int
    predicted_heavy_atoms: int
    reference_identity: str | None
    predicted_identity: str | None
    mapping_count: int
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PoseAnalysis:
    pose_index: int
    vina_score_kcal_mol: float | None
    rmsd_angstrom: float | None
    rmsd_status: str
    rmsd_reason: str | None
    reference_heavy_atoms: int | None = None
    predicted_heavy_atoms: int | None = None
    mapping_count: int = 0
    derived_pdbqt_path: str | None = None
    derived_sdf_path: str | None = None
    derived_pdbqt_sha256: str | None = None
    derived_sdf_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CaseAnalysis:
    case_id: str
    status: str
    pose_1_rmsd_angstrom: float | None
    minimum_rmsd_angstrom: float | None
    best_pose_index: int | None
    pose_1_success: bool | None
    secondary_success: bool | None
    returned_pose_count: int
    analyzed_pose_count: int
    first_loss: str | None
    first_loss_reason: str | None
    failed_execution: bool
    score_parse_status: str
    reference: dict[str, Any]
    poses: tuple[PoseAnalysis, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["poses"] = [pose.to_dict() for pose in self.poses]
        return value


@dataclass(frozen=True)
class ReferenceContext:
    molecule: Chem.Mol | None
    metadata: dict[str, Any]
    failure_stage: str | None = None
    failure_reason: str | None = None


@dataclass(frozen=True)
class RawResultsSeal:
    protocol_id: str
    protocol_hash: str
    planned_run_id: str
    run_id: str
    raw_results_seal_sha256: str
    records: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class OpenBabelPoseAdapter:
    """Normative PDBQT-to-analysis adapter for future sealed runs."""

    engine: OpenBabelEngine
    adapter_id: str = POSE_CONVERSION_ADAPTER_ID

    def convert(self, input_path: Path, output_path: Path) -> Mapping[str, Any]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = self.engine.convert(
            input_path,
            output_path,
            options=(),
            timeout=60.0,
            protocol_id=self.adapter_id,
        )
        if result.returncode != 0 or not output_path.is_file():
            raise APODOCK001AnalysisError(
                f"Open Babel pose conversion failed for {input_path.name}"
            )
        return {
            "adapter_id": self.adapter_id,
            "input_sha256": result.input_sha256,
            "output_sha256": result.output_sha256,
            "command": list(result.command),
        }


def _coordinate_identity(points: Sequence[Sequence[float]]) -> str:
    return sha256_json([[round(float(value), 6) for value in point] for point in points])


def _heavy_coordinates(molecule: Chem.Mol) -> tuple[tuple[float, float, float], ...]:
    heavy = _legacy_redocking._heavy_atom_copy(molecule)
    conformer = heavy.GetConformer()
    return tuple(
        (
            float(conformer.GetAtomPosition(index).x),
            float(conformer.GetAtomPosition(index).y),
            float(conformer.GetAtomPosition(index).z),
        )
        for index in range(heavy.GetNumAtoms())
    )


def _copy_with_coordinates(
    molecule: Chem.Mol,
    coordinates: Sequence[Sequence[float]],
) -> Chem.Mol:
    heavy = _legacy_redocking._heavy_atom_copy(molecule)
    if heavy.GetNumAtoms() != len(coordinates):
        raise ValueError("coordinate count does not match the heavy-atom molecule")
    transformed = Chem.Mol(heavy)
    conformer = transformed.GetConformer()
    for index, (x, y, z) in enumerate(coordinates):
        conformer.SetAtomPosition(index, (float(x), float(y), float(z)))
    return transformed


def same_frame_symmetry_aware_rmsd(
    reference: Chem.Mol,
    predicted: Chem.Mol,
    *,
    max_matches: int = SYMMETRY_MAX_MATCHES,
) -> SameFrameRmsdResult:
    """Calculate heavy-atom RMSD in-place, without any rigid-body fitting.

    ``max_matches`` is a hard fail-closed cap.  If RDKit returns exactly the
    cap, enumeration may have been truncated, so the result is indeterminate.
    The only optimized quantity is the atom correspondence mapping.
    """

    try:
        ref = _legacy_redocking._connectivity_graph(reference)
        pred = _legacy_redocking._connectivity_graph(predicted)
        ref_identity = Chem.MolToSmiles(ref, canonical=True, isomericSmiles=False)
        pred_identity = Chem.MolToSmiles(pred, canonical=True, isomericSmiles=False)
    except (RuntimeError, ValueError) as exc:
        return SameFrameRmsdResult(
            "INDETERMINATE", None, 0, 0, None, None, 0, str(exc)
        )

    reference_atoms = ref.GetNumAtoms()
    predicted_atoms = pred.GetNumAtoms()
    if reference_atoms != predicted_atoms:
        return SameFrameRmsdResult(
            "INDETERMINATE",
            None,
            reference_atoms,
            predicted_atoms,
            ref_identity,
            pred_identity,
            0,
            "heavy-atom counts differ",
        )
    if ref.GetNumBonds() != pred.GetNumBonds() or ref_identity != pred_identity:
        return SameFrameRmsdResult(
            "INDETERMINATE",
            None,
            reference_atoms,
            predicted_atoms,
            ref_identity,
            pred_identity,
            0,
            "reference and predicted element-labeled graphs differ",
        )

    try:
        matches = ref.GetSubstructMatches(
            pred,
            uniquify=False,
            useChirality=False,
            maxMatches=max_matches,
        )
    except (RuntimeError, ValueError) as exc:
        return SameFrameRmsdResult(
            "INDETERMINATE",
            None,
            reference_atoms,
            predicted_atoms,
            ref_identity,
            pred_identity,
            0,
            f"symmetry mapping failed: {exc}",
        )
    mapping_count = len(matches)
    if not matches:
        return SameFrameRmsdResult(
            "INDETERMINATE",
            None,
            reference_atoms,
            predicted_atoms,
            ref_identity,
            pred_identity,
            0,
            "no exact graph-isomorphic atom mapping was found",
        )
    if mapping_count >= max_matches:
        return SameFrameRmsdResult(
            "INDETERMINATE",
            None,
            reference_atoms,
            predicted_atoms,
            ref_identity,
            pred_identity,
            mapping_count,
            "symmetry mapping enumeration cap was reached",
        )

    try:
        best = min(
            _same_frame_rmsd_for_mapping(ref, pred, tuple(match))
            for match in matches
        )
    except (RuntimeError, ValueError) as exc:
        return SameFrameRmsdResult(
            "INDETERMINATE",
            None,
            reference_atoms,
            predicted_atoms,
            ref_identity,
            pred_identity,
            mapping_count,
            f"same-frame RMSD calculation failed: {exc}",
        )
    if not math.isfinite(best):
        return SameFrameRmsdResult(
            "INDETERMINATE",
            None,
            reference_atoms,
            predicted_atoms,
            ref_identity,
            pred_identity,
            mapping_count,
            "same-frame RMSD is non-finite",
        )
    return SameFrameRmsdResult(
        "PASS",
        float(best),
        reference_atoms,
        predicted_atoms,
        ref_identity,
        pred_identity,
        mapping_count,
    )


def _parse_ligand_components(
    pdb_text: str,
    *,
    component_ids: Sequence[str],
    author_chain: str,
    expected_auth_seq_ids: Sequence[int],
) -> tuple[tuple[float, float, float], ...]:
    grouped: dict[str, dict[tuple[int, str], list[tuple[float, float, float]]]] = {
        component: {} for component in component_ids
    }
    for line in pdb_text.splitlines():
        if len(line) < 54 or not _legacy_redocking._primary_altloc(line):
            continue
        if line[:6].strip() != "HETATM" or line[21].strip() != author_chain:
            continue
        component = line[17:20].strip()
        if component not in grouped:
            continue
        if _legacy_redocking._element_from_pdb_line(line) in {"H", "D"}:
            continue
        try:
            auth_seq_id = int(line[22:26].strip())
        except ValueError:
            continue
        point = (
            float(line[30:38]),
            float(line[38:46]),
            float(line[46:54]),
        )
        grouped[component].setdefault((auth_seq_id, line[26].strip()), []).append(point)

    points: list[tuple[float, float, float]] = []
    for index, component in enumerate(component_ids):
        instances = grouped[component]
        if len(instances) != 1:
            raise ValueError(
                f"expected one {component} instance on chain {author_chain}, "
                f"found {len(instances)}"
            )
        (auth_seq_id, _insertion), component_points = next(iter(instances.items()))
        if index < len(expected_auth_seq_ids) and auth_seq_id != expected_auth_seq_ids[index]:
            raise ValueError(
                f"{component} auth_seq_id {auth_seq_id} differs from frozen "
                f"{expected_auth_seq_ids[index]}"
            )
        points.extend(component_points)
    if not points:
        raise ValueError("frozen ligand instance has no heavy-atom coordinates")
    return tuple(points)


def _reference_failure(
    stage: str,
    reason: str,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> ReferenceContext:
    return ReferenceContext(
        molecule=None,
        metadata=dict(metadata or {}),
        failure_stage=stage,
        failure_reason=reason,
    )


def build_transformed_reference(
    protocol: Mapping[str, Any],
    bundle_root: str | Path,
    case: Mapping[str, Any],
) -> ReferenceContext:
    """Build an apo-frame reference using only frozen receptor coordinates.

    The Kabsch transform here is the frozen holo-receptor → apo-receptor
    structural transform.  It is never applied to a predicted pose and is not
    part of the pose RMSD calculation.
    """

    root = Path(bundle_root)
    case_id = str(case["case_id"])
    apo_path = root / "pdb" / f"{case['apo_pdb_id']}.pdb"
    holo_path = root / "pdb" / f"{case['holo_pdb_id']}.pdb"
    for path, expected in (
        (apo_path, str(case["apo_pdb_sha256"])),
        (holo_path, str(case["holo_pdb_sha256"])),
    ):
        if not path.is_file() or sha256_file(path) != expected:
            raise AnalysisGateError(
                f"frozen reference input hash mismatch for {case_id}: {path.name}"
            )

    try:
        apo_text = apo_path.read_text(encoding="utf-8", errors="replace")
        holo_text = holo_path.read_text(encoding="utf-8", errors="replace")
        apo_residues = parse_protein_chain(
            apo_text, str(case["apo_receptor_author_chain"])
        )
        holo_residues = parse_protein_chain(
            holo_text, str(case["holo_receptor_author_chain"])
        )
        pairs = matched_global_ca_pairs(holo_residues, apo_residues)
        expected_pairs = int(case["matched_identical_global_ca_pairs"])
        if len(pairs) != expected_pairs:
            return _reference_failure(
                "REFERENCE_TRANSFORM_MISMATCH",
                f"matched CA pair count {len(pairs)} != frozen {expected_pairs}",
            )
        transform = kabsch_source_to_target(pairs)
        if not math.isfinite(transform.rmsd_angstrom):
            return _reference_failure(
                "REFERENCE_TRANSFORM_MISMATCH",
                "holo-to-apo reference transform is non-finite",
            )
        points = _parse_ligand_components(
            holo_text,
            component_ids=tuple(case["holo_ligand_components"]),
            author_chain=str(case["holo_ligand_author_chain"]),
            expected_auth_seq_ids=tuple(case["ligand_component_auth_seq_ids"]),
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return _reference_failure("REFERENCE_COORDINATES_INCOMPLETE", str(exc))

    expected_holo_hash = str(case["holo_reference_coordinate_hash"])
    observed_holo_hash = _coordinate_identity(points)
    metadata: dict[str, Any] = {
        "apo_pdb_id": case["apo_pdb_id"],
        "holo_pdb_id": case["holo_pdb_id"],
        "holo_reference_coordinate_hash": observed_holo_hash,
        "transformed_holo_reference_coordinate_hash": None,
        "matched_identical_global_ca_pairs": len(pairs),
        "transform_rmsd_angstrom": transform.rmsd_angstrom,
        "reference_heavy_atoms": len(points),
        "reference_policy": "frozen holo ligand transformed by frozen receptor transform",
    }
    if observed_holo_hash != expected_holo_hash:
        return _reference_failure(
            "REFERENCE_TRANSFORM_MISMATCH",
            "holo reference coordinate hash differs from the frozen protocol",
            metadata=metadata,
        )

    transformed_points = transform.apply(points)
    expected_transformed_hash = str(case["transformed_holo_reference_coordinate_hash"])
    observed_transformed_hash = _coordinate_identity(transformed_points)
    metadata["transformed_holo_reference_coordinate_hash"] = observed_transformed_hash
    if observed_transformed_hash != expected_transformed_hash:
        return _reference_failure(
            "REFERENCE_TRANSFORM_MISMATCH",
            "transformed holo reference coordinate hash differs from the frozen protocol",
            metadata=metadata,
        )

    if case_id == "APD-010":
        # The structural PDB has 24 mapped heavy atoms while the immutable
        # BEM+MAV adapter has 25.  No experimental coordinate is fabricated.
        metadata["policy"] = "BEM+MAV missing complete experimental correspondence"
        return _reference_failure(
            "REFERENCE_COORDINATES_INCOMPLETE",
            "APD-010 BEM+MAV has no complete mapped experimental reference; "
            "conformer coordinates are not substituted",
            metadata=metadata,
        )

    reference_path = root / "reference-sdf" / str(case["reference_filename"])
    expected_sdf_hash = str(case["reference_sdf_sha256"])
    if not reference_path.is_file() or sha256_file(reference_path) != expected_sdf_hash:
        raise AnalysisGateError(
            f"frozen reference SDF hash mismatch for {case_id}: {reference_path.name}"
        )
    try:
        reference = _legacy_redocking.load_single_sdf(reference_path)
        heavy = _legacy_redocking._heavy_atom_copy(reference)
    except (OSError, ValueError, RuntimeError) as exc:
        return _reference_failure("REFERENCE_COORDINATES_INCOMPLETE", str(exc), metadata=metadata)

    sdf_points = _heavy_coordinates(heavy)
    if len(sdf_points) != len(points):
        return _reference_failure(
            "REFERENCE_COORDINATES_INCOMPLETE",
            "reference SDF and frozen holo ligand have different heavy-atom counts",
            metadata=metadata,
        )
    if any(math.dist(sdf_point, pdb_point) > 1e-6 for sdf_point, pdb_point in zip(sdf_points, points)):
        return _reference_failure(
            "REFERENCE_COORDINATES_INCOMPLETE",
            "reference SDF coordinates do not reproduce the frozen holo coordinate order",
            metadata=metadata,
        )
    metadata["reference_sdf_sha256"] = expected_sdf_hash
    metadata["reference_sdf_coordinate_hash"] = _coordinate_identity(sdf_points)
    metadata["policy"] = "frozen reference SDF coordinates transformed by receptor transform"
    return ReferenceContext(
        molecule=_copy_with_coordinates(heavy, transformed_points),
        metadata=metadata,
    )


def _split_pdbqt_models(text: str) -> list[str]:
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


_VINA_SCORE_RE = re.compile(
    r"^REMARK\s+VINA\s+RESULT:\s+"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
)


def _model_score(model: str) -> float | None:
    matches = [_VINA_SCORE_RE.match(line) for line in model.splitlines()]
    values = [float(match.group(1)) for match in matches if match is not None]
    if len(values) != 1 or not math.isfinite(values[0]):
        return None
    return values[0]


def _pose_stage(reason: str | None) -> str:
    text = (reason or "").lower()
    if "cap" in text or "enumeration" in text:
        return "SYMMETRY_CAP_REACHED"
    if "graph" in text or "heavy-atom" in text or "mapping" in text:
        return "GRAPH_MISMATCH"
    return "GRAPH_MISMATCH"


def evaluate_pose_sequence(
    case_id: str,
    reference: Chem.Mol | None,
    poses: Sequence[Chem.Mol | None],
    scores: Sequence[float | None],
    *,
    returned_pose_count: int | None = None,
    reference_failure_stage: str | None = None,
    reference_failure_reason: str | None = None,
    conversion_failures: Mapping[int, str] | None = None,
    score_parse_failed: bool = False,
    reference_metadata: Mapping[str, Any] | None = None,
    derived_paths: Mapping[int, Mapping[str, str | None]] | None = None,
) -> CaseAnalysis:
    """Evaluate an ordered pose sequence without changing any coordinates."""

    if len(poses) != len(scores):
        raise ValueError("pose and score vectors must have equal length")
    analyzed_count = min(len(poses), MAX_ANALYZED_POSES)
    conversion_failures = conversion_failures or {}
    derived_paths = derived_paths or {}
    pose_records: list[PoseAnalysis] = []
    for zero_index in range(analyzed_count):
        pose_index = zero_index + 1
        score = scores[zero_index]
        paths = derived_paths.get(pose_index, {})
        if reference_failure_stage:
            result = SameFrameRmsdResult(
                "INDETERMINATE",
                None,
                reference.GetNumAtoms() if reference is not None else 0,
                0,
                None,
                None,
                0,
                reference_failure_reason,
            )
        elif pose_index in conversion_failures:
            result = SameFrameRmsdResult(
                "INDETERMINATE", None, 0, 0, None, None, 0, conversion_failures[pose_index]
            )
        elif poses[zero_index] is None:
            result = SameFrameRmsdResult(
                "INDETERMINATE", None, 0, 0, None, None, 0, "pose conversion produced no molecule"
            )
        else:
            result = same_frame_symmetry_aware_rmsd(reference, poses[zero_index])  # type: ignore[arg-type]
        pose_records.append(
            PoseAnalysis(
                pose_index=pose_index,
                vina_score_kcal_mol=score,
                rmsd_angstrom=result.rmsd_angstrom,
                rmsd_status=result.status,
                rmsd_reason=result.reason,
                reference_heavy_atoms=result.reference_heavy_atoms,
                predicted_heavy_atoms=result.predicted_heavy_atoms,
                mapping_count=result.mapping_count,
                derived_pdbqt_path=paths.get("pdbqt"),
                derived_sdf_path=paths.get("sdf"),
                derived_pdbqt_sha256=paths.get("pdbqt_sha256"),
                derived_sdf_sha256=paths.get("sdf_sha256"),
            )
        )

    score_status = "FAILED" if score_parse_failed else "PASS"
    valid = [pose for pose in pose_records if pose.rmsd_status == "PASS" and pose.rmsd_angstrom is not None]
    pose_1 = pose_records[0] if pose_records else None
    pose_1_rmsd = pose_1.rmsd_angstrom if pose_1 is not None else None
    minimum_pose = min(valid, key=lambda pose: (float(pose.rmsd_angstrom), pose.pose_index), default=None)
    minimum_rmsd = minimum_pose.rmsd_angstrom if minimum_pose else None
    first_loss: str | None = reference_failure_stage
    first_loss_reason = reference_failure_reason
    if first_loss is None and score_parse_failed:
        first_loss = "SCORE_PARSE_FAILED"
        first_loss_reason = "every returned pose must contain exactly one finite Vina score"
    if first_loss is None and conversion_failures:
        first_loss = "POSE_CONVERSION_FAILED"
        first_loss_reason = conversion_failures[min(conversion_failures)]
    if first_loss is None:
        for pose in pose_records:
            if pose.rmsd_status != "PASS":
                first_loss = _pose_stage(pose.rmsd_reason)
                first_loss_reason = pose.rmsd_reason
                break

    primary_determinate = (
        pose_1 is not None
        and pose_1.rmsd_status == "PASS"
        and pose_1.rmsd_angstrom is not None
        and not score_parse_failed
        and reference_failure_stage is None
    )
    status = "DETERMINATE" if primary_determinate else "INDETERMINATE"
    return CaseAnalysis(
        case_id=case_id,
        status=status,
        pose_1_rmsd_angstrom=pose_1_rmsd,
        minimum_rmsd_angstrom=minimum_rmsd,
        best_pose_index=minimum_pose.pose_index if minimum_pose else None,
        pose_1_success=(pose_1_rmsd <= POSE_SUCCESS_THRESHOLD_ANGSTROM) if primary_determinate else None,
        secondary_success=(minimum_rmsd <= POSE_SUCCESS_THRESHOLD_ANGSTROM) if minimum_rmsd is not None else None,
        returned_pose_count=returned_pose_count if returned_pose_count is not None else len(poses),
        analyzed_pose_count=analyzed_count,
        first_loss=first_loss,
        first_loss_reason=first_loss_reason,
        failed_execution=False,
        score_parse_status=score_status,
        reference=dict(reference_metadata or {}),
        poses=tuple(pose_records),
    )


def _failed_case(
    case_id: str,
    *,
    stage: str,
    reason: str,
    returned_pose_count: int = 0,
) -> CaseAnalysis:
    return CaseAnalysis(
        case_id=case_id,
        status="FAILED_EXECUTION" if stage in {"RAW_OUTPUT_MISSING", "EXECUTION_FAILED"} else "INDETERMINATE",
        pose_1_rmsd_angstrom=None,
        minimum_rmsd_angstrom=None,
        best_pose_index=None,
        pose_1_success=None,
        secondary_success=None,
        returned_pose_count=returned_pose_count,
        analyzed_pose_count=0,
        first_loss=stage,
        first_loss_reason=reason,
        failed_execution=stage in {"RAW_OUTPUT_MISSING", "EXECUTION_FAILED"},
        score_parse_status="NOT_ATTEMPTED",
        reference={},
        poses=(),
    )


def _raw_path(run_root: Path, record: Mapping[str, Any]) -> Path:
    value = record.get("raw_output_path")
    if not isinstance(value, str) or not value:
        raise AnalysisGateError("raw result record has no raw_output_path")
    path = Path(value)
    return path if path.is_absolute() else run_root / path


def verify_raw_results_seal(
    run_root: str | Path,
    *,
    protocol_id: str,
    protocol_hash: str,
    planned_run_id: str,
    case_ids: Sequence[str] = EXPECTED_CASE_IDS,
) -> RawResultsSeal:
    """Require and revalidate both run-manifest and raw-results-seal."""

    root = Path(run_root)
    manifest_path = root / "run-manifest.json"
    seal_path = root / "raw-results-seal.json"
    if not manifest_path.is_file() or not seal_path.is_file():
        raise AnalysisGateError("analysis requires run-manifest.json and raw-results-seal.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        seal = json.loads(seal_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnalysisGateError(f"cannot load raw result seal: {exc}") from exc
    if manifest.get("status") != "RAW_RESULTS_SEALED" or manifest.get("raw_results_sealed") is not True:
        raise AnalysisGateError("analysis requires status=RAW_RESULTS_SEALED and raw_results_sealed=true")
    if seal.get("status") != "SEALED":
        raise AnalysisGateError("raw-results-seal.json is not SEALED")
    for payload, name in ((manifest, "run-manifest"), (seal, "raw-results-seal")):
        if payload.get("protocol_id") != protocol_id or payload.get("protocol_hash") != protocol_hash:
            raise AnalysisGateError(f"{name} protocol identity differs from v1.0.2")
    if manifest.get("planned_run_id") != planned_run_id:
        raise AnalysisGateError("run manifest planned_run_id differs from the frozen execution plan")
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise AnalysisGateError("sealed run must contain a final run_id")
    if seal.get("run_id") != run_id:
        raise AnalysisGateError("raw-results-seal run_id differs from run-manifest")

    records_list = manifest.get("cases")
    if not isinstance(records_list, list):
        raise AnalysisGateError("run-manifest cases are missing")
    records = {str(record.get("case_id")): dict(record) for record in records_list if isinstance(record, dict)}
    expected_ids = tuple(case_ids)
    if tuple(records) != expected_ids or len(records) != len(records_list):
        raise AnalysisGateError("run-manifest case order or identity differs from APD-001..APD-010")

    observed_hashes: dict[str, str | None] = {}
    for case_id in expected_ids:
        record = records[case_id]
        path = _raw_path(root, record)
        declared = record.get("raw_output_sha256")
        if declared is not None and (not isinstance(declared, str) or len(declared) != 64):
            raise AnalysisGateError(f"invalid raw output hash for {case_id}")
        observed = sha256_file(path) if path.is_file() else None
        if observed != declared:
            raise AnalysisGateError(f"BLOCKED: raw result seal mismatch ({case_id})")
        observed_hashes[case_id] = observed

    declared_hashes = seal.get("raw_output_hashes")
    if declared_hashes != observed_hashes:
        raise AnalysisGateError("BLOCKED: raw result seal mismatch")
    seal_hash = sha256_json(observed_hashes)
    if seal.get("raw_results_seal_sha256") != seal_hash or manifest.get("raw_results_seal_sha256") != seal_hash:
        raise AnalysisGateError("BLOCKED: raw result seal mismatch")
    return RawResultsSeal(
        protocol_id=protocol_id,
        protocol_hash=protocol_hash,
        planned_run_id=planned_run_id,
        run_id=run_id,
        raw_results_seal_sha256=seal_hash,
        records=records,
    )


def _analyze_case(
    protocol: Mapping[str, Any],
    bundle_root: Path,
    run_root: Path,
    record: Mapping[str, Any],
    converter: PoseRepresentationAdapter,
) -> CaseAnalysis:
    case_id = str(record["case_id"])
    if record.get("status") != "COMPLETED":
        return _failed_case(case_id, stage="EXECUTION_FAILED", reason="execution record is not COMPLETED")
    raw_path = _raw_path(run_root, record)
    if not raw_path.is_file() or record.get("raw_output_sha256") is None:
        return _failed_case(case_id, stage="RAW_OUTPUT_MISSING", reason="sealed raw output is absent")
    raw_hash_before = sha256_file(raw_path)
    if raw_hash_before != record.get("raw_output_sha256"):
        raise AnalysisGateError(f"BLOCKED: raw result seal mismatch ({case_id})")
    raw_text = raw_path.read_text(encoding="utf-8", errors="replace")
    model_blocks = _split_pdbqt_models(raw_text)
    if not model_blocks:
        return _failed_case(case_id, stage="PDBQT_PARSE_FAILED", reason="no PDBQT models were found")
    scores = [_model_score(model) for model in model_blocks]
    score_parse_failed = any(score is None for score in scores)
    case = next(item for item in protocol["benchmark"]["cases"] if item["case_id"] == case_id)
    if score_parse_failed:
        result = evaluate_pose_sequence(
            case_id,
            None,
            [None] * min(len(model_blocks), MAX_ANALYZED_POSES),
            scores[:MAX_ANALYZED_POSES],
            returned_pose_count=len(model_blocks),
            score_parse_failed=True,
        )
        if raw_hash_before != sha256_file(raw_path):
            raise AnalysisGateError(f"BLOCKED: raw result seal mismatch ({case_id})")
        return result

    reference = build_transformed_reference(protocol, bundle_root, case)
    pose_molecules: list[Chem.Mol | None] = []
    conversion_failures: dict[int, str] = {}
    derived_paths: dict[int, dict[str, str | None]] = {}
    derived_case_root = run_root / "analysis-derived" / case_id
    for zero_index, block in enumerate(model_blocks[:MAX_ANALYZED_POSES]):
        pose_index = zero_index + 1
        derived_pdbqt = derived_case_root / f"pose_{pose_index:02d}.pdbqt"
        derived_sdf = derived_case_root / f"pose_{pose_index:02d}.sdf"
        derived_pdbqt.parent.mkdir(parents=True, exist_ok=True)
        derived_pdbqt.write_bytes(block.encode("utf-8"))
        try:
            converter.convert(derived_pdbqt, derived_sdf)
            if not derived_sdf.is_file() or derived_sdf.stat().st_size == 0:
                raise APODOCK001AnalysisError("pose adapter produced no SDF")
            pose_molecules.append(_legacy_redocking.load_single_sdf(derived_sdf))
        except (OSError, ValueError, RuntimeError, APODOCK001AnalysisError) as exc:
            pose_molecules.append(None)
            conversion_failures[pose_index] = str(exc)
        derived_paths[pose_index] = {
            "pdbqt": str(derived_pdbqt.relative_to(run_root).as_posix()),
            "sdf": str(derived_sdf.relative_to(run_root).as_posix()) if derived_sdf.is_file() else None,
            "pdbqt_sha256": sha256_file(derived_pdbqt),
            "sdf_sha256": sha256_file(derived_sdf) if derived_sdf.is_file() else None,
        }
    if raw_hash_before != sha256_file(raw_path):
        raise AnalysisGateError(f"BLOCKED: raw result seal mismatch ({case_id})")
    return evaluate_pose_sequence(
        case_id,
        reference.molecule,
        pose_molecules,
        scores[:MAX_ANALYZED_POSES],
        returned_pose_count=len(model_blocks),
        reference_failure_stage=reference.failure_stage,
        reference_failure_reason=reference.failure_reason,
        conversion_failures=conversion_failures,
        reference_metadata=reference.metadata,
        derived_paths=derived_paths,
    )


def aggregate_case_analyses(cases: Sequence[CaseAnalysis]) -> dict[str, Any]:
    """Aggregate the complete ten-case vector without silently excluding cases."""

    ordered = list(cases)
    case_ids = [case.case_id for case in ordered]
    if tuple(case_ids) != EXPECTED_CASE_IDS:
        raise ValueError("analysis aggregation requires APD-001 through APD-010 in frozen order")
    determinate = [case for case in ordered if case.status == "DETERMINATE"]
    indeterminate = [case for case in ordered if case.status == "INDETERMINATE"]
    failed = [case for case in ordered if case.failed_execution]
    primary_values = [float(case.pose_1_rmsd_angstrom) for case in determinate if case.pose_1_rmsd_angstrom is not None]
    secondary_values = [float(case.minimum_rmsd_angstrom) for case in determinate if case.minimum_rmsd_angstrom is not None]
    primary_successes = sum(bool(case.pose_1_success) for case in determinate)
    secondary_successes = sum(bool(case.secondary_success) for case in determinate)
    return {
        "case_order": case_ids,
        "determinate_count": len(determinate),
        "indeterminate_count": len(indeterminate),
        "failed_execution_count": len(failed),
        "indeterminate_case_ids": [case.case_id for case in indeterminate],
        "failed_execution_case_ids": [case.case_id for case in failed],
        "first_loss_counts": dict(sorted(Counter(case.first_loss for case in ordered if case.first_loss).items())),
        "primary": {
            "metric": "pose_1_rmsd_angstrom",
            "success_threshold_angstrom": POSE_SUCCESS_THRESHOLD_ANGSTROM,
            "success_count": primary_successes,
            "denominator": len(primary_values),
            "mean_over_determinate": statistics.fmean(primary_values) if primary_values else None,
            "median_over_determinate": statistics.median(primary_values) if primary_values else None,
            "excluded_case_ids": [case.case_id for case in ordered if case not in determinate],
        },
        "secondary": {
            "metric": "minimum_rmsd_angstrom",
            "success_threshold_angstrom": POSE_SUCCESS_THRESHOLD_ANGSTROM,
            "success_count": secondary_successes,
            "denominator": len(secondary_values),
            "mean_over_determinate": statistics.fmean(secondary_values) if secondary_values else None,
            "median_over_determinate": statistics.median(secondary_values) if secondary_values else None,
            "excluded_case_ids": [case.case_id for case in ordered if case not in determinate],
        },
        "cases": [case.to_dict() for case in ordered],
    }


def analyze_sealed_run(
    *,
    protocol_path: str | Path,
    bundle_root: str | Path,
    run_root: str | Path,
    converter: PoseRepresentationAdapter,
    analysis_commit_sha: str,
) -> dict[str, Any]:
    """Analyze exactly one already-sealed run without invoking Vina."""

    protocol = load_and_validate_v102(Path(protocol_path))
    bundle = Path(bundle_root)
    verify_frozen_input_bundle(protocol, bundle)
    planned_run_id = _planned_run_id_from_protocol(protocol, Path(protocol_path))
    seal = verify_raw_results_seal(
        run_root,
        protocol_id=str(protocol["protocol_id"]),
        protocol_hash=str(protocol["protocol_hash"]),
        planned_run_id=planned_run_id,
    )
    root = Path(run_root)
    cases = tuple(
        _analyze_case(protocol, bundle, root, seal.records[case_id], converter)
        for case_id in EXPECTED_CASE_IDS
    )
    aggregation = aggregate_case_analyses(cases)
    manifest: dict[str, Any] = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "status": "ANALYSIS_COMPLETE",
        "protocol_id": protocol["protocol_id"],
        "protocol_hash": protocol["protocol_hash"],
        "planned_run_id": planned_run_id,
        "run_id": seal.run_id,
        "raw_results_seal_sha256": seal.raw_results_seal_sha256,
        "analysis_engine_id": ANALYSIS_ENGINE_ID,
        "evaluator_semantics_version": EVALUATOR_SEMANTICS_VERSION,
        "analysis_commit_sha": analysis_commit_sha,
        "pose_representation_adapter": getattr(converter, "adapter_id", POSE_CONVERSION_ADAPTER_ID),
        "same_frame_no_fit": True,
        "symmetry_max_matches": SYMMETRY_MAX_MATCHES,
        "primary_pose_rule": "first pose in raw Vina output order",
        "secondary_pose_rule": "minimum RMSD among first 20 raw poses",
        "success_threshold_angstrom": POSE_SUCCESS_THRESHOLD_ANGSTROM,
        "aggregation": aggregation,
        "indeterminates": [
            {
                "case_id": case.case_id,
                "first_loss": case.first_loss,
                "reason": case.first_loss_reason,
            }
            for case in cases
            if case.status != "DETERMINATE"
        ],
    }
    manifest["analysis_manifest_sha256"] = sha256_json(manifest)
    return manifest


def _planned_run_id_from_protocol(protocol: Mapping[str, Any], protocol_path: Path) -> str:
    """Rebuild the deterministic plan identity without reading future results."""

    from research_os.docking.apodock001_execution import build_execution_plan
    from research_os.docking.apodock001_runner import APODOCK001Runner

    runner = APODOCK001Runner(protocol_path)
    return build_execution_plan(protocol, runner).planned_run_id


def write_analysis_manifest(path: str | Path, manifest: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "ANALYSIS_ENGINE_ID",
    "ANALYSIS_SCHEMA_VERSION",
    "EVALUATOR_SEMANTICS_VERSION",
    "FIRST_LOSS_STAGES",
    "MAX_ANALYZED_POSES",
    "POSE_SUCCESS_THRESHOLD_ANGSTROM",
    "SYMMETRY_MAX_MATCHES",
    "APODOCK001AnalysisError",
    "AnalysisGateError",
    "CaseAnalysis",
    "OpenBabelPoseAdapter",
    "PoseAnalysis",
    "PoseRepresentationAdapter",
    "RawResultsSeal",
    "SameFrameRmsdResult",
    "aggregate_case_analyses",
    "analyze_sealed_run",
    "build_transformed_reference",
    "evaluate_pose_sequence",
    "same_frame_symmetry_aware_rmsd",
    "verify_raw_results_seal",
    "write_analysis_manifest",
]
