from research_os.docking import astex20
from research_os.docking.astex20_runner import (
    HISTORICAL_REDOCK_002_PASSING,
    HISTORICAL_REDOCK_002_TOTAL,
    _descriptive_astex20,
)


def test_astex20_preflight_evidence_identity_is_frozen():
    assert astex20.PREFLIGHT_RUN_ID == 34544166868
    assert astex20.PREFLIGHT_ARTIFACT_ID == 10178395083
    assert astex20.PREFLIGHT_ARTIFACT_SHA256 == (
        "56240b2eb1493190e7902ac26a026183a906d0e4a5b0f1068cdd43f185b62314"
    )
    assert astex20.PREFLIGHT_SELECTION_MANIFEST_HASH == (
        "8119f2ece8bd1be2612e74520871cbeddb5fa9be7951d23c88db478e122a1690"
    )


def test_astex20_exact_prospective_cohort_is_frozen():
    observed = [
        (
            case.case_id,
            case.pdb_id,
            case.ligand_id,
            case.ligand_author_chain,
            case.receptor_author_chains,
        )
        for case in astex20.FROZEN_PROSPECTIVE_CASES
    ]
    assert observed == [
        ("ATX-001", "1R1H", "BIR", "A", ("A",)),
        ("ATX-002", "1SJ0", "E4D", "A", ("A",)),
        ("ATX-003", "1MEH", "MOA", "A", ("A",)),
        ("ATX-004", "1V4S", "MRK", "A", ("A",)),
        ("ATX-005", "1T40", "ID5", "A", ("A",)),
        ("ATX-006", "1PMN", "984", "A", ("A",)),
        ("ATX-007", "1KZK", "JE2", "A", ("A", "B")),
        ("ATX-008", "1HQ2", "PH2", "A", ("A",)),
        ("ATX-009", "1S3V", "TQD", "A", ("A",)),
        ("ATX-010", "1Z95", "198", "A", ("A",)),
        ("ATX-011", "1UNL", "RRC", "A", ("A",)),
        ("ATX-012", "1TOW", "CRZ", "A", ("A",)),
        ("ATX-013", "1UOU", "CMU", "A", ("A",)),
        ("ATX-014", "1P2Y", "NCT", "A", ("A",)),
        ("ATX-015", "1L7F", "BCZ", "A", ("A",)),
    ]


def test_astex20_frozen_cohort_is_disjoint_from_historical_five():
    prospective = {f"{case.pdb_id}_{case.ligand_id}" for case in astex20.FROZEN_PROSPECTIVE_CASES}
    assert len(prospective) == 15
    assert prospective.isdisjoint(astex20.PRIOR_OBSERVED_ASTEX)


def test_astex20_rejections_are_pre_result_structural_only():
    assert [rank for rank, _, _ in astex20.PREFLIGHT_REJECTED_BEFORE_COHORT_FILLED] == [
        4, 5, 6, 7, 12, 15, 16, 17, 23
    ]
    assert all(reason == "multiple ligand instances" for _, _, reason in astex20.PREFLIGHT_REJECTED_BEFORE_COHORT_FILLED)


def test_descriptive_astex20_keeps_historical_and_prospective_denominators_explicit():
    assert HISTORICAL_REDOCK_002_PASSING == 2
    assert HISTORICAL_REDOCK_002_TOTAL == 5
    summary = _descriptive_astex20({"passing_rmsd_cases": 6, "total_cases": 15})
    assert summary["prospective_passing_rmsd_cases"] == 6
    assert summary["prospective_total_cases"] == 15
    assert summary["combined_passing_rmsd_cases"] == 8
    assert summary["combined_total_cases"] == 20
    assert summary["combined_fraction"] == 0.4
