from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from research_os.molecular_discovery import moldisc019


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "programs" / "moldisc-019-experimental-bridge" / "program.json"
PACKAGE = ROOT / "experimental_packages" / "biolab-physical-loop-0"


def test_program_parent_and_panel_contract_are_frozen() -> None:
    config = moldisc019.load_program_config_v19(CONFIG)
    assert config["program_id"] == "MOLDISC-019"
    assert config["parents"]["moldisc018"]["program_scientific_hash"] == moldisc019.PARENT_MOLDISC018_HASH
    assert config["panel"]["member_count"] == 4
    assert set(config["panel"]["members"]) == {"A0B0", "A1B0", "A0B1", "A1B1"}
    assert config["boundaries"]["new_docking_runs"] == 0
    assert config["boundaries"]["molecule_generation_executed"] is False


def test_package_has_exactly_four_compounds_and_no_selection_language() -> None:
    panel = json.loads((PACKAGE / "panel_manifest.json").read_text(encoding="utf-8"))
    assert panel["member_count"] == 4
    assert [item["panel_key"] for item in panel["members"]] == ["A0B0", "A1B0", "A0B1", "A1B1"]
    forbidden = {"lead", "winner", "predicted_best", "expected_to_work", "recommended"}
    for path in (PACKAGE / "compounds").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert not forbidden.intersection(data)
        assert data["source_measurement_transfer_allowed"] is False


def test_first_decision_artifact_is_closed_and_experiment_first() -> None:
    decision = moldisc019.build_first_decision()
    assert decision["CURRENT_PROGRAM"] == "MOLDISC-018"
    assert decision["CURRENT_MAX_LOCAL_EVIDENCE"] == "E2_COMPUTATIONAL"
    assert decision["TARGET_GAP"] == "GAP-EXPERIMENTAL-SOLUBILITY"
    assert decision["REQUIRED_EVIDENCE"] == "E4_CURATED_EXPERIMENTAL"
    assert decision["SELECTED_ACTION"] == "EXPERIMENT"
    assert decision["COMPUTATIONAL_CONTINUATION_ALLOWED"] is False
    assert decision["STOP_REASON"] == "EXPERIMENTAL_VALIDATION_REQUIRED"


def test_prepare_and_status_are_non_experimental() -> None:
    prepared = moldisc019.prepare_package(CONFIG, PACKAGE)
    status = moldisc019.package_status(PACKAGE)
    assert prepared["real_experiment_executed"] is False
    assert prepared["e4_created"] is False
    assert status["status"] == "AWAITING_EXTERNAL_PROTOCOL_OR_QUOTE"
    assert status["physical_loop_state"] == "AWAITING_EXTERNAL_PROTOCOL"


def test_result_validation_requires_all_gates_and_ingestion_is_fail_closed() -> None:
    fixture = json.loads((PACKAGE / "external_result_example_TEST_SYNTHETIC.json").read_text(encoding="utf-8"))
    validation = moldisc019.validate_result(fixture, PACKAGE)
    assert validation["eligible_for_e4"] is False
    with pytest.raises(moldisc019.MOLDISC019Error):
        moldisc019.ingest_result(fixture, PACKAGE)


def test_eligible_result_creates_update_and_recomputes_state() -> None:
    result = json.loads((PACKAGE / "external_result_example_TEST_SYNTHETIC.json").read_text(encoding="utf-8"))
    result.update(
        {
            "actual_experiment": True,
            "synthetic": False,
            "evidence_classification": "E4_CURATED_EXPERIMENTAL",
            "fixture_classification": "EXTERNAL_RESULT",
            "sample_identity_method": "InChIKey",
            "protocol_status": "FROZEN",
            "protocol_hash": "a" * 64,
            "provenance": {"classification": "EXTERNAL_RESULT", "source": "contract-test"},
            "raw_artifacts": ["official-report.pdf"],
            "raw_artifact_hashes": ["b" * 64],
            "report_file": "official-report.pdf",
            "report_hash": "c" * 64,
        }
    )
    validation = moldisc019.validate_result(result, PACKAGE)
    assert validation["eligible_for_e4"] is True
    ingested = moldisc019.ingest_result(result, PACKAGE)
    assert ingested["evidence_level"] == "E4_CURATED_EXPERIMENTAL"
    assert ingested["e5_created"] is False
    assert ingested["update"]["affected_gap_ids"] == ["GAP-EXPERIMENTAL-SOLUBILITY"]
    assert ingested["updated_state"]["experiment_status"] == "E4_RESULT_INGESTED"
    assert ingested["recomputed_decision"]["target_gap"] != "GAP-EXPERIMENTAL-SOLUBILITY"


def test_first_run_record_contains_no_experiment() -> None:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as temporary:
        result = moldisc019.record_first_run(CONFIG, PACKAGE, temporary)
        assert result["real_experiment_executed"] is False
        assert result["new_docking_runs"] == 0
        assert result["new_molecules_generated"] == 0
        assert (Path(temporary) / "biolab-loop-v0.1-first-decision.json").is_file()
        assert (Path(temporary) / "moldisc-019-first-run-v1.json").is_file()
