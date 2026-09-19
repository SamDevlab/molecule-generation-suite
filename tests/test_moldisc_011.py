from __future__ import annotations

from pathlib import Path

import pytest

from research_os.molecular_discovery.moldisc011 import (
    COVERAGE_BOUNDARY,
    EXPECTED_PRODUCTS,
    GENERATOR_ID,
    PARENT_MOLDISC009_HASH,
    PARENT_MOLDISC010_HASH,
    SEED_INCHIKEY,
    SEED_SMILES,
    SecondDemethylProfile,
    VARIANT_IDS,
    _select_generated,
    generate_second_demethyl_series,
    load_program_config_v11,
)


CONFIG = Path("programs/moldisc-011-demethyl03-second-demethyl/program.json")


def _profile(variant_id: str, similarity: float, *, esol_status: str = "OUT_OF_DOMAIN"):
    return SecondDemethylProfile(
        candidate_id=f"CAND-{variant_id}",
        variant_id=variant_id,
        source_role="GENERATED",
        canonical_smiles="CC",
        inchikey="QGZKDVFQNNGYKY-UHFFFAOYSA-N",
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
        aqsoldb_top_neighbor_observation_count=1,
        aqsoldb_top_neighbor_measured_log_s_mol_l_median=-2.0,
        aqsoldb_top_neighbor_measured_log_s_mol_l_min=-2.0,
        aqsoldb_top_neighbor_measured_log_s_mol_l_max=-2.0,
        followup_eligible=similarity >= COVERAGE_BOUNDARY,
    )


def test_moldisc_011_protocol_freezes_parent_generation_selection_and_no_docking():
    config = load_program_config_v11(CONFIG)
    assert config["program_id"] == "MOLDISC-011"
    assert config["parent_program"]["program_scientific_hash"] == PARENT_MOLDISC009_HASH
    assert config["moldisc010_evidence"]["program_scientific_hash"] == PARENT_MOLDISC010_HASH
    assert config["seed"]["canonical_smiles"] == SEED_SMILES
    assert config["seed"]["inchikey"] == SEED_INCHIKEY
    assert config["generation"]["generator_id"] == GENERATOR_ID
    assert config["generation"]["expected_seed_terminal_methyl_sites"] == 3
    assert config["generation"]["expected_unique_generated_candidates"] == 2
    assert tuple(config["generation"]["variant_ids_in_sorted_product_order"]) == VARIANT_IDS
    assert config["evidence"]["esol_used_for_selection"] is False
    assert config["evidence"]["moldisc010_score_used_for_generation"] is False
    assert config["evidence"]["moldisc010_score_used_for_selection"] is False
    assert config["evidence"]["docking_executed"] is False


def test_generator_enumerates_three_raw_sites_and_two_exact_unique_products():
    pytest.importorskip("rdkit")
    analogs = generate_second_demethyl_series()
    assert tuple(item.variant_id for item in analogs) == VARIANT_IDS
    assert sum(len(item.removed_seed_atom_indices) for item in analogs) == 3
    assert len(analogs) == 2
    assert [item.smiles for item in analogs] == [item["smiles"] for item in EXPECTED_PRODUCTS]
    assert [item.inchikey for item in analogs] == [item["inchikey"] for item in EXPECTED_PRODUCTS]
    assert sorted(len(item.removed_seed_atom_indices) for item in analogs) == [1, 2]
    assert all(item.evidence_level == "E0_HEURISTIC" for item in analogs)
    assert all(item.operation == "delete_one_terminal_methyl" for item in analogs)


def test_selection_uses_aqsoldb_coverage_not_esol_or_docking():
    selection = _select_generated(
        (
            _profile("STEP2-DEMETHYL-01", 0.51, esol_status="IN_DOMAIN"),
            _profile("STEP2-DEMETHYL-02", 0.63, esol_status="OUT_OF_DOMAIN"),
        )
    )
    assert selection.selected_variant_id == "STEP2-DEMETHYL-02"
    assert selection.selected_nearest_similarity == pytest.approx(0.63)
    assert selection.eligible_generated_candidate_ids == (
        "CAND-STEP2-DEMETHYL-02",
        "CAND-STEP2-DEMETHYL-01",
    )
    assert selection.to_dict()["selection_used_esol"] is False
    assert selection.to_dict()["moldisc010_score_used_for_selection"] is False
    assert selection.to_dict()["docking_executed"] is False


def test_selection_returns_none_when_coverage_gate_is_not_met():
    selection = _select_generated((_profile("STEP2-DEMETHYL-01", 0.39), _profile("STEP2-DEMETHYL-02", 0.20)))
    assert selection.selected_candidate_id is None
    assert selection.eligible_generated_candidate_ids == ()
