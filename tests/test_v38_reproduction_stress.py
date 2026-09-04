from __future__ import annotations

import pytest

from research_os.benchmark.reproduction import ReproductionCase, ReproductionStressBenchmark, ReproducibilityStatus, StressStatus, StressTestResult


def test_v38_contract_round_trip_ignores_report_extensions() -> None:
    case = ReproductionCase("R1", "RDKit", "original", "rerun", ReproducibilityStatus.REPRODUCED, "a" * 64, "b" * 64, {"python": "3.11"})
    stress = StressTestResult("STRESS-01", "sealed mutation", "blocked", "RunMutationError", StressStatus.PASS)
    benchmark = ReproductionStressBenchmark("v1", "research-os-v1.3", "commit", "start", "finish", (case,), (stress,), {"python_3_11": {"status": "PASS"}}, {"gate": True}, "PASS", "data only")
    payload = {**benchmark.to_dict(), "counts": {"reproduction_cases": 1}, "ledger": {"status": "PASS"}}
    restored = ReproductionStressBenchmark.from_dict(payload)
    assert restored.digest == benchmark.digest
    assert restored.reproduction_cases[0].status == ReproducibilityStatus.REPRODUCED
    assert restored.stress_tests[0].passed


def test_diverged_reproduction_requires_first_divergence() -> None:
    with pytest.raises(ValueError, match="first_divergence"):
        ReproductionCase("R2", "engine", "original", "rerun", "DIVERGED", "a" * 64, "b" * 64)
