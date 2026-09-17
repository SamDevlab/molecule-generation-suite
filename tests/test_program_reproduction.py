from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from research_os.cli import main
from research_os.programs import (
    ResearchProgramStore,
    inspect_program_reproduction,
    reproduce_program_execution,
    verify_program_reproduction,
)
from research_os.programs.synthesis import synthesize_program

sys.path.insert(0, str(Path(__file__).parent))
from test_program_synthesis import _run_program  # noqa: E402


def _prepared_source(tmp_path: Path) -> Path:
    root, _ = _run_program(tmp_path / "source-input", directions={"a": "SUPPORTS", "b": "SUPPORTS"})
    synthesize_program(root)
    assert verify_program_reproduction(root).status == "FAIL"  # source is not a reproduction package
    return root


def test_reproduction_preserves_protocol_and_creates_new_execution_tree(tmp_path: Path) -> None:
    source = _prepared_source(tmp_path)
    target = tmp_path / "reproduction"

    source_before = {path.relative_to(source).as_posix(): path.read_bytes() for path in source.rglob("*") if path.is_file()}
    result = reproduce_program_execution(source, target)

    assert result["status"] == "SCIENTIFICALLY_EQUIVALENT"
    assert result["source_program_protocol_id"] == result["reproduced_program_protocol_id"]
    assert result["source_program_execution_id"] != result["reproduced_program_execution_id"]
    assert result["scientific_equivalence"] is True
    assert all(item["execution_identity_different"] for item in result["campaign_results"])
    assert result["source_synthesis_id"] != result["reproduced_synthesis_id"]
    assert verify_program_reproduction(target).status == "PASS"
    source_after = {path.relative_to(source).as_posix(): path.read_bytes() for path in source.rglob("*") if path.is_file()}
    assert source_after == source_before


def test_reproduction_record_survives_store_restart_and_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _prepared_source(tmp_path)
    target = tmp_path / "reproduction"
    assert main(["program", "reproduce", str(source), "--output", str(target)]) == 0
    result = json.loads(capsys.readouterr().out)

    store = ResearchProgramStore(target / "reproduced-program" / "program-store.sqlite3")
    restored = store.get_reproduction(result["reproduction_id"])
    store.close()
    assert restored == result
    assert main(["program", "reproduction-verify", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"
    assert main(["program", "reproduction-inspect", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["reproduction_id"] == result["reproduction_id"]
    assert inspect_program_reproduction(target)["verification"]["status"] == "PASS"


def test_source_mutation_is_fail_closed_and_target_is_not_overwritten(tmp_path: Path) -> None:
    source = _prepared_source(tmp_path)
    target = tmp_path / "reproduction"
    result = reproduce_program_execution(source, target)
    assert result["status"] == "SCIENTIFICALLY_EQUIVALENT"

    manifest_path = source / "program-manifest.json"
    original = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(original.replace('"scientific_status": "ASSESSED"', '"scientific_status": "TAMPERED"'), encoding="utf-8")
    blocked = reproduce_program_execution(source, tmp_path / "blocked")
    assert blocked["status"] == "BLOCKED"
    assert blocked["first_loss"] == "PROGRAM_REPRODUCTION_SOURCE_INVALID"
    assert verify_program_reproduction(tmp_path / "blocked").status == "PASS"
    manifest_path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="already exists"):
        reproduce_program_execution(source, target)


def test_dataset_mutation_blocks_before_reproduced_program_starts(tmp_path: Path) -> None:
    source = _prepared_source(tmp_path)
    dataset = tmp_path / "source-input" / "data.csv"
    dataset.write_text(dataset.read_text(encoding="utf-8") + "999,999,999\n", encoding="utf-8")

    blocked = reproduce_program_execution(source, tmp_path / "blocked")

    assert blocked["status"] == "BLOCKED"
    assert blocked["first_loss"] == "PROGRAM_REPRODUCTION_DATASET_IDENTITY_MISMATCH"
    assert not (tmp_path / "blocked" / "reproduced-program").exists()


def test_reproduction_verification_detects_target_record_tampering(tmp_path: Path) -> None:
    source = _prepared_source(tmp_path)
    target = tmp_path / "reproduction"
    reproduce_program_execution(source, target)

    record_path = target / "reproduction-manifest.json"
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    payload["scientific_equivalence"] = False
    record_path.write_text(json.dumps(payload), encoding="utf-8")

    verification = verify_program_reproduction(target)
    assert verification.status == "FAIL"
    assert verification.first_loss == "PROGRAM_REPRODUCTION_RECORD_INVALID"


def test_implementation_drift_blocks_before_child_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _prepared_source(tmp_path)
    import research_os.programs.reproduction as reproduction

    monkeypatch.setattr(reproduction, "_implementation_identity", lambda: {"sha256": "f" * 64})
    blocked = reproduce_program_execution(source, tmp_path / "blocked")

    assert blocked["status"] == "BLOCKED"
    assert blocked["first_loss"] == "PROGRAM_REPRODUCTION_IMPLEMENTATION_MISMATCH"
    assert not (tmp_path / "blocked" / "reproduced-program").exists()


def test_reproduction_hash_is_operationally_neutral(tmp_path: Path) -> None:
    source = _prepared_source(tmp_path)
    first = reproduce_program_execution(source, tmp_path / "one")
    second = reproduce_program_execution(source, tmp_path / "two")
    assert first["reproduction_id"] == second["reproduction_id"]
    assert first["reproduction_hash"] == second["reproduction_hash"]
    assert first["source_program_root"] != second["source_program_root"] or first["reproduced_program_root"] != second["reproduced_program_root"]
