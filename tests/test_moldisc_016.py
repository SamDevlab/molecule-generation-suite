from __future__ import annotations

from pathlib import Path

import pytest

from research_os.molecular_discovery.moldisc016 import (
    ANALYSIS_CONDITIONS,
    CANDIDATES,
    EXPECTED_DOCKING_RUNS,
    contact_residues,
    factorial_contrasts,
    build_execution_plan,
    load_program_config_v16,
    receptor_frame_rmsd,
    sign_consistent,
    _summary_matrix,
)


CONFIG = Path("programs/moldisc-016-je2-source-megacampaign/program.json")


def test_frozen_program_loads_with_four_candidates_and_eight_campaigns() -> None:
    config = load_program_config_v16(CONFIG)
    assert config["program_id"] == "MOLDISC-016"
    assert len(config["panel"]) == 4
    assert len(config["campaigns"]) == 8
    assert config["resource_bounds"]["planned_docking_runs"] == EXPECTED_DOCKING_RUNS
    assert config["boundaries"]["generation_executed"] is False
    assert config["boundaries"]["candidate_selection_executed"] is False
    assert config["boundaries"]["lead_selection_executed"] is False


def test_execution_plan_is_exactly_four_by_eight_and_isolation_is_frozen() -> None:
    plan = build_execution_plan(load_program_config_v16(CONFIG))
    assert len(plan) == EXPECTED_DOCKING_RUNS
    assert len({item["run_id"] for item in plan}) == EXPECTED_DOCKING_RUNS
    assert [sum(item["campaign_id"] == campaign for item in plan) for campaign in ("CAMP-016-A", "CAMP-016-B", "CAMP-016-C", "CAMP-016-D")] == [8, 8, 8, 8]
    assert {item["vina_seed"] for item in plan if item["campaign_id"] == "CAMP-016-B"} == {1337, 2025}
    assert all(item["etkdg_seed"] == 42 and item["exhaustiveness"] == 16 for item in plan if item["campaign_id"] == "CAMP-016-B")
    assert {item["etkdg_seed"] for item in plan if item["campaign_id"] == "CAMP-016-C"} == {1337, 2025}
    assert all(item["vina_seed"] == 42 and item["exhaustiveness"] == 16 for item in plan if item["campaign_id"] == "CAMP-016-C")
    assert {item["exhaustiveness"] for item in plan if item["campaign_id"] == "CAMP-016-D"} == {8, 32}
    assert all(item["vina_seed"] == 42 and item["etkdg_seed"] == 42 for item in plan if item["campaign_id"] == "CAMP-016-D")
    assert ANALYSIS_CONDITIONS == ("baseline", "vina_seed_1337", "vina_seed_2025", "etkdg_seed_1337", "etkdg_seed_2025", "exhaustiveness_8", "exhaustiveness_32")
    assert len(CANDIDATES) == 4


def test_factorial_formulas_and_sign_consistency_are_descriptive() -> None:
    assert factorial_contrasts(1.0, 3.0, 2.0, 7.0) == {
        "vina_rank1_score_oh_contrast": 3.5,
        "vina_rank1_score_nsub_contrast": 2.5,
        "vina_rank1_score_interaction_contrast": 3.0,
    }
    assert sign_consistent([-1.0, -2.0, -0.5]) is True
    assert sign_consistent([-1.0, 0.0]) is False
    assert sign_consistent([]) is False


def test_receptor_frame_rmsd_does_not_remove_translation() -> None:
    left = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]
    assert receptor_frame_rmsd(left, left) == pytest.approx(0.0)
    assert receptor_frame_rmsd(left, [(1.0, 0.0, 0.0), (2.0, 0.0, 0.0)]) == pytest.approx(1.0)


def test_contacts_use_four_angstrom_heavy_atom_boundary() -> None:
    receptor = [{"chain": "A", "residue_name": "TYR", "residue_sequence": "10", "insertion_code": "", "x": 0.0, "y": 0.0, "z": 0.0}]
    assert len(contact_residues([(3.9, 0.0, 0.0)], receptor)) == 1
    assert len(contact_residues([(4.0, 0.0, 0.0)], receptor)) == 1
    assert contact_residues([(4.1, 0.0, 0.0)], receptor) == []


def test_contextual_summary_matrix_matches_moldisc_014_source_profiles() -> None:
    candidates = {candidate.key: candidate for candidate in CANDIDATES}
    records = {
        f"{key}__baseline__RUN_A": {"technical_status": "PASS", "pose_count": 20, "pose_1_score_kcal_mol": -9.0}
        for key in candidates
    }
    rows = _summary_matrix(records, candidates)
    assert [(row["factor_A"], row["factor_B"], row["source_connectivity_match"], row["ESOL_status"]) for row in rows] == [
        ("A0", "B0", False, "OUT_OF_DOMAIN"),
        ("A1", "B0", False, "IN_DOMAIN"),
        ("A0", "B1", False, "OUT_OF_DOMAIN"),
        ("A1", "B1", True, "OUT_OF_DOMAIN"),
    ]
