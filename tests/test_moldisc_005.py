from __future__ import annotations

from pathlib import Path

import pytest

from research_os.molecular_discovery.moldisc005 import (
    COVERAGE_BOUNDARY,
    GENERATOR_ID,
    AnalogEvidenceProfile,
    _select_generated,
    generate_nct_n_alkyl_series,
    load_program_config_v5,
)


CONFIG = Path("programs/moldisc-005-nct-nalkyl-series/program.json")


def _profile(variant_id: str, similarity: float, *, role: str = "GENERATED", chemistry: str = "PASS"):
    return AnalogEvidenceProfile(
        candidate_id=f"ID-{variant_id}",
        variant_id=variant_id,
        source_role=role,
        smiles="CCO",
        chemistry_status=chemistry,
        esol_status="IN_DOMAIN",
        predicted_log_s_mol_l=-1.0,
        esol_max_training_tanimoto=0.5,
        aqsoldb_nearest_similarity=similarity,
        aqsoldb_similarity_bin="[0.4,0.6)" if similarity >= 0.4 else "[0.0,0.4)",
        aqsoldb_neighbors_ge_0_4=int(similarity >= 0.4),
        aqsoldb_top_neighbor_smiles="CCO",
        aqsoldb_top_neighbor_measured_log_s_mol_l=-0.5,
        followup_eligible=(role == "GENERATED" and chemistry == "PASS" and similarity >= 0.4),
    )


def test_moldisc_005_protocol_freezes_variants_and_disables_esol_selection():
    config = load_program_config_v5(CONFIG)
    assert config["program_id"] == "MOLDISC-005"
    assert config["generation"]["generator_id"] == GENERATOR_ID
    assert [item["variant_id"] for item in config["generation"]["frozen_variants"]] == [
        "N-H",
        "N-ETHYL",
        "N-PROPYL",
    ]
    assert config["solubility_evidence"]["aqsoldb_coverage_boundary"] == COVERAGE_BOUNDARY
    assert config["solubility_evidence"]["esol_absolute_ranking_allowed"] is False
    assert config["generated_analog_followup_rule"]["esol_prediction_used_for_selection"] is False
    assert config["docking"]["execute_in_v1"] is False


def test_nct_n_alkyl_generator_produces_three_unique_e0_analogs():
    pytest.importorskip("rdkit")
    analogs = generate_nct_n_alkyl_series()
    assert [item.variant_id for item in analogs] == ["N-H", "N-ETHYL", "N-PROPYL"]
    assert len({item.smiles for item in analogs}) == 3
    assert len({item.inchikey for item in analogs}) == 3
    assert all(item.evidence_level == "E0_HEURISTIC" for item in analogs)
    assert all(item.generator_id == GENERATOR_ID for item in analogs)
    assert all(len(item.generation_hash) == 64 for item in analogs)


def test_followup_selection_uses_aqsoldb_coverage_not_esol_prediction():
    profiles = (
        _profile("N-H", 0.45),
        _profile("N-ETHYL", 0.70),
        _profile("N-PROPYL", 0.55),
        _profile("N-METHYL-SEED", 1.0, role="SEED"),
    )
    selection = _select_generated(profiles)
    assert selection.selected_variant_id == "N-ETHYL"
    assert selection.selected_nearest_similarity == pytest.approx(0.70)
    assert selection.eligible_generated_candidate_ids == (
        "ID-N-ETHYL",
        "ID-N-PROPYL",
        "ID-N-H",
    )


def test_followup_selection_closes_when_generated_analogs_lack_coverage():
    profiles = (
        _profile("N-H", 0.39),
        _profile("N-ETHYL", 0.20),
        _profile("N-PROPYL", 0.10),
        _profile("N-METHYL-SEED", 1.0, role="SEED"),
    )
    selection = _select_generated(profiles)
    assert selection.selected_candidate_id is None
    assert selection.eligible_generated_candidate_ids == ()
