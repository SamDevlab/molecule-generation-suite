from __future__ import annotations

from pathlib import Path

from research_os.molecular_discovery.moldisc007 import (
    COVERAGE_BOUNDARY,
    PROGRAM_ID,
    RANK1_RMSD_THRESHOLD_ANGSTROM,
    FallbackCandidate,
    load_program_config_v7,
    run_moldisc_007,
    select_operational_fallback,
)


CONFIG = Path("programs/moldisc-007-operational-fallback/program.json")


def test_moldisc_007_protocol_freezes_parent_and_selection_rule():
    config = load_program_config_v7(CONFIG)
    assert config["program_id"] == PROGRAM_ID
    assert config["program_version"] == "1.0"
    assert config["parent_evidence"]["moldisc_006_status"] == "CLOSED_INDETERMINATE_TARGET_PREPARATION"
    assert config["selection_rule"]["aqsoldb_eligibility_boundary"] == COVERAGE_BOUNDARY
    assert config["selection_rule"]["require_redock_rank_1_rmsd_lte_angstrom"] == RANK1_RMSD_THRESHOLD_ANGSTROM
    assert config["selection_rule"]["post_result_rule_changes_allowed"] is False


def test_frozen_fallback_rule_selects_atx007():
    config = load_program_config_v7(CONFIG)
    candidates = tuple(FallbackCandidate(**item) for item in config["candidates"])
    selection = select_operational_fallback(candidates)
    assert selection.selected_case_id == "ATX-007"
    assert selection.selected_pdb_id == "1KZK"
    assert selection.selected_chem_comp_id == "JE2"
    assert selection.eligible_case_ids == ("ATX-007",)


def test_selection_tie_breaks_by_case_id():
    candidates = (
        FallbackCandidate("ATX-020", "X", "A", "T", 0.5, 1.0, True, False, None),
        FallbackCandidate("ATX-019", "Y", "B", "T", 0.5, 1.0, True, False, None),
    )
    selection = select_operational_fallback(candidates)
    assert selection.selected_case_id == "ATX-019"
    assert selection.eligible_case_ids == ("ATX-019", "ATX-020")


def test_program_writes_auditable_selection_artifacts(tmp_path: Path):
    result = run_moldisc_007(config_path=CONFIG, output_root=tmp_path / "moldisc007")
    assert result.selection.selected_case_id == "ATX-007"
    assert len(result.program_scientific_hash) == 64
    root = tmp_path / "moldisc007"
    assert (root / "program_manifest.json").is_file()
    assert (root / "selection.json").is_file()
    assert (root / "program_report.md").is_file()
