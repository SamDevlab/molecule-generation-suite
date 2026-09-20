from __future__ import annotations

from pathlib import Path

import numpy as np
from rdkit import Chem

from research_os.molecular_discovery import moldisc017


CONFIG = Path("programs/moldisc-017-hiv-protease-receptor-state/program.json")


def test_program_config_is_frozen_and_exactly_36_runs():
    config = moldisc017.load_program_config_v17(CONFIG)
    plan = moldisc017.build_execution_plan(config)
    assert len(plan) == 36
    assert [item["campaign_id"] for item in plan[:4]] == ["CAMP-017-B"] * 4
    assert sum(item["campaign_id"] == "CAMP-017-C" for item in plan) == 16
    assert sum(item["campaign_id"] == "CAMP-017-D" for item in plan) == 16
    assert all(item["receptor"] in {"R1", "R2"} for item in plan)


def test_k57_is_context_only_and_r0_is_not_rerun():
    config = moldisc017.load_program_config_v17(CONFIG)
    assert config["target_panel"]["R0"]["rerun"] is False
    assert config["native_context_only"]["docking_allowed"] is False
    assert config["native_context_only"]["K57_WT"]["expected_inchikey"] == moldisc017.K57_INCHIKEY
    assert config["native_context_only"]["K57_MUTANT"]["formula"] == moldisc017.K57_FORMULA


def test_strict_mcs_expected_program_edges():
    manifest = moldisc017.strict_mcs_manifest()
    assert {key: value["num_atoms"] for key, value in manifest["edges"].items()} == moldisc017.MCS_EXPECTED
    assert manifest["rule_id"] == "STRICT_MAXIMUM_COMMON_HEAVY_ATOM_SUBSTRUCTURE"


def test_factorial_formulas_and_sign_consistency():
    values = moldisc017.factorial_contrasts(-10.0, -9.0, -8.0, -7.0)
    assert values == {"oh": 1.0, "nsub": 2.0, "interaction": 0.0}
    assert moldisc017.sign_consistent([1.0, 2.0, 3.0])
    assert not moldisc017.sign_consistent([1.0, -2.0, 3.0])


def test_kabsch_synthetic_rotation_translation():
    reference = np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    rotation = np.asarray([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    translation = np.asarray([2.0, -3.0, 1.5])
    moving = (rotation.T @ (reference - translation).T).T
    result = moldisc017.kabsch_align(reference.tolist(), moving.tolist())
    assert result["atom_count"] == 4
    assert result["rmsd_angstrom"] < 1e-10


def test_source_fixtures_are_frozen():
    config = moldisc017.load_program_config_v17(CONFIG)
    assert config["target_panel"]["R1"]["mutations"] == ["Q7K", "L33I", "L63I"]
    assert config["target_panel"]["R2"]["mutations"] == ["Q7K", "L33I", "L63I", "V82F", "I84V"]
    assert config["target_panel"]["R1"]["native_ligand_inchikey"] == moldisc017.JE2_INCHIKEY
    assert config["target_panel"]["R2"]["native_ligand_inchikey"] == moldisc017.JE2_INCHIKEY


def test_no_new_molecule_generation_or_selection_is_encoded():
    config = moldisc017.load_program_config_v17(CONFIG)
    assert all(config["boundaries"][key] is False for key in ("generation_executed", "candidate_selection_executed", "lead_selection_executed", "measurement_transfer_allowed", "winner_created", "universal_metric_created"))
    assert config["native_context_only"]["experimental_activity_transfer_allowed"] is False
