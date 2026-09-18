from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_os.molecular_discovery.generation import (
    GENERATOR_ID,
    generate_halogen_analogs,
)
from research_os.molecular_discovery.moldisc001 import (
    PROGRAM_ID,
    load_program_config,
    run_moldisc_001,
)
from research_os.molecular_discovery.solubility import SolubilityPrediction


CONFIG = Path("programs/moldisc-001-id5/program.json")


class FakePredictor:
    def predict(self, smiles: str) -> SolubilityPrediction:
        score = -1.0 - (len(smiles) % 7) / 10.0
        return SolubilityPrediction(
            smiles=smiles,
            predicted_log_s_mol_l=score,
            max_training_tanimoto=0.75,
            applicability_threshold=0.26,
            in_domain=True,
        )

    def evidence_manifest(self):
        return {
            "model_identity": "test-frozen-esol",
            "evidence_level": "E1_ML",
        }


def test_moldisc_001_protocol_identity_is_frozen():
    config = load_program_config(CONFIG)
    assert config["program_id"] == PROGRAM_ID
    assert config["target"]["pdb_id"] == "1T40"
    assert config["seed"]["pdb_chem_comp_id"] == "ID5"
    assert config["seed"]["inchi_key"] == "ZCAGEXZTORJQDZ-UHFFFAOYSA-N"
    assert config["generation"]["generator_id"] == GENERATOR_ID
    assert config["target"]["docking_execution_in_program_v1"] is False


def test_id5_generator_produces_deterministic_single_halogen_neighborhood():
    pytest.importorskip("rdkit")
    config = load_program_config(CONFIG)
    report = generate_halogen_analogs(
        config["seed"]["smiles"],
        seed_id="MOLDISC-001-ID5",
        max_candidates=config["generation"]["max_candidates"],
    )
    assert report.candidate_count == 8
    assert len({candidate.smiles for candidate in report.candidates}) == 8
    assert all(candidate.evidence_level == "E0_HEURISTIC" for candidate in report.candidates)
    assert all(candidate.from_element == "F" for candidate in report.candidates)
    assert {candidate.to_element for candidate in report.candidates} == {"Cl", "Br"}
    assert len(report.scientific_hash) == 64


def test_moldisc_001_runs_seed_plus_generated_candidates_without_automatic_docking(tmp_path: Path):
    pytest.importorskip("rdkit")
    result = run_moldisc_001(
        config_path=CONFIG,
        output_root=tmp_path / "program",
        predictor=FakePredictor(),
    )
    assert result.program_id == PROGRAM_ID
    assert result.candidate_count == 9
    assert result.generation.candidate_count == 8
    assert len(result.program_scientific_hash) == 64

    candidates = result.discovery_report.candidates
    assert len(candidates) == 9
    assert all(candidate.chemistry_status == "PASS" for candidate in candidates)
    assert all(candidate.solubility_status == "IN_DOMAIN" for candidate in candidates)
    assert all(candidate.docking_status == "NOT_REQUESTED" for candidate in candidates)

    seed = next(candidate for candidate in candidates if candidate.candidate_id == "MOLDISC-001-SEED-ID5")
    assert seed.origin["source_type"] == "curated_crystallographic_ligand"
    generated = [candidate for candidate in candidates if candidate.candidate_id != seed.candidate_id]
    assert all(candidate.origin["evidence_level"] == "E0_HEURISTIC" for candidate in generated)
    assert all(candidate.origin["generator_id"] == GENERATOR_ID for candidate in generated)

    root = tmp_path / "program"
    assert (root / "program_manifest.json").is_file()
    assert (root / "generation.json").is_file()
    assert (root / "program_report.md").is_file()
    assert (root / "workflow" / "manifest.json").is_file()

    manifest = json.loads((root / "program_manifest.json").read_text(encoding="utf-8"))
    assert manifest["candidate_count"] == 9
    assert manifest["target"]["future_analog_docking_context"] == "NON_COGNATE_HOLO_CROSSDOCKING"
