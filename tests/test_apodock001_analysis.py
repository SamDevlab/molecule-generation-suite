from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest
from rdkit import Chem

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking import apodock001_analysis as analysis
from research_os.docking.apodock001_analysis import (
    ANALYSIS_ENGINE_ID,
    AnalysisGateError,
    CaseAnalysis,
    aggregate_case_analyses,
    analyze_sealed_run,
    build_transformed_reference,
    evaluate_pose_sequence,
    same_frame_symmetry_aware_rmsd,
    verify_raw_results_seal,
)
from research_os.docking.apodock001_protocol import load_and_validate_v102


ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "configs/apodock001-protocol-freeze-v1.0.2.json"
BUNDLE = ROOT / "inputs/apodock001/v1.0.2"
PROTOCOL_ID = "research-os.apodock001.protocol.v1.0.2+aa40517362e14795"
PROTOCOL_HASH = "aa40517362e14795a9ea4747b632fab81b2fc1f5bb49e4c880d9ad38699de03c"
PLANNED_RUN_ID = "research-os.apodock001.planned-run.v1+ff217589e517ab64"


def _molecule(smiles: str, coordinates: list[tuple[float, float, float]]) -> Chem.Mol:
    molecule = Chem.MolFromSmiles(smiles)
    assert molecule is not None
    assert molecule.GetNumAtoms() == len(coordinates)
    conformer = Chem.Conformer(molecule.GetNumAtoms())
    for index, point in enumerate(coordinates):
        conformer.SetAtomPosition(index, point)
    molecule.AddConformer(conformer)
    return molecule


def _cc_o(offset: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> Chem.Mol:
    ox, oy, oz = offset
    return _molecule("CCO", [(0.0 + ox, 0.0 + oy, 0.0 + oz), (1.5 + ox, 0.0 + oy, 0.0 + oz), (2.5 + ox, 1.0 + oy, 0.0 + oz)])


def _pdbqt(scores: list[float]) -> bytes:
    blocks = []
    for index, score in enumerate(scores, start=1):
        blocks.append(
            "\n".join(
                [
                    f"MODEL        {index}",
                    f"REMARK VINA RESULT: {score:.3f} 0.000 0.000",
                    "ENDMDL",
                    "",
                ]
            )
        )
    return "".join(blocks).encode("utf-8")


class _SyntheticPoseAdapter:
    adapter_id = "fixture.openbabel-pose-adapter.v1"

    def convert(self, input_path: Path, output_path: Path) -> dict[str, str]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer = Chem.SDWriter(str(output_path))
        writer.write(_cc_o())
        writer.close()
        return {"adapter_id": self.adapter_id}


def _write_sealed_fixture(root: Path, *, scores: list[float] | None = None) -> Path:
    run_root = root / "run"
    run_root.mkdir(parents=True)
    scores = scores or [-1.0]
    records = []
    raw_hashes: dict[str, str | None] = {}
    for case_id in (f"APD-{index:03d}" for index in range(1, 11)):
        raw_path = run_root / "raw" / case_id / "vina_poses.pdbqt"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(_pdbqt(scores))
        digest = sha256_file(raw_path)
        raw_hashes[case_id] = digest
        records.append(
            {
                "case_id": case_id,
                "status": "COMPLETED",
                "raw_output_path": str(raw_path),
                "raw_output_sha256": digest,
            }
        )
    seal_hash = sha256_json(raw_hashes)
    manifest = {
        "schema_version": "research-os.apodock001.run-manifest.v1",
        "status": "RAW_RESULTS_SEALED",
        "protocol_id": PROTOCOL_ID,
        "protocol_hash": PROTOCOL_HASH,
        "planned_run_id": PLANNED_RUN_ID,
        "run_id": "research-os.apodock001.run.v1+fixture00000000",
        "cases": records,
        "raw_results_sealed": True,
        "raw_results_seal_sha256": seal_hash,
    }
    seal = {
        "schema_version": "research-os.apodock001.raw-results-seal.v1",
        "status": "SEALED",
        "protocol_id": PROTOCOL_ID,
        "protocol_hash": PROTOCOL_HASH,
        "run_id": manifest["run_id"],
        "raw_results_seal_sha256": seal_hash,
        "raw_output_hashes": raw_hashes,
    }
    (run_root / "run-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (run_root / "raw-results-seal.json").write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    return run_root


def test_same_frame_identical_pose_is_zero_and_translation_is_not_fitted() -> None:
    reference = _cc_o()
    identical = _cc_o()
    translated = _cc_o((5.0, 0.0, 0.0))
    assert same_frame_symmetry_aware_rmsd(reference, identical).rmsd_angstrom == pytest.approx(0.0)
    assert same_frame_symmetry_aware_rmsd(reference, translated).rmsd_angstrom == pytest.approx(5.0)


def test_rotation_without_fit_remains_nonzero() -> None:
    reference = _molecule("CCO", [(1.0, 0.0, 0.0), (2.5, 0.0, 0.0), (3.5, 1.0, 0.0)])
    rotated = _molecule("CCO", [(0.0, 1.0, 0.0), (0.0, 2.5, 0.0), (-1.0, 3.5, 0.0)])
    result = same_frame_symmetry_aware_rmsd(reference, rotated)
    assert result.status == "PASS"
    assert result.rmsd_angstrom is not None and result.rmsd_angstrom > 0.0


def test_atom_ordering_and_symmetric_permutation_use_graph_mapping() -> None:
    reference = _cc_o()
    reordered = Chem.RenumberAtoms(reference, [2, 1, 0])
    assert same_frame_symmetry_aware_rmsd(reference, reordered).rmsd_angstrom == pytest.approx(0.0)

    symmetric = _molecule("CC(C)C", [(0.0, 0.0, 0.0), (1.5, 0.0, 0.0), (1.5, 1.0, 0.0), (1.5, -1.0, 0.0)])
    permuted = Chem.RenumberAtoms(symmetric, [0, 1, 3, 2])
    assert same_frame_symmetry_aware_rmsd(symmetric, permuted).rmsd_angstrom == pytest.approx(0.0)


def test_graph_and_heavy_atom_mismatch_are_indeterminate() -> None:
    assert same_frame_symmetry_aware_rmsd(_cc_o(), _molecule("CCN", [(0, 0, 0), (1, 0, 0), (2, 0, 0)])).status == "INDETERMINATE"
    assert same_frame_symmetry_aware_rmsd(_cc_o(), _molecule("CCCO", [(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)])).status == "INDETERMINATE"


def test_symmetry_cap_is_fail_closed() -> None:
    count = 6
    molecule = _molecule(
        ".".join(["CC"] * count),
        [(float(index), 0.0, 0.0) for index in range(count * 2)],
    )
    result = same_frame_symmetry_aware_rmsd(molecule, molecule)
    assert result.status == "INDETERMINATE"
    assert "cap" in (result.reason or "").lower()
    assert result.mapping_count == analysis.SYMMETRY_MAX_MATCHES


def test_primary_pose_one_secondary_minimum_and_pose_twenty_cap() -> None:
    reference = _cc_o()
    pose_1 = _cc_o((5.0, 0.0, 0.0))
    pose_2 = _cc_o()
    result = evaluate_pose_sequence("APD-001", reference, [pose_1, pose_2], [-1.0, -2.0])
    assert result.pose_1_rmsd_angstrom == pytest.approx(5.0)
    assert result.pose_1_success is False
    assert result.minimum_rmsd_angstrom == pytest.approx(0.0)
    assert result.best_pose_index == 2
    assert result.secondary_success is True

    twenty_one = evaluate_pose_sequence(
        "APD-001", reference, [reference] * 21, [-1.0] * 21
    )
    assert twenty_one.returned_pose_count == 21
    assert twenty_one.analyzed_pose_count == 20
    assert len(twenty_one.poses) == 20


def test_missing_vina_score_is_fail_closed() -> None:
    result = evaluate_pose_sequence(
        "APD-001",
        _cc_o(),
        [None],
        [None],
        score_parse_failed=True,
    )
    assert result.status == "INDETERMINATE"
    assert result.first_loss == "SCORE_PARSE_FAILED"
    assert result.poses[0].vina_score_kcal_mol is None


def test_threshold_is_inclusive_and_aggregation_keeps_denominators() -> None:
    at_threshold = evaluate_pose_sequence("APD-001", _cc_o(), [_cc_o((2.0, 0, 0))], [-1.0])
    indeterminate = evaluate_pose_sequence("APD-002", _cc_o(), [_molecule("CCN", [(0, 0, 0), (1, 0, 0), (2, 0, 0)])], [-1.0])
    cases = [at_threshold, indeterminate]
    for index in range(3, 11):
        cases.append(
            CaseAnalysis(
                case_id=f"APD-{index:03d}", status="INDETERMINATE",
                pose_1_rmsd_angstrom=None, minimum_rmsd_angstrom=None,
                best_pose_index=None, pose_1_success=None, secondary_success=None,
                returned_pose_count=0, analyzed_pose_count=0,
                first_loss="REFERENCE_COORDINATES_INCOMPLETE",
                first_loss_reason="fixture", failed_execution=False,
                score_parse_status="NOT_ATTEMPTED", reference={}, poses=(),
            )
        )
    aggregate = aggregate_case_analyses(cases)
    assert aggregate["primary"]["success_count"] == 1
    assert aggregate["primary"]["denominator"] == 1
    assert aggregate["primary"]["mean_over_determinate"] == pytest.approx(2.0)
    assert aggregate["primary"]["median_over_determinate"] == pytest.approx(2.0)
    assert aggregate["indeterminate_count"] == 9


def test_raw_seal_is_required_and_tamper_is_blocked(tmp_path: Path) -> None:
    protocol = load_and_validate_v102(PROTOCOL)
    run_root = _write_sealed_fixture(tmp_path)
    seal = verify_raw_results_seal(
        run_root,
        protocol_id=protocol["protocol_id"],
        protocol_hash=protocol["protocol_hash"],
        planned_run_id=PLANNED_RUN_ID,
    )
    assert seal.run_id.startswith("research-os.apodock001.run.v1+")

    manifest = json.loads((run_root / "run-manifest.json").read_text(encoding="utf-8"))
    manifest["raw_results_sealed"] = False
    (run_root / "run-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(AnalysisGateError, match="RAW_RESULTS_SEALED"):
        verify_raw_results_seal(
            run_root,
            protocol_id=protocol["protocol_id"],
            protocol_hash=protocol["protocol_hash"],
            planned_run_id=PLANNED_RUN_ID,
        )

    run_root = _write_sealed_fixture(tmp_path / "tampered-seal")
    seal_payload = json.loads((run_root / "raw-results-seal.json").read_text(encoding="utf-8"))
    seal_payload["raw_results_seal_sha256"] = "0" * 64
    (run_root / "raw-results-seal.json").write_text(json.dumps(seal_payload), encoding="utf-8")
    with pytest.raises(AnalysisGateError, match="raw result seal mismatch"):
        verify_raw_results_seal(
            run_root,
            protocol_id=protocol["protocol_id"],
            protocol_hash=protocol["protocol_hash"],
            planned_run_id=PLANNED_RUN_ID,
        )


def test_analyzer_preserves_raw_bytes_and_produces_deterministic_fixture_manifest(tmp_path: Path) -> None:
    run_root = _write_sealed_fixture(tmp_path)
    raw_before = {
        path: path.read_bytes()
        for path in (run_root / "raw").rglob("*.pdbqt")
    }
    first = analyze_sealed_run(
        protocol_path=PROTOCOL,
        bundle_root=BUNDLE,
        run_root=run_root,
        converter=_SyntheticPoseAdapter(),
        analysis_commit_sha="fixture-commit",
    )
    second = analyze_sealed_run(
        protocol_path=PROTOCOL,
        bundle_root=BUNDLE,
        run_root=run_root,
        converter=_SyntheticPoseAdapter(),
        analysis_commit_sha="fixture-commit",
    )
    assert first == second
    assert first["analysis_engine_id"] == ANALYSIS_ENGINE_ID
    assert first["aggregation"]["case_order"] == [f"APD-{index:03d}" for index in range(1, 11)]
    assert all(case["status"] == "INDETERMINATE" for case in first["aggregation"]["cases"])
    assert all(path.read_bytes() == content for path, content in raw_before.items())

    changed_metadata = analyze_sealed_run(
        protocol_path=PROTOCOL,
        bundle_root=BUNDLE,
        run_root=run_root,
        converter=_SyntheticPoseAdapter(),
        analysis_commit_sha="different-operational-commit",
    )
    assert changed_metadata["analysis_commit_sha"] != first["analysis_commit_sha"]
    assert changed_metadata["aggregation"] == first["aggregation"]


def test_raw_output_mutation_after_seal_is_blocked(tmp_path: Path) -> None:
    run_root = _write_sealed_fixture(tmp_path)
    raw_path = next((run_root / "raw").rglob("*.pdbqt"))
    raw_path.write_bytes(raw_path.read_bytes() + b"mutation")
    with pytest.raises(AnalysisGateError, match="raw result seal mismatch"):
        analyze_sealed_run(
            protocol_path=PROTOCOL,
            bundle_root=BUNDLE,
            run_root=run_root,
            converter=_SyntheticPoseAdapter(),
            analysis_commit_sha="fixture-commit",
        )


def test_reference_transform_hash_and_apd010_policy_are_frozen() -> None:
    protocol = load_and_validate_v102(PROTOCOL)
    apd001 = protocol["benchmark"]["cases"][0]
    reference = build_transformed_reference(protocol, BUNDLE, apd001)
    assert reference.failure_stage is None
    assert reference.metadata["transformed_holo_reference_coordinate_hash"] == apd001["transformed_holo_reference_coordinate_hash"]

    apd010 = protocol["benchmark"]["cases"][-1]
    incomplete = build_transformed_reference(protocol, BUNDLE, apd010)
    assert incomplete.molecule is None
    assert incomplete.failure_stage == "REFERENCE_COORDINATES_INCOMPLETE"
    assert "not substituted" in (incomplete.failure_reason or "")


def test_getbestrms_and_predicted_reference_kabsch_are_not_used(monkeypatch: pytest.MonkeyPatch) -> None:
    import research_os.docking.redocking as legacy

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("historical aligned RMSD must not be called")

    monkeypatch.setattr(legacy.rdMolAlign, "GetBestRMS", forbidden)
    monkeypatch.setattr(analysis, "kabsch_source_to_target", forbidden)
    result = same_frame_symmetry_aware_rmsd(_cc_o(), _cc_o((5.0, 0.0, 0.0)))
    assert result.rmsd_angstrom == pytest.approx(5.0)
    assert "GetBestRMS" not in Path(analysis.__file__).read_text(encoding="utf-8")
