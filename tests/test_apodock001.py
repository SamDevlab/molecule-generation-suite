from __future__ import annotations

import math

import pytest

from research_os.docking import apodock001, apodock001_freeze
from research_os.docking.crossdock_alignment import ProteinResidue, kabsch_source_to_target
from research_os.docking.crossdock_identity import stable_hash


def _residue(letter: str, xyz: tuple[float, float, float]) -> ProteinResidue:
    return ProteinResidue(
        auth_seq_id=1,
        insertion_code="",
        resname="ALA",
        one_letter=letter,
        ca_xyz=xyz,
        heavy_xyz=(xyz,),
    )


def test_published_source_and_case_metadata_are_frozen() -> None:
    assert apodock001.source_list_sha256() == apodock001.SOURCE_LIST_SHA256
    assert apodock001.case_metadata_sha256() == apodock001.CASE_METADATA_SHA256


def test_exact_ten_published_pairs_are_frozen_in_table_order() -> None:
    cases = apodock001.FROZEN_PUBLISHED_CASES
    assert len(cases) == apodock001.PUBLISHED_CASE_COUNT == 10
    assert tuple(case.case_id for case in cases) == apodock001.EXPECTED_CASE_IDS
    assert tuple((case.apo_pdb_id, case.holo_pdb_id) for case in cases) == (
        apodock001.EXPECTED_PDB_PAIRS
    )


def test_case_ids_and_structures_are_unique() -> None:
    cases = apodock001.FROZEN_PUBLISHED_CASES
    assert len({case.case_id for case in cases}) == 10
    pdb_ids = [pdb_id for case in cases for pdb_id in (case.apo_pdb_id, case.holo_pdb_id)]
    assert len(pdb_ids) == len(set(pdb_ids)) == 20


def test_ligand_mapping_is_explicit_and_branched_case_is_not_hidden() -> None:
    cases = apodock001.FROZEN_PUBLISHED_CASES
    assert all(case.holo_ligand_author_chain == "A" for case in cases[:9])
    assert all(case.ligand_representation == "single_ccd" for case in cases[:9])
    assert cases[-1].case_id == "APD-010"
    assert cases[-1].ligand_representation == "branched_glycan"
    assert cases[-1].holo_ligand_components == ("BEM", "MAV")
    assert cases[-1].holo_ligand_author_chain == "B"


def test_protocol_is_known_site_rigid_apo_not_blind_docking() -> None:
    assert "rigid-known-site" in apodock001.PROTOCOL_ID
    assert apodock001.LIGAND_GRID_PADDING_ANGSTROM == 6.0
    assert apodock001.GRID_MIN_SIDE_ANGSTROM == 20.0
    assert apodock001.GRID_MAX_SIDE_ANGSTROM == 30.0


def test_global_alignment_pairs_all_identical_aligned_residues() -> None:
    holo = (
        _residue("A", (0.0, 0.0, 0.0)),
        _residue("B", (1.0, 0.0, 0.0)),
        _residue("C", (0.0, 1.0, 0.0)),
    )
    apo = (
        _residue("A", (4.0, 7.0, -2.0)),
        _residue("B", (4.0, 8.0, -2.0)),
        _residue("C", (3.0, 7.0, -2.0)),
    )
    pairs = apodock001.matched_global_ca_pairs(holo, apo)
    assert len(pairs) == 3
    transform = kabsch_source_to_target(pairs)
    assert transform.rmsd_angstrom == pytest.approx(0.0, abs=1e-10)
    for observed, expected in zip(transform.apply([res.ca_xyz for res in holo]), [res.ca_xyz for res in apo]):
        assert math.dist(observed, expected) == pytest.approx(0.0, abs=1e-10)


def test_successful_no_vina_preflight_identity_is_frozen() -> None:
    identities = list(apodock001_freeze.FROZEN_STRUCTURAL_IDENTITIES)
    assert len(identities) == 10
    assert [row["case_id"] for row in identities] == list(apodock001.EXPECTED_CASE_IDS)
    assert stable_hash(identities) == apodock001_freeze.SELECTION_MANIFEST_HASH
    assert apodock001_freeze.STRUCTURALLY_ELIGIBLE_COUNT == 10
    assert apodock001_freeze.CHEMISTRY_READY_FOR_VINA_COUNT == 9
    assert identities[-1]["ligand_components"] == ["BEM", "MAV"]
    assert identities[-1]["chemistry_ready_for_vina"] is False
