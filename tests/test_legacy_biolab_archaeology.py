from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from research_os.legacy.biolab_archaeology import _normalize_identity, build_artifacts, dry_run


ROOT = Path(__file__).resolve().parents[1]


def _write_priority_fixture(root: Path) -> None:
    fixtures = {
        "Biolab/TOP_10_HITS_REFINADOS.csv": "Par_Molecular,Veredito,Delta_G_Consenso_C2\nLegacy pair,HIT REFINADO,-2.1\n",
        "Biolab/matriz_compostos_filtrados.csv": "Nome,Smiles,Peso_Molecular\nEthanol,CCO,46.069\n",
        "formolecular/csv_elite_farma/RANKING_FARMACOS_ELITE_ADMET.csv": "ID,SMILES,Score_QED\nETH,CCO,0.7\n",
        "formolecular/novo_horizonte/top10_validado_4EY7.csv": "ID_Mestre,SMILES,Eficacia_Humana_4EY7\nMOL_1,c1ccccc1,-6\n",
        "formolecular/novo_horizonte/top10_isolado.csv": "ID_Mestre,SMILES,Origem_Historica\nMOL_1,c1ccccc1,Gen 1\n",
        "formolecular/novo_horizonte/banco_mestre_unificado.csv": "ID_Mestre,SMILES,Origem_Historica\nMOL_2,not-a-smiles,Gen 2\n",
    }
    for relative, content in fixtures.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    (root / "formolecular/modelos_ia").mkdir(parents=True, exist_ok=True)
    (root / "formolecular/modelos_ia_farma").mkdir(parents=True, exist_ok=True)
    (root / "formolecular/modelos_ia/metadados_treino.json").write_text(json.dumps({"tamanho_ultimo_treino": 1, "r2_qed": 0.7}), encoding="utf-8")
    (root / "formolecular/modelos_ia/metadados_aero.json").write_text(json.dumps({"tamanho_ultimo_treino": 1, "r2_isp": 0.2}), encoding="utf-8")
    (root / "formolecular/modelos_ia_farma/metadados_farma_admet.json").write_text(json.dumps({"tamanho_ultimo_treino": 1, "r2_qed": 0.8}), encoding="utf-8")


def test_dry_run_does_not_write_and_detects_priority_sources(tmp_path: Path):
    _write_priority_fixture(tmp_path)
    result = dry_run(tmp_path, repo_root=ROOT)
    assert result["dry_run"] is True
    assert result["statistics"]["priority_sources_found"] == 6
    assert result["statistics"]["rows_scanned"] == 6
    assert not (tmp_path / "legacy" / "biolab-v0").exists()


def test_identity_normalization_deduplicates_without_collapsing_invalid_rows(tmp_path: Path):
    _write_priority_fixture(tmp_path)
    output = tmp_path / "out"
    manifest = build_artifacts(tmp_path, output_dir=output, repo_root=ROOT)
    assert manifest["statistics"]["identity_valid"] == 4
    assert manifest["statistics"]["identity_invalid"] == 1
    assert manifest["statistics"]["identity_missing"] == 1
    assert manifest["statistics"]["unique_exact_identities"] == 2
    assert manifest["statistics"]["duplicate_identities"] == 2
    rows = list(csv.DictReader((output / "legacy_molecular_index.csv").open(encoding="utf-8", newline="")))
    ethanol = next(row for row in rows if row["inchikey"] == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N")
    assert ethanol["legacy_source_count"] == "2"
    assert "BIOLAB_FILTERED" in ethanol["legacy_roles"]
    assert "FARMA_ELITE" in ethanol["legacy_roles"]
    assert any(row["identity_status"] == "IDENTITY_INVALID" for row in rows)


def test_evidence_contract_and_generation_boundary_are_closed(tmp_path: Path):
    _write_priority_fixture(tmp_path)
    output = tmp_path / "out"
    manifest = build_artifacts(tmp_path, output_dir=output, repo_root=ROOT)
    contract = json.loads((output / "evidence_contract.json").read_text(encoding="utf-8"))
    assert contract["origin"] == "LEGACY"
    assert contract["evidence_level"] == "COMPUTATIONAL"
    assert contract["experimental_validation"] == "NONE"
    assert contract["may_create_e4"] is False
    assert contract["may_open_generation_gate"] is False
    assert manifest["invariants"] == {
        "legacy_can_create_e4": False,
        "real_experiment_executed": False,
        "e4_created": False,
        "next_generation_allowed": False,
        "raw_data_committed": False,
    }


def test_stereoisomer_connectivity_is_not_exact_identity():
    first = _normalize_identity({"original_smiles": "F[C@H](Cl)Br", "original_inchi": "", "original_inchikey": ""})
    second = _normalize_identity({"original_smiles": "F[C@@H](Cl)Br", "original_inchi": "", "original_inchikey": ""})
    assert first["identity_status"] == "IDENTITY_VALID"
    assert second["identity_status"] == "IDENTITY_VALID"
    assert first["inchikey"] != second["inchikey"]
    assert first["inchikey"].split("-", 1)[0] == second["inchikey"].split("-", 1)[0]


def test_deterministic_regeneration(tmp_path: Path):
    _write_priority_fixture(tmp_path)
    first = build_artifacts(tmp_path, output_dir=tmp_path / "one", repo_root=ROOT)
    second = build_artifacts(tmp_path, output_dir=tmp_path / "two", repo_root=ROOT)
    assert first["canonical_corpus_hash"] == second["canonical_corpus_hash"]
    first_hashes = {path.name: path.read_bytes() for path in (tmp_path / "one").iterdir() if path.name != "manifest.json"}
    second_hashes = {path.name: path.read_bytes() for path in (tmp_path / "two").iterdir() if path.name != "manifest.json"}
    assert first_hashes == second_hashes


@pytest.mark.skipif(__import__("importlib").util.find_spec("rdkit") is None, reason="RDKit optional dependency")
def test_current_panel_match_categories_are_separate(tmp_path: Path):
    _write_priority_fixture(tmp_path)
    output = tmp_path / "out"
    build_artifacts(tmp_path, output_dir=output, repo_root=ROOT)
    rows = list(csv.DictReader((output / "current_panel_matches.csv").open(encoding="utf-8", newline="")))
    assert rows
    assert {row["match_type"] for row in rows} <= {"EXACT_IDENTITY_MATCH", "CONNECTIVITY_MATCH", "STRUCTURAL_SIMILARITY", "NO_MATCH"}
    assert all(row["similarity"] for row in rows)
