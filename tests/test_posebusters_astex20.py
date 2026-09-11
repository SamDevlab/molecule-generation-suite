from __future__ import annotations

from copy import deepcopy

import pytest

import research_os.docking.posebusters_astex20 as pb002
from research_os.docking.posebusters_astex20 import (
    EXPECTED_CASE_IDS,
    EXPECTED_SOURCE_LOCALIZED,
    EXPECTED_SOURCE_TOTAL,
    SOURCE_BENCHMARK_ID,
    SOURCE_EVALUATOR_PROTOCOL_ID,
    SOURCE_PROTOCOL_ID,
    SOURCE_SCIENTIFIC_RESULT_HASH,
    verify_source_report,
)


def _source_report() -> dict[str, object]:
    return {
        "benchmark_id": SOURCE_BENCHMARK_ID,
        "protocol_id": SOURCE_PROTOCOL_ID,
        "evaluator_protocol_id": SOURCE_EVALUATOR_PROTOCOL_ID,
        "scientific_result_hash": SOURCE_SCIENTIFIC_RESULT_HASH,
        "records": [
            {"result": {"case_id": case_id, "pose_1_rmsd_angstrom": 1.0}}
            for case_id in EXPECTED_CASE_IDS
        ],
        "summary": {
            "pose_1_rmsd_le_2_angstrom": {
                "count": EXPECTED_SOURCE_LOCALIZED,
                "denominator": EXPECTED_SOURCE_TOTAL,
            }
        },
    }


@pytest.fixture(autouse=True)
def _mock_recomputed_hash_for_metadata_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pb002,
        "redock_scientific_result_hash",
        lambda report: SOURCE_SCIENTIFIC_RESULT_HASH,
    )


def test_sealed_redock003_source_is_accepted() -> None:
    records = verify_source_report(_source_report())
    assert len(records) == 15
    assert tuple(record["result"]["case_id"] for record in records) == EXPECTED_CASE_IDS


def test_wrong_scientific_hash_is_rejected() -> None:
    report = _source_report()
    report["scientific_result_hash"] = "0" * 64
    with pytest.raises(RuntimeError, match="scientific identity mismatch"):
        verify_source_report(report)


def test_recomputed_scientific_content_hash_must_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _source_report()
    monkeypatch.setattr(pb002, "redock_scientific_result_hash", lambda report: "0" * 64)
    with pytest.raises(RuntimeError, match="scientific content hash mismatch"):
        verify_source_report(report)


def test_case_identity_or_order_change_is_rejected() -> None:
    report = _source_report()
    records = list(report["records"])
    records[0], records[1] = records[1], records[0]
    report["records"] = records
    with pytest.raises(RuntimeError, match="case identity/order mismatch"):
        verify_source_report(report)


def test_source_localization_count_is_frozen_at_eight_of_fifteen() -> None:
    report = deepcopy(_source_report())
    report["summary"]["pose_1_rmsd_le_2_angstrom"]["count"] = 9
    with pytest.raises(RuntimeError, match="localization count mismatch"):
        verify_source_report(report)


def test_source_denominator_is_frozen_at_fifteen() -> None:
    report = deepcopy(_source_report())
    report["summary"]["pose_1_rmsd_le_2_angstrom"]["denominator"] = 14
    with pytest.raises(RuntimeError, match="denominator mismatch"):
        verify_source_report(report)
