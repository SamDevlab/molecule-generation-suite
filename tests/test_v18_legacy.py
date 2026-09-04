from pathlib import Path

import pytest

from research_os.candidates import CandidateEvaluation, CandidateGenerator, CandidateRanking, GenerationMethod
from research_os.legacy import LegacyDataClass, MigrationStatus, ParityType, scan_legacy


def test_candidate_generation_is_always_synthetic():
    candidates = CandidateGenerator(seed=7).generate(GenerationMethod.LEGACY_IMPORT, ["CCO", "c1ccccc1"], limit=1)
    assert len(candidates) == 1
    assert candidates[0].synthetic is True
    assert candidates[0].method is GenerationMethod.LEGACY_IMPORT


def test_ranking_excludes_ood_and_indeterminate_without_numeric_penalty():
    result = CandidateRanking.rank(
        [
            CandidateEvaluation("a", "qed", 0.7, "max", "RDKit", "PASS"),
            CandidateEvaluation("b", "qed", 100.0, "max", "ML", "PASS", ood=True),
            CandidateEvaluation("c", "qed", 0.99, "max", "Vina", "INDETERMINATE"),
        ],
        metric="qed",
    )
    assert [item.candidate_id for item in result.ranked] == ["a"]
    assert result.exclusion_reasons == {"b": "OUT_OF_DOMAIN", "c": "INDETERMINATE"}


def test_read_only_inventory_finds_legacy_flows_without_editing(tmp_path: Path):
    (tmp_path / "Biolab").mkdir()
    (tmp_path / "formolecular").mkdir()
    script = tmp_path / "formolecular" / "g_oraculo_aeroespacial.py"
    script.write_text("import xgboost\nR2_confiança\n", encoding="utf-8")
    data = tmp_path / "formolecular" / "ranking.csv"
    data.write_text("SMILES,score\nCCO,1\n", encoding="utf-8")
    before = script.read_bytes()
    inventory = scan_legacy(tmp_path)
    assert inventory.components[0].status is MigrationStatus.ACTIVE
    assert any("ML_PIPELINE" in item.flags for item in inventory.components)
    assert inventory.quarantine[0].data_class is LegacyDataClass.UNKNOWN_PROVENANCE
    assert inventory.replacements
    assert script.read_bytes() == before


@pytest.mark.skipif(__import__("importlib").util.find_spec("rdkit") is None, reason="RDKit optional dependency")
def test_legacy_deterministic_parity_contract():
    from research_os.legacy import deterministic_property_parity

    assessment = deterministic_property_parity("CCO")
    assert assessment.parity is ParityType.NUMERICAL
    assert assessment.equivalent is True
    assert set(assessment.replacement_values) == {"qed", "molecular_weight", "logp", "tpsa", "fraction_csp3", "rotatable_bonds", "aromatic_rings", "h_donors", "h_acceptors"}

