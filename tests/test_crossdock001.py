from __future__ import annotations

import math

import pytest

from research_os.docking.crossdock001 import (
    DIRECTED_CASE_COUNT,
    EXPECTED_SELECTED_PAIR_IDS,
    EXPECTED_SELECTION_KEYS,
    FROZEN_SELECTED_PAIRS,
    SOURCE_LIST_SHA256,
    directed_case_specs,
    previously_observed_pdb_ids,
    selected_published_pairs,
    selection_key,
    source_list_sha256,
)
from research_os.docking.crossdock_alignment import (
    kabsch_source_to_target,
    needleman_wunsch_indices,
)


def test_published_source_list_identity_is_frozen() -> None:
    assert source_list_sha256() == SOURCE_LIST_SHA256


def test_deterministic_selection_is_exactly_the_frozen_five_pairs() -> None:
    selected = selected_published_pairs()
    assert tuple(pair.pair_id for pair in selected) == EXPECTED_SELECTED_PAIR_IDS
    assert tuple(selection_key(pair) for pair in selected) == EXPECTED_SELECTION_KEYS
    assert tuple(pair.pair_id for pair in FROZEN_SELECTED_PAIRS) == EXPECTED_SELECTED_PAIR_IDS


def test_selected_pairs_do_not_overlap_prior_redocking_pdbs() -> None:
    observed = previously_observed_pdb_ids()
    for pair in FROZEN_SELECTED_PAIRS:
        assert pair.first.pdb_id not in observed
        assert pair.second.pdb_id not in observed


def test_both_directions_are_frozen_for_all_five_pairs() -> None:
    cases = directed_case_specs()
    assert len(cases) == DIRECTED_CASE_COUNT
    assert tuple(case["case_id"] for case in cases) == (
        "XDK-01-1", "XDK-01-2",
        "XDK-02-1", "XDK-02-2",
        "XDK-03-1", "XDK-03-2",
        "XDK-04-1", "XDK-04-2",
        "XDK-05-1", "XDK-05-2",
    )
    for first, second in zip(cases[::2], cases[1::2]):
        assert first["pair_id"] == second["pair_id"]
        assert first["source"] == second["target"]
        assert first["target"] == second["source"]


def test_alignment_tie_breaking_is_deterministic() -> None:
    assert needleman_wunsch_indices("ABC", "ABC") == ((0, 0), (1, 1), (2, 2))
    assert needleman_wunsch_indices("AB", "AAB") == ((None, 0), (0, 1), (1, 2))


def test_kabsch_transform_maps_source_into_target_frame() -> None:
    source = (
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )
    target = tuple((-y + 4.0, x + 7.0, z - 2.0) for x, y, z in source)
    transform = kabsch_source_to_target(tuple(zip(source, target)))
    assert transform.pair_count == 4
    assert transform.rmsd_angstrom == pytest.approx(0.0, abs=1e-10)
    transformed = transform.apply(source)
    for observed, expected in zip(transformed, target):
        assert math.dist(observed, expected) == pytest.approx(0.0, abs=1e-10)
