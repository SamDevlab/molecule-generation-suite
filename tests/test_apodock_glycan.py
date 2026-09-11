from __future__ import annotations

import pytest

from research_os.docking.apodock_glycan import (
    GlycanLinkEndpoint,
    parse_glycan_atoms,
    parse_glycan_links,
    structural_identity,
    validate_link_atoms,
)


def _hetatm(serial: int, atom: str, res: str, chain: str, seq: int, element: str, xyz=(1.0, 2.0, 3.0)) -> str:
    chars = [" "] * 80
    chars[0:6] = list("HETATM")
    chars[6:11] = list(f"{serial:5d}")
    chars[12:16] = list(f"{atom:>4s}")
    chars[17:20] = list(f"{res:>3s}")
    chars[21] = chain
    chars[22:26] = list(f"{seq:4d}")
    chars[30:38] = list(f"{xyz[0]:8.3f}")
    chars[38:46] = list(f"{xyz[1]:8.3f}")
    chars[46:54] = list(f"{xyz[2]:8.3f}")
    chars[76:78] = list(f"{element:>2s}")
    return "".join(chars)


def _link(atom1: str, res1: str, chain1: str, seq1: int, atom2: str, res2: str, chain2: str, seq2: int) -> str:
    chars = [" "] * 80
    chars[0:4] = list("LINK")
    chars[12:16] = list(f"{atom1:>4s}")
    chars[17:20] = list(f"{res1:>3s}")
    chars[21] = chain1
    chars[22:26] = list(f"{seq1:4d}")
    chars[42:46] = list(f"{atom2:>4s}")
    chars[47:50] = list(f"{res2:>3s}")
    chars[51] = chain2
    chars[52:56] = list(f"{seq2:4d}")
    return "".join(chars)


def _synthetic_pdb() -> str:
    return "\n".join(
        [
            _hetatm(1, "C1", "BEM", "B", 2, "C"),
            _hetatm(2, "O4", "MAV", "B", 1, "O", xyz=(2.0, 2.0, 3.0)),
            _hetatm(3, "O2", "BEM", "B", 2, "O", xyz=(1.0, 3.0, 3.0)),
            _hetatm(4, "CA", "CA", "A", 900, "CA"),
            _link("C1", "BEM", "B", 2, "O4", "MAV", "B", 1),
        ]
    )


def test_parser_keeps_exact_component_atom_identity_and_coordinates():
    atoms = parse_glycan_atoms(_synthetic_pdb(), component_ids=("BEM", "MAV"), author_chain="B")
    assert [(atom.component_id, atom.auth_seq_id, atom.atom_name) for atom in atoms] == [
        ("BEM", 2, "C1"),
        ("BEM", 2, "O2"),
        ("MAV", 1, "O4"),
    ]
    assert atoms[0].xyz == (1.0, 2.0, 3.0)


def test_parser_captures_only_intra_glycan_link_on_target_chain():
    links = parse_glycan_links(_synthetic_pdb(), component_ids=("BEM", "MAV"), author_chain="B")
    assert len(links) == 1
    assert links[0].canonical_endpoints() == (
        GlycanLinkEndpoint("BEM", 2, "", "C1", "B"),
        GlycanLinkEndpoint("MAV", 1, "", "O4", "B"),
    )


def test_structural_identity_is_independent_of_link_endpoint_order():
    forward = _synthetic_pdb()
    reverse = forward.rsplit("\n", 1)[0] + "\n" + _link("O4", "MAV", "B", 1, "C1", "BEM", "B", 2)
    forward_atoms = parse_glycan_atoms(forward, component_ids=("BEM", "MAV"), author_chain="B")
    reverse_atoms = parse_glycan_atoms(reverse, component_ids=("BEM", "MAV"), author_chain="B")
    forward_links = parse_glycan_links(forward, component_ids=("BEM", "MAV"), author_chain="B")
    reverse_links = parse_glycan_links(reverse, component_ids=("BEM", "MAV"), author_chain="B")
    assert structural_identity(forward_atoms, forward_links) == structural_identity(reverse_atoms, reverse_links)


def test_link_endpoint_must_exist_in_atom_inventory():
    text = _hetatm(1, "C1", "BEM", "B", 2, "C") + "\n" + _link("C1", "BEM", "B", 2, "O4", "MAV", "B", 1)
    with pytest.raises(ValueError, match="missing glycan components"):
        parse_glycan_atoms(text, component_ids=("BEM", "MAV"), author_chain="B")
