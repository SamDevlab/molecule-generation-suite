from __future__ import annotations

from pathlib import Path

import pytest

from research_os.molecular_discovery.moldisc009 import (
    COVERAGE_BOUNDARY,
    GENERATOR_ID,
    JE2AnalogProfile,
    PARENT_PROGRAM_HASH,
    SEED_INCHIKEY,
    SEED_SMILES,
    VARIANT_IDS,
    _select_generated,
    generate_je2_single_demethyl_series,
    load_program_config_v9,
)


CONFIG = Path("programs/moldisc-009-je2-demethyl-series/program.json")


def _profile(variant_id: str, similarity: float, *, esol_status: str = "OUT_OF_DOMAIN"):
    return JE2AnalogProfile(
        candidate_id=f"CAND-{variant_id}",
        variant_id=variant_id,
        source_role="GENERATED",
        smiles="CC",
        chemistry_status="PASS",
        esol_status=esol_status,
        predicted_log_s_mol_l=-9.0 if esol_status == "IN_DOMAIN" else -1.0,
        esol_max_training_tanimoto=0.9 if esol_status == "IN_DOMAIN" else 0.1,
        aqsoldb_nearest_similarity=similarity,
        aqsoldb_similarity_bin="[0.4,0.6)",
        aqsoldb_neighbors_ge_0_4=1,
        aqsoldb_neighbors_ge_0_6=0,
        aqsoldb_neighbors_ge_0_8=0,
        exact_aqsoldb_match=False,
        aqsoldb_top_neighbor_smiles="CCC",
        aqsoldb_top_neighbor_inchikey="NEIGHBOR",
        aqsoldb_top_neighbor_measured_log_s_mol_l=-2.0,
        followup_eligible=similarity >= COVERAGE_BOUNDARY,
    )


def test_moldisc_009_protocol_freezes_parent_seed_generation_and_no_docking():
    config = load_program_config_v9(CONFIG)
    assert config["program_id"] == "MOLDISC-009"
    assert config["parent_program"]["program_scientific_hash"] == PARENT_PROGRAM_HASH
    assert config["seed"]["canonical_smiles"] == SEED_SMILES
    assert config["seed"]["inchikey"] == SEED_INCHIKEY
    assert config["generation"]["generator_id"] == GENERATOR_ID
    assert config["generation"]["expected_seed_terminal_methyl_sites"] == 4
    assert config["generation"]["expected_unique_generated_candidates"] == 3
    assert tuple(config["generation"]["variant_ids_in_sorted_product_order"]) == VARIANT_IDS
    assert config["evidence"]["esol_used_for_selection"] is False
    assert config["evidence"]["docking_in_v1"] is False


def test_je2_generator_enumerates_complete_unique_single_terminal_methyl_deletions():
    pytest.importorskip("rdkit")
    analogs = generate_je2_single_demethyl_series()
    assert tuple(item.variant_id for item in analogs) == VARIANT_IDS
    assert len(analogs) == 3
    assert len({item.smiles for item in analogs}) == 3
    assert len({item.inchikey for item in analogs}) == 3
    assert all(item.evidence_level == "E0_HEURISTIC" for item in analogs)
    assert all(item.operation == "delete_one_terminal_methyl" for item in analogs)
    assert sorted(len(item.removed_seed_atom_indices) for item in analogs) == [1, 1, 2]


def test_selection_uses_aqsoldb_coverage_not_esol_status_or_numeric_prediction():
    profiles = (
        _profile("DEMETHYL-01", 0.51, esol_status="IN_DOMAIN"),
        _profile("DEMETHYL-02", 0.63, esol_status="OUT_OF_DOMAIN"),
        _profile("DEMETHYL-03", 0.39, esol_status="IN_DOMAIN"),
    )
    selection = _select_generated(profiles)
    assert selection.selected_variant_id == "DEMETHYL-02"
    assert selection.selected_nearest_similarity == pytest.approx(0.63)
    assert selection.eligible_generated_candidate_ids == (
        "CAND-DEMETHYL-02",
        "CAND-DEMETHYL-01",
    )


def test_selection_returns_none_when_measured_source_coverage_gate_is_not_met():
    selection = _select_generated((
        _profile("DEMETHYL-01", 0.39),
        _profile("DEMETHYL-02", 0.20),
    ))
    assert selection.selected_candidate_id is None
    assert selection.eligible_generated_candidate_ids == ()
