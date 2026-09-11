from research_os.docking import astex20
from research_os.docking.redocking import FROZEN_REDOCKING_CASES
from research_os.docking.redocking_holdout import FROZEN_HOLDOUT_CASES


def test_astex20_source_identity_is_frozen():
    assert astex20.BENCHMARK_ID == "REDOCK-003"
    assert astex20.PROTOCOL_ID == "research-os.redocking.astex20.v1.0"
    assert astex20.SOURCE_SET == "Astex Diverse Set"
    assert len(astex20.ASTEX_DIVERSE_85) == 85
    assert len(set(astex20.ASTEX_DIVERSE_85)) == 85
    assert astex20.source_list_sha256() == astex20.SOURCE_LIST_SHA256


def test_astex20_prior_observed_cases_match_redock_002():
    redock_002 = {f"{case.pdb_id}_{case.ligand_id}" for case in FROZEN_HOLDOUT_CASES}
    assert set(astex20.PRIOR_OBSERVED_ASTEX) == redock_002


def test_astex20_hash_ranking_is_deterministic_and_frozen():
    ranked = astex20.ranked_unseen_candidates()
    assert len(ranked) == 80
    assert ranked[:15] == astex20.INITIAL_HASH_RANKED_15
    assert set(ranked).isdisjoint(astex20.PRIOR_OBSERVED_ASTEX)


def test_astex20_candidates_do_not_overlap_redock_001():
    prior = {f"{case.pdb_id}_{case.ligand_id}" for case in FROZEN_REDOCKING_CASES}
    assert prior.isdisjoint(astex20.ranked_unseen_candidates())


def _pdb_line(record, serial, atom, residue, chain, seq, x, y, z, element):
    return (
        f"{record:<6}{serial:>5} {atom:<4} {residue:>3} {chain:1}{seq:>4}    "
        f"{x:>8.3f}{y:>8.3f}{z:>8.3f}{1.00:>6.2f}{20.00:>6.2f}          {element:>2}"
    )


def test_structural_discovery_finds_unique_ligand_and_contact_chains():
    lines = [
        "REMARK   2 RESOLUTION.    1.80 ANGSTROMS.",
        "COMPND    MOLECULE: TEST PROTEIN;",
        _pdb_line("ATOM", 1, "CA", "ALA", "A", 1, 0.0, 0.0, 0.0, "C"),
        _pdb_line("ATOM", 2, "CA", "ALA", "B", 1, 30.0, 0.0, 0.0, "C"),
        _pdb_line("HETATM", 3, "C1", "LIG", "L", 501, 3.0, 0.0, 0.0, "C"),
        _pdb_line("HETATM", 4, "O1", "LIG", "L", 501, 4.0, 0.0, 0.0, "O"),
    ]
    discovered = astex20.discover_structural_case("\n".join(lines), "9XYZ", "LIG")
    assert discovered["ligand_author_chain"] == "L"
    assert discovered["ligand_auth_seq_id"] == 501
    assert discovered["ligand_heavy_atoms_from_pdb"] == 2
    assert discovered["receptor_author_chains"] == ["A"]
    assert discovered["resolution_angstrom"] == 1.8
    assert discovered["target"] == "TEST PROTEIN"


def test_structural_discovery_rejects_multiple_ligand_instances():
    lines = [
        "REMARK   2 RESOLUTION.    2.00 ANGSTROMS.",
        _pdb_line("ATOM", 1, "CA", "ALA", "A", 1, 0.0, 0.0, 0.0, "C"),
        _pdb_line("HETATM", 2, "C1", "LIG", "L", 501, 3.0, 0.0, 0.0, "C"),
        _pdb_line("HETATM", 3, "C1", "LIG", "M", 502, 4.0, 0.0, 0.0, "C"),
    ]
    try:
        astex20.discover_structural_case("\n".join(lines), "9XYZ", "LIG")
    except ValueError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("multiple ligand instances must fail closed")
