from __future__ import annotations

import re

from research_os.docking.crossdock001 import directed_case_specs
from research_os.docking.crossdock001_freeze import (
    FROZEN_DIRECTED_STRUCTURAL_IDENTITIES,
    PREFLIGHT_ARTIFACT_ID,
    PREFLIGHT_ARTIFACT_ZIP_SHA256,
    PREFLIGHT_FREEZE_HEAD_SHA,
    PREFLIGHT_RUN_ID,
    PREFLIGHT_SELECTION_MANIFEST_HASH,
)


_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")


def test_structural_freeze_covers_exactly_all_directed_cases() -> None:
    expected = tuple(case["case_id"] for case in directed_case_specs())
    assert tuple(FROZEN_DIRECTED_STRUCTURAL_IDENTITIES) == expected
    assert len(expected) == 10


def test_preflight_provenance_is_frozen() -> None:
    assert PREFLIGHT_RUN_ID == 34605661949
    assert PREFLIGHT_ARTIFACT_ID == 10266555733
    assert PREFLIGHT_SELECTION_MANIFEST_HASH == (
        "9631023f89b2971a503cab193989e0ac8d3eb53642d27fdcbf5572e5e04e4a26"
    )
    assert PREFLIGHT_ARTIFACT_ZIP_SHA256 == (
        "de539ce3c3f08d892ae967bb09f7aaac0fd4cec6fadfe5407ad3ff0cd650eff4"
    )
    assert PREFLIGHT_FREEZE_HEAD_SHA == "34780d629b800578becd72ad1280b36c1b90f252"


def test_all_frozen_structural_hashes_and_alignment_counts_are_valid() -> None:
    for case_id, identity in FROZEN_DIRECTED_STRUCTURAL_IDENTITIES.items():
        assert case_id.startswith("XDK-")
        for field in (
            "source_pdb_sha256",
            "target_pdb_sha256",
            "transformed_source_reference_coordinate_hash",
            "target_reference_coordinate_hash",
            "grid_hash",
        ):
            assert _HEX64.fullmatch(str(identity[field]))
        assert int(identity["matched_identical_pocket_ca_pairs"]) >= 8

    assert _HEX64.fullmatch(PREFLIGHT_SELECTION_MANIFEST_HASH)
    assert _HEX64.fullmatch(PREFLIGHT_ARTIFACT_ZIP_SHA256)
    assert _HEX40.fullmatch(PREFLIGHT_FREEZE_HEAD_SHA)
