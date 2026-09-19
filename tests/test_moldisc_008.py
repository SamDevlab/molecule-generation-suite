from __future__ import annotations

from pathlib import Path

import pytest

from research_os.molecular_discovery.aqsoldb_coverage import (
    AqSolDBNeighbor,
    CandidateCoverage,
)
from research_os.molecular_discovery.moldisc008 import (
    COVERAGE_BOUNDARY,
    EXPECTED_PARENT_PROGRAM_HASH,
    MOLDISC008Error,
    SEED_CANDIDATE_ID,
    _profile,
    load_program_config_v8,
)
from research_os.molecular_discovery.workflow import CandidateAssessment


CONFIG = Path("programs/moldisc-008-je2-evidence-profile/program.json")


def _assessment(*, chemistry="PASS", domain="IN_DOMAIN"):
    return CandidateAssessment(
        candidate_id=SEED_CANDIDATE_ID,
        smiles="CCO",
        name="JE2",
        origin={"source_type": "RCSB_crystallographic_chemical_component"},
        chemistry_status=chemistry,
        molecule_run_id="RUN-TEST",
        molecule_properties={},
        solubility_status=domain,
        solubility={
            "predicted_log_s_mol_l": -2.1,
            "max_training_tanimoto": 0.33,
            "applicability_threshold": 0.26684684684684684,
            "domain_status": domain,
        },
        docking_status="NOT_REQUESTED",
        docking=None,
        first_loss=None,
        priority_group="ELIGIBLE_FOR_REVIEW" if domain == "IN_DOMAIN" else "OUT_OF_DOMAIN",
        review_order=1,
    )


def _coverage(similarity=0.57):
    neighbor = AqSolDBNeighbor(
        similarity=similarity,
        canonical_smiles="CCN",
        inchikey="FAKE-NEIGHBOR",
        observation_count=2,
        median_measured_log_s_mol_l=-1.2,
        minimum_measured_log_s_mol_l=-1.4,
        maximum_measured_log_s_mol_l=-1.0,
        source_ids=("E-1", "E-2"),
    )
    return CandidateCoverage(
        candidate_id=SEED_CANDIDATE_ID,
        smiles="CCO",
        canonical_smiles="CCO",
        inchikey="FAKE-JE2",
        nearest_similarity=similarity,
        similarity_bin="[0.4,0.6)",
        neighbors_ge_0_4=3,
        neighbors_ge_0_6=0,
        neighbors_ge_0_8=0,
        top_neighbors=(neighbor,),
    )


def test_moldisc_008_protocol_freezes_je2_parent_and_no_generation():
    config = load_program_config_v8(CONFIG)
    assert config["program_id"] == "MOLDISC-008"
    assert config["parent_program"]["program_scientific_hash"] == EXPECTED_PARENT_PROGRAM_HASH
    assert config["seed"]["case_id"] == "ATX-007"
    assert config["seed"]["pdb_id"] == "1KZK"
    assert config["seed"]["chem_comp_id"] == "JE2"
    assert config["execution"]["molecule_generation"] is False
    assert config["execution"]["docking"] is False
    assert config["followup_gate"]["esol_in_domain_required"] is False


def test_profile_marks_source_ready_from_chemistry_and_coverage_not_esol_domain():
    profile = _profile(_assessment(domain="OUT_OF_DOMAIN"), _coverage(similarity=0.57))
    assert profile.generation_source_ready is True
    assert profile.esol_status == "OUT_OF_DOMAIN"
    assert profile.aqsoldb_nearest_similarity == pytest.approx(0.57)
    assert profile.exact_aqsoldb_match is False


def test_profile_closes_generation_readiness_below_coverage_boundary():
    profile = _profile(_assessment(domain="IN_DOMAIN"), _coverage(similarity=0.39))
    assert COVERAGE_BOUNDARY == 0.4
    assert profile.generation_source_ready is False


def test_profile_rejects_identity_mismatch():
    local = _coverage()
    mismatched = CandidateCoverage(
        candidate_id=local.candidate_id,
        smiles=local.smiles,
        canonical_smiles="CCN",
        inchikey=local.inchikey,
        nearest_similarity=local.nearest_similarity,
        similarity_bin=local.similarity_bin,
        neighbors_ge_0_4=local.neighbors_ge_0_4,
        neighbors_ge_0_6=local.neighbors_ge_0_6,
        neighbors_ge_0_8=local.neighbors_ge_0_8,
        top_neighbors=local.top_neighbors,
    )
    with pytest.raises(MOLDISC008Error, match="canonical structure identities differ"):
        _profile(_assessment(), mismatched)
