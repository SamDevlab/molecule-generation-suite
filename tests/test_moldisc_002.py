from __future__ import annotations

from pathlib import Path

import pytest

from research_os.molecular_discovery.aqsoldb_coverage import (
    AqSolDBSourceRecord,
    assess_aqsoldb_coverage,
    curate_structure_groups,
    parse_aqsoldb_csv,
)
from research_os.molecular_discovery.moldisc002 import (
    PROGRAM_ID,
    _parent_candidates,
    load_program_config_v2,
)


CONFIG = Path("programs/moldisc-002-aqsoldb-coverage/program.json")


def test_aqsoldb_parser_preserves_source_measurements():
    records, row_count, parsed_hash = parse_aqsoldb_csv(
        "ID,SMILES,Solubility,InChIKey\n"
        "A,CCO,-0.3,LFQSCWFLJHTTHZ-UHFFFAOYSA-N\n"
        "B,CCC,-1.2,ATUOYWHBWRKTHZ-UHFFFAOYSA-N\n"
    )
    assert row_count == 2
    assert len(records) == 2
    assert records[0].measured_log_s_mol_l == -0.3
    assert len(parsed_hash) == 64


def test_structure_groups_preserve_repeated_measurements():
    pytest.importorskip("rdkit")
    records = (
        AqSolDBSourceRecord("A", "CCO", -0.2),
        AqSolDBSourceRecord("B", "OCC", -0.8),
        AqSolDBSourceRecord("C", "CCC", -1.5),
    )
    groups, invalid = curate_structure_groups(records)
    assert invalid == 0
    ethanol = next(group for group in groups if group.observation_count == 2)
    assert ethanol.measured_log_s_values == (-0.2, -0.8)
    assert ethanol.median_measured_log_s_mol_l == pytest.approx(-0.5)
    assert ethanol.measurement_span == pytest.approx(0.6)


def test_coverage_uses_historical_similarity_bins_without_training():
    pytest.importorskip("rdkit")
    records = (
        AqSolDBSourceRecord("A", "CCO", -0.3),
        AqSolDBSourceRecord("B", "CCC", -1.2),
        AqSolDBSourceRecord("C", "c1ccccc1", -2.5),
    )
    report = assess_aqsoldb_coverage(
        [{"id": "Q1", "smiles": "CCO"}],
        records=records,
        source_row_count=3,
        parsed_source_hash="a" * 64,
    )
    item = report.candidates[0]
    assert item.nearest_similarity == pytest.approx(1.0)
    assert item.similarity_bin == "[0.8,1.0]"
    assert item.neighbors_ge_0_8 >= 1
    assert item.top_neighbors[0].source_ids == ("A",)


def test_moldisc_002_reuses_exact_moldisc_001_generation():
    pytest.importorskip("rdkit")
    config = load_program_config_v2(CONFIG)
    candidates, generation_hash = _parent_candidates(config, CONFIG)
    assert config["program_id"] == PROGRAM_ID
    assert len(candidates) == 9
    assert generation_hash == "d2881a9906a6a60d54e90a303601d9509983e6f1a0b9ce01a0792bf088890abe"
    assert candidates[0]["id"] == "MOLDISC-001-SEED-ID5"
    assert len({item["id"] for item in candidates}) == 9
