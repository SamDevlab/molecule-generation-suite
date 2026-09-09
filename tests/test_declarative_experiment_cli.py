from __future__ import annotations

import json
from pathlib import Path

from research_os.cli import main


REFERENCE_PROTOCOL = "examples/experiments/reference-regression.yaml"


def _last_json(capsys) -> dict:
    output = capsys.readouterr().out
    return json.loads(output)


def test_cli_runs_and_verifies_declarative_experiment(tmp_path: Path, capsys) -> None:
    output = tmp_path / "runs"
    assert main(["run", "experiment", REFERENCE_PROTOCOL, "--output", str(output)]) == 0
    run_payload = _last_json(capsys)
    run_root = run_payload["root"]
    assert run_payload["experiment_id"] == "REFERENCE-REGRESSION-001"

    assert main(["run", "experiment-verify", run_root]) == 0
    verification = _last_json(capsys)
    assert verification["status"] == "PASS"
    assert verification["scientific_result_hash"] == run_payload["scientific_result_hash"]


def test_cli_inspects_and_compares_identical_runs(tmp_path: Path, capsys) -> None:
    assert main(["run", "experiment", REFERENCE_PROTOCOL, "--output", str(tmp_path / "left")]) == 0
    left = _last_json(capsys)
    assert main(["run", "experiment", REFERENCE_PROTOCOL, "--output", str(tmp_path / "right")]) == 0
    right = _last_json(capsys)

    assert main(["run", "experiment-inspect", left["root"]]) == 0
    inspected = _last_json(capsys)
    assert inspected["verification"]["status"] == "PASS"
    assert inspected["scientific_result_hash"] == left["scientific_result_hash"]

    assert main(["run", "experiment-compare", left["root"], right["root"]]) == 0
    compared = _last_json(capsys)
    assert compared["compatible"] is True
    assert compared["same_scientific_result"] is True


def test_cli_delegates_existing_commands_to_preserved_cli(capsys) -> None:
    assert main(["labs"]) == 0
    payload = _last_json(capsys)
    assert "labs" in payload
