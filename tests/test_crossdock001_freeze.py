from __future__ import annotations

import re

from research_os.docking.crossdock001 import directed_case_specs
from research_os.docking.crossdock001_freeze import (
    FROZEN_DIRECTED_STRUCTURAL_IDENTITIES,
    NONPORTABLE_PREFLIGHT_ARTIFACT_ID,
    NONPORTABLE_PREFLIGHT_RAW_MANIFEST_HASH,
    NONPORTABLE_PREFLIGHT_RUN_ID,
    PREFLIGHT_ARTIFACT_ID,
    PREFLIGHT_ARTIFACT_ZIP_SHA256,
    PREFLIGHT_FREEZE_HEAD_SHA,
    PREFLIGHT_RUN_ID,
    PREFLIGHT_SELECTION_MANIFEST_HASH,
)
from research_os.docking.crossdock_identity import stable_hash


_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")


def test_structural_freeze_covers_exactly_all_directed_cases() -> None:
    expected = tuple(case["case_id"] for case in directed_case_specs())
    assert tuple(FROZEN_DIRECTED_STRUCTURAL_IDENTITIES) == expected
    assert len(expected) == 10


def test_portable_preflight_provenance_is_frozen() -> None:
    assert PREFLIGHT_RUN_ID == 34607126629
    assert PREFLIGHT_ARTIFACT_ID == 10266663459
    assert PREFLIGHT_SELECTION_MANIFEST_HASH == (
        "852f027bdc55ba8c2def9d3fde0a80e70cf6a4ffc375b4eb8a696e436b681215"
    )
    assert PREFLIGHT_ARTIFACT_ZIP_SHA256 == (
        "1c2a1f62e4290b3c21cfc918579c6f34e362c82c63a943bc2d8d4e1ee9cdcb5d"
    )
    assert PREFLIGHT_FREEZE_HEAD_SHA == "4192379f4a88262a20e2e64a46b486cd2047aa18"


def test_nonportable_first_manifest_is_retained_only_as_audit_provenance() -> None:
    assert NONPORTABLE_PREFLIGHT_RUN_ID == 34605661949
    assert NONPORTABLE_PREFLIGHT_ARTIFACT_ID == 10266555733
    assert NONPORTABLE_PREFLIGHT_RAW_MANIFEST_HASH == (
        "9631023f89b2971a503cab193989e0ac8d3eb53642d27fdcbf5572e5e04e4a26"
    )
    assert NONPORTABLE_PREFLIGHT_RAW_MANIFEST_HASH != PREFLIGHT_SELECTION_MANIFEST_HASH


def test_canonical_structural_hash_ignores_machine_epsilon_but_not_real_changes() -> None:
    first = {"x": 1.000000000000001, "nested": [2.000000000000004, -3.0]}
    equivalent = {"nested": [2.0, -3.000000000000003], "x": 1.0}
    changed = {"x": 1.00001, "nested": [2.0, -3.0]}
    assert stable_hash(first) == stable_hash(equivalent)
    assert stable_hash(first) != stable_hash(changed)


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
