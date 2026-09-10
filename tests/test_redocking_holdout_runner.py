from __future__ import annotations

from research_os.docking import redocking_holdout_runner as runner
from research_os.docking.redocking_holdout import FROZEN_HOLDOUT_CASES, PROTOCOL_ID
from research_os.docking.redocking_v12 import PROTOCOL_ID as EVALUATOR_PROTOCOL_ID


class _FakeEngine:
    executable = "/fake/engine"
    version = "fake-version"


def test_holdout_runner_reuses_v12_executor_and_preserves_all_cases(monkeypatch, tmp_path):
    seen: list[str] = []

    monkeypatch.setattr(runner, "VinaEngine", _FakeEngine)
    monkeypatch.setattr(runner, "OpenBabelEngine", _FakeEngine)

    def fake_run_redocking_case(case, workdir, *, vina, obabel):
        seen.append(case.case_id)
        value = 0.5 + 0.1 * len(seen)
        return {
            "case": case.to_dict(),
            "result": {
                "case_id": case.case_id,
                "status": "PASS",
                "pose_1_rmsd_angstrom": value,
                "minimum_rmsd_angstrom": value,
                "pose_count": 1,
                "vina_pose_1_score_kcal_mol": -7.0,
                "first_loss": None,
                "pose_1_success": True,
            },
            "provenance": {
                "protocol_id": EVALUATOR_PROTOCOL_ID,
                "docking": {"status": "SUPPORTED_AND_EXECUTED"},
            },
            "poses": [],
        }

    monkeypatch.setattr(runner.evaluator, "run_redocking_case", fake_run_redocking_case)

    report = runner.run_frozen_holdout_benchmark(tmp_path)

    assert seen == [case.case_id for case in FROZEN_HOLDOUT_CASES]
    assert report["protocol_id"] == PROTOCOL_ID
    assert report["evaluator_protocol_id"] == EVALUATOR_PROTOCOL_ID
    assert len(report["records"]) == 5
    assert report["summary"]["total_cases"] == 5
    assert report["summary"]["pose_1_rmsd_le_2_angstrom"]["denominator"] == 5
    assert (tmp_path / "redocking-holdout-result-v1.0.json").is_file()


def test_holdout_scientific_identity_does_not_depend_on_host_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "VinaEngine", _FakeEngine)
    monkeypatch.setattr(runner, "OpenBabelEngine", _FakeEngine)

    def fake_run_redocking_case(case, workdir, *, vina, obabel):
        return {
            "case": case.to_dict(),
            "result": {
                "case_id": case.case_id,
                "status": "PASS",
                "pose_1_rmsd_angstrom": 1.0,
                "minimum_rmsd_angstrom": 1.0,
                "pose_count": 1,
                "vina_pose_1_score_kcal_mol": -7.0,
                "first_loss": None,
                "pose_1_success": True,
            },
            "provenance": {"protocol_id": EVALUATOR_PROTOCOL_ID},
            "poses": [],
        }

    monkeypatch.setattr(runner.evaluator, "run_redocking_case", fake_run_redocking_case)
    first = runner.run_frozen_holdout_benchmark(tmp_path / "a")

    monkeypatch.setattr(runner.platform, "python_version", lambda: "9.9.9")
    monkeypatch.setattr(runner.platform, "platform", lambda: "different-host")
    second = runner.run_frozen_holdout_benchmark(tmp_path / "b")

    assert first["scientific_result_hash"] == second["scientific_result_hash"]
    assert first["execution_hash"] != second["execution_hash"]
