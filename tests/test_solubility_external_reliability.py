from __future__ import annotations

import pytest

from research_os.benchmark.solubility import SolubilityBenchmarkError
from research_os.benchmark.solubility_external_reliability import (
    CONSENSUS_STRATA,
    EXPECTED_EXTERNAL_COUNT,
    EXPECTED_EXTERNAL_HASH,
    RELIABILITY_GROUPS,
    _summarize_stratum,
    parse_reliability_metadata,
)


def test_parse_reliability_metadata_preserves_official_fields() -> None:
    text = "\n".join(
        [
            "ID,SMILES,Solubility,Group,Occurrences,SD",
            "a,CC,-1.0,G1,1,0",
            "b,CCC,-2.0,G2,2,0.75",
            "c,CCCC,-3.0,G5,4,0.25",
        ]
    )
    records, metadata_hash = parse_reliability_metadata(text)
    assert [record.group for record in records] == ["G1", "G2", "G5"]
    assert [record.occurrences for record in records] == [1, 2, 4]
    assert [record.sd for record in records] == [0.0, 0.75, 0.25]
    assert len(metadata_hash) == 64


def test_parse_reliability_metadata_fails_closed_on_missing_columns() -> None:
    text = "ID,SMILES,Solubility\na,CC,-1.0\n"
    with pytest.raises(SolubilityBenchmarkError, match="missing column"):
        parse_reliability_metadata(text)


def test_parse_reliability_metadata_fails_closed_on_unknown_group() -> None:
    text = "ID,Group,Occurrences,SD\na,G9,1,0\n"
    with pytest.raises(SolubilityBenchmarkError, match="unexpected AqSolDB reliability group"):
        parse_reliability_metadata(text)


def test_predeclared_groups_and_consensus_strata_are_frozen() -> None:
    assert RELIABILITY_GROUPS == ("G1", "G2", "G3", "G4", "G5")
    assert CONSENSUS_STRATA == {
        "single_observation": ("G1",),
        "repeated_higher_dispersion": ("G2", "G4"),
        "repeated_lower_dispersion": ("G3", "G5"),
    }
    assert EXPECTED_EXTERNAL_COUNT == 8863
    assert EXPECTED_EXTERNAL_HASH == "0c3179ccdeb47b96b0afb3c38f61f6e9b95ab09c3071b18a433e3fb147d9c002"


def test_stratum_summary_keeps_error_and_domain_accounting_transparent() -> None:
    text = "\n".join(
        [
            "ID,Group,Occurrences,SD",
            "a,G3,2,0.2",
            "b,G3,2,0.4",
            "c,G3,2,0.3",
        ]
    )
    metadata, _ = parse_reliability_metadata(text)
    summary = _summarize_stratum(
        "G3",
        ("G3",),
        [0, 1, 2],
        truth=[-1.0, -2.0, -3.0],
        prediction=[-1.0, -1.0, -4.0],
        similarities=[0.2, 0.5, 0.8],
        metadata=metadata,
        ad_threshold=0.3,
    )
    assert summary.n == 3
    assert summary.in_domain_count == 2
    assert summary.out_of_domain_count == 1
    assert summary.out_of_domain_fraction == pytest.approx(1 / 3)
    assert summary.metrics.mae == pytest.approx(2 / 3)
    assert summary.median_max_train_similarity == 0.5
    assert summary.median_curated_sd == 0.3
    assert summary.median_occurrences == 2
