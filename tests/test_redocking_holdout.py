from research_os.docking.redocking import FROZEN_REDOCKING_CASES
from research_os.docking.redocking_holdout import (
    BENCHMARK_ID,
    FROZEN_HOLDOUT_CASES,
    POSE_SUCCESS_THRESHOLD_ANGSTROM,
    PROTOCOL_ID,
    SOURCE_SET,
)


def test_redock_002_identity_is_frozen():
    assert BENCHMARK_ID == "REDOCK-002"
    assert PROTOCOL_ID == "research-os.redocking.holdout.v1.0"
    assert SOURCE_SET == "Astex Diverse Set"
    assert POSE_SUCCESS_THRESHOLD_ANGSTROM == 2.0


def test_redock_002_cases_are_exactly_frozen():
    assert [
        (
            case.case_id,
            case.pdb_id,
            case.ligand_id,
            case.ligand_author_chain,
            case.receptor_author_chains,
        )
        for case in FROZEN_HOLDOUT_CASES
    ] == [
        ("HLD-001", "1V0P", "PVB", "A", ("A",)),
        ("HLD-002", "1W1P", "GIO", "B", ("B",)),
        ("HLD-003", "2BM2", "PM2", "B", ("B",)),
        ("HLD-004", "1VCJ", "IBA", "A", ("A",)),
        ("HLD-005", "1TT1", "KAI", "A", ("A",)),
    ]


def test_redock_002_has_no_redock_001_complex_overlap():
    prior = {(case.pdb_id, case.ligand_id) for case in FROZEN_REDOCKING_CASES}
    holdout = {(case.pdb_id, case.ligand_id) for case in FROZEN_HOLDOUT_CASES}
    assert len(holdout) == 5
    assert prior.isdisjoint(holdout)


def test_redock_002_spans_distinct_targets():
    targets = {case.target for case in FROZEN_HOLDOUT_CASES}
    assert len(targets) == len(FROZEN_HOLDOUT_CASES)
