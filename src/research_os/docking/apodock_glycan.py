"""Structural parsing primitives for APODOCK branched-glycan ligands.

This module does not create docking chemistry and does not call Vina.  Its
first role is to capture the atom inventory and explicit PDB LINK connectivity
of the remediated 1Y3N oligosaccharide before a chemistry adapter is written.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from research_os.core.hashing import sha256_json
from research_os.docking import redocking as base


@dataclass(frozen=True, order=True)
class GlycanAtom:
    component_id: str
    auth_seq_id: int
    insertion_code: str
    atom_name: str
    element: str
    xyz: tuple[float, float, float]

    def stable_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["xyz"] = [round(value, 6) for value in self.xyz]
        return payload


@dataclass(frozen=True, order=True)
class GlycanLinkEndpoint:
    component_id: str
    auth_seq_id: int
    insertion_code: str
    atom_name: str
    author_chain: str


@dataclass(frozen=True)
class GlycanLink:
    first: GlycanLinkEndpoint
    second: GlycanLinkEndpoint

    def canonical_endpoints(self) -> tuple[GlycanLinkEndpoint, GlycanLinkEndpoint]:
        return tuple(sorted((self.first, self.second)))  # type: ignore[return-value]

    def stable_dict(self) -> dict[str, object]:
        first, second = self.canonical_endpoints()
        return {"first": asdict(first), "second": asdict(second)}


def _int_field(value: str, *, label: str) -> int:
    try:
        return int(value.strip())
    except ValueError as exc:
        raise ValueError(f"invalid {label}: {value!r}") from exc


def _xyz(line: str) -> tuple[float, float, float]:
    return float(line[30:38]), float(line[38:46]), float(line[46:54])


def parse_glycan_atoms(
    pdb_text: str,
    *,
    component_ids: tuple[str, ...],
    author_chain: str,
) -> tuple[GlycanAtom, ...]:
    wanted = set(component_ids)
    atoms: list[GlycanAtom] = []
    seen: set[tuple[str, int, str, str]] = set()
    for line in pdb_text.splitlines():
        if len(line) < 54 or line[:6].strip() != "HETATM" or not base._primary_altloc(line):
            continue
        if line[21].strip() != author_chain:
            continue
        component_id = line[17:20].strip()
        if component_id not in wanted:
            continue
        element = base._element_from_pdb_line(line)
        if element in {"H", "D"}:
            continue
        auth_seq_id = _int_field(line[22:26], label="HETATM auth_seq_id")
        insertion_code = line[26].strip()
        atom_name = line[12:16].strip()
        key = (component_id, auth_seq_id, insertion_code, atom_name)
        if key in seen:
            raise ValueError(f"duplicate glycan atom identity: {key}")
        seen.add(key)
        atoms.append(
            GlycanAtom(
                component_id=component_id,
                auth_seq_id=auth_seq_id,
                insertion_code=insertion_code,
                atom_name=atom_name,
                element=element,
                xyz=_xyz(line),
            )
        )
    if not atoms:
        raise ValueError("no requested glycan heavy atoms found")
    missing = wanted - {atom.component_id for atom in atoms}
    if missing:
        raise ValueError(f"missing glycan components: {sorted(missing)}")
    return tuple(sorted(atoms))


def _link_endpoint(line: str, *, second: bool) -> GlycanLinkEndpoint:
    if second:
        atom_slice, res_slice, chain_index, seq_slice, icode_index = (
            slice(42, 46), slice(47, 50), 51, slice(52, 56), 56
        )
    else:
        atom_slice, res_slice, chain_index, seq_slice, icode_index = (
            slice(12, 16), slice(17, 20), 21, slice(22, 26), 26
        )
    return GlycanLinkEndpoint(
        component_id=line[res_slice].strip(),
        auth_seq_id=_int_field(line[seq_slice], label="LINK auth_seq_id"),
        insertion_code=line[icode_index].strip(),
        atom_name=line[atom_slice].strip(),
        author_chain=line[chain_index].strip(),
    )


def parse_glycan_links(
    pdb_text: str,
    *,
    component_ids: tuple[str, ...],
    author_chain: str,
) -> tuple[GlycanLink, ...]:
    wanted = set(component_ids)
    links: list[GlycanLink] = []
    seen: set[tuple[GlycanLinkEndpoint, GlycanLinkEndpoint]] = set()
    for line in pdb_text.splitlines():
        if not line.startswith("LINK") or len(line) < 57:
            continue
        first = _link_endpoint(line, second=False)
        second = _link_endpoint(line, second=True)
        if (
            first.author_chain != author_chain
            or second.author_chain != author_chain
            or first.component_id not in wanted
            or second.component_id not in wanted
        ):
            continue
        link = GlycanLink(first, second)
        key = link.canonical_endpoints()
        if key not in seen:
            links.append(link)
            seen.add(key)
    return tuple(sorted(links, key=lambda link: link.canonical_endpoints()))


def validate_link_atoms(
    atoms: tuple[GlycanAtom, ...], links: tuple[GlycanLink, ...]
) -> None:
    atom_keys = {
        (atom.component_id, atom.auth_seq_id, atom.insertion_code, atom.atom_name)
        for atom in atoms
    }
    for link in links:
        for endpoint in link.canonical_endpoints():
            key = (
                endpoint.component_id,
                endpoint.auth_seq_id,
                endpoint.insertion_code,
                endpoint.atom_name,
            )
            if key not in atom_keys:
                raise ValueError(f"LINK endpoint is absent from glycan atom inventory: {key}")


def structural_identity(
    atoms: tuple[GlycanAtom, ...], links: tuple[GlycanLink, ...]
) -> str:
    validate_link_atoms(atoms, links)
    return sha256_json(
        {
            "atoms": [atom.stable_dict() for atom in atoms],
            "links": [link.stable_dict() for link in links],
        }
    )
