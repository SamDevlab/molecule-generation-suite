from __future__ import annotations

from pathlib import Path

import pytest

from research_os.molecular_discovery.aqsoldb_coverage import CandidateCoverage
from research_os.molecular_discovery.moldisc003 import (
    ELIGIBILITY_BOUNDARY,
    RCSBChemicalIdentity,
    _select_seed,
    load_program_config_v3,
    parse_rcsb_chemcomp,
)


CONFIG = Path("programs/moldisc-003-redock-seed-coverage/program.json")


def _coverage(case_id: str, similarity: float) -> CandidateCoverage:
    return CandidateCoverage(
        candidate_id=case_id,
        smiles="CCO",
        canonical_smiles="CCO",
        inchikey="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
        nearest_similarity=similarity,
        similarity_bin=("[0.4,0.6)" if similarity >= 0.4 else "[0.0,0.4)"),
        neighbors_ge_0_4=int(similarity >= 0.4),
        neighbors_ge_0_6=0,
        neighbors_ge_0_8=0,
        top_neighbors=(),
    )


def _identity(case_id: str, chem_comp_id: str, pdb_id: str) -> RCSBChemicalIdentity:
    return RCSBChemicalIdentity(
        case_id=case_id,
        pdb_id=pdb_id,
        chem_comp_id=chem_comp_id,
        target="TARGET",
        selected_smiles="CCO",
        canonical_smiles="CCO",
        rdkit_inchikey="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
        reported_inchikey="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
        reported_name="ethanol",
        formula="C2 H6 O",
        formula_weight=46.07,
        source_url=f"https://data.rcsb.org/rest/v1/core/chemcomp/{chem_comp_id}",
    )


def test_moldisc_003_protocol_freezes_redock_cohort_and_boundary():
    config = load_program_config_v3(CONFIG)
    assert len(config["cases"]) == 15
    assert config["parent_benchmark"]["benchmark_id"] == "REDOCK-003"
    assert config["selection_rule"]["eligibility_boundary"] == ELIGIBILITY_BOUNDARY
    assert config["selection_rule"]["post_result_threshold_tuning"] is False
    assert {item["case_id"] for item in config["cases"]} == {
        f"ATX-{index:03d}" for index in range(1, 16)
    }


def test_parse_rcsb_chemcomp_accepts_direct_descriptor_schema():
    pytest.importorskip("rdkit")
    payload = {
        "rcsb_id": "TST",
        "chem_comp": {
            "name": "ETHANOL",
            "formula": "C2 H6 O",
            "formula_weight": 46.07,
        },
        "rcsb_chem_comp_descriptor": {
            "SMILES": "CCO",
            "SMILES_stereo": "CCO",
            "InChIKey": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
        },
    }
    item = parse_rcsb_chemcomp(
        payload,
        case={"case_id": "ATX-999", "pdb_id": "9XYZ", "chem_comp_id": "TST", "target": "TEST"},
        source_url="https://example.invalid/TST",
    )
    assert item.canonical_smiles == "CCO"
    assert item.rdkit_inchikey == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
    assert item.inchikey_matches_reported is True


def test_seed_selection_requires_predeclared_0_4_boundary_and_uses_highest_similarity():
    identities = (
        _identity("ATX-001", "AAA", "1AAA"),
        _identity("ATX-002", "BBB", "1BBB"),
        _identity("ATX-003", "CCC", "1CCC"),
    )
    selection = _select_seed(
        (
            _coverage("ATX-001", 0.39),
            _coverage("ATX-002", 0.41),
            _coverage("ATX-003", 0.58),
        ),
        identities,
    )
    assert selection.selected_case_id == "ATX-003"
    assert selection.selected_chem_comp_id == "CCC"
    assert selection.selected_nearest_similarity == pytest.approx(0.58)
    assert selection.eligible_case_ids == ("ATX-003", "ATX-002")


def test_seed_selection_closes_without_seed_when_no_case_reaches_boundary():
    identities = (
        _identity("ATX-001", "AAA", "1AAA"),
        _identity("ATX-002", "BBB", "1BBB"),
    )
    selection = _select_seed(
        (_coverage("ATX-001", 0.399), _coverage("ATX-002", 0.20)),
        identities,
    )
    assert selection.selected_case_id is None
    assert selection.eligible_case_ids == ()
