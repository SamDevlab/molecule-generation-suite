"""Fail-closed structural parsing for the APD-010 BEM/MAV glycan.

This module deliberately stops at the experimental structural inventory.  It
does not infer a chemical graph, generate a conformer, prepare a PDBQT, or
invoke a docking engine.  The chemical graph is assembled by the dedicated
CCD adapter in :mod:`apodock_glycan_chemistry`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Iterable


@dataclass(frozen=True, order=True)
class GlycanAtom:
    component_id: str
    auth_seq_id: int
    insertion_code: str
    atom_name: str
    element: str
    xyz: tuple[float, float, float]

    def stable_dict(self) -> dict[str, object]:
        return {
            "component_id": self.component_id,
            "auth_seq_id": self.auth_seq_id,
            "insertion_code": self.insertion_code,
            "atom_name": self.atom_name,
            "element": self.element,
            "xyz": [round(value, 6) for value in self.xyz],
        }


@dataclass(frozen=True, order=True)
class GlycanLinkEndpoint:
    component_id: str
    auth_seq_id: int
    insertion_code: str
    atom_name: str
    author_chain: str

    def stable_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, order=True)
class GlycanLink:
    first: GlycanLinkEndpoint
    second: GlycanLinkEndpoint

    def stable_dict(self) -> dict[str, object]:
        first, second = sorted((self.first, self.second))
        return {
            "first": first.stable_dict(),
            "second": second.stable_dict(),
        }


class GlycanStructureError(ValueError):
    """Raised when the frozen experimental glycan inventory is invalid."""


def _altloc_is_primary(value: str) -> bool:
    return value in {"", " ", "A", "1"}


def _parse_auth_seq_id(value: str, *, line_number: int) -> int:
    try:
        return int(value.strip())
    except ValueError as exc:
        raise GlycanStructureError(
            f"invalid author residue number at PDB line {line_number}: {value!r}"
        ) from exc


def _element_from_atom_line(line: str) -> str:
    element = line[76:78].strip().upper()
    if element:
        return element
    atom_name = line[12:16].strip().upper()
    return atom_name[:2] if len(atom_name) > 1 and atom_name[:2].isalpha() else atom_name[:1]


def parse_glycan_atoms(
    pdb_text: str,
    component_ids: Iterable[str],
    author_chain: str,
) -> tuple[GlycanAtom, ...]:
    """Parse primary heavy-atom HETATM records for the selected glycan.

    Alternate locations other than blank/A/1 are ignored.  Duplicate atom
    keys, missing requested components, malformed coordinates, and malformed
    residue numbers fail closed.
    """

    wanted = frozenset(component_ids)
    if not wanted:
        raise GlycanStructureError("at least one glycan component is required")

    atoms: list[GlycanAtom] = []
    seen: set[tuple[str, int, str, str]] = set()
    for line_number, line in enumerate(pdb_text.splitlines(), start=1):
        if not line.startswith("HETATM") or len(line) < 78:
            continue
        if line[21].strip() != author_chain:
            continue
        if not _altloc_is_primary(line[16]):
            continue
        component_id = line[17:20].strip()
        if component_id not in wanted:
            continue
        element = _element_from_atom_line(line)
        if element in {"H", "D"}:
            continue
        try:
            xyz = (
                float(line[30:38]),
                float(line[38:46]),
                float(line[46:54]),
            )
        except ValueError as exc:
            raise GlycanStructureError(
                f"invalid glycan coordinates at PDB line {line_number}"
            ) from exc
        auth_seq_id = _parse_auth_seq_id(line[22:26], line_number=line_number)
        insertion_code = line[26].strip()
        atom_name = line[12:16].strip()
        key = (component_id, auth_seq_id, insertion_code, atom_name)
        if key in seen:
            raise GlycanStructureError(f"duplicate glycan atom key: {key}")
        seen.add(key)
        atoms.append(
            GlycanAtom(
                component_id=component_id,
                auth_seq_id=auth_seq_id,
                insertion_code=insertion_code,
                atom_name=atom_name,
                element=element,
                xyz=xyz,
            )
        )

    found = {atom.component_id for atom in atoms}
    missing = sorted(wanted - found)
    if missing:
        raise GlycanStructureError(f"missing glycan components: {missing}")
    if not atoms:
        raise GlycanStructureError("no selected glycan heavy atoms found")
    return tuple(sorted(atoms))


def _parse_link_endpoint(line: str, *, offset: int, author_chain: str) -> GlycanLinkEndpoint:
    component_id = line[offset + 5 : offset + 8].strip()
    chain = line[offset + 9].strip()
    return GlycanLinkEndpoint(
        component_id=component_id,
        auth_seq_id=_parse_auth_seq_id(line[offset + 10 : offset + 14], line_number=0),
        insertion_code=line[offset + 14].strip(),
        atom_name=line[offset : offset + 4].strip(),
        author_chain=chain,
    )


def parse_glycan_links(
    pdb_text: str,
    component_ids: Iterable[str],
    author_chain: str,
) -> tuple[GlycanLink, ...]:
    """Parse LINK records whose two endpoints belong to the selected glycan."""

    wanted = frozenset(component_ids)
    links: set[GlycanLink] = set()
    for line_number, line in enumerate(pdb_text.splitlines(), start=1):
        if not line.startswith("LINK") or len(line) < 57:
            continue
        if not _altloc_is_primary(line[16]) or not _altloc_is_primary(line[46]):
            continue
        try:
            endpoint_a = _parse_link_endpoint(line, offset=12, author_chain=author_chain)
            endpoint_b = _parse_link_endpoint(line, offset=42, author_chain=author_chain)
        except GlycanStructureError as exc:
            raise GlycanStructureError(f"invalid LINK at PDB line {line_number}: {exc}") from exc
        if endpoint_a.component_id not in wanted or endpoint_b.component_id not in wanted:
            continue
        if endpoint_a.author_chain != author_chain or endpoint_b.author_chain != author_chain:
            continue
        if endpoint_a.component_id == endpoint_b.component_id:
            continue
        first, second = sorted((endpoint_a, endpoint_b))
        links.add(GlycanLink(first, second))
    return tuple(sorted(links))


def validate_link_atoms(
    atoms: Iterable[GlycanAtom],
    links: Iterable[GlycanLink],
) -> None:
    atom_keys = {
        (atom.component_id, atom.auth_seq_id, atom.insertion_code, atom.atom_name)
        for atom in atoms
    }
    for link in links:
        for endpoint in (link.first, link.second):
            key = (
                endpoint.component_id,
                endpoint.auth_seq_id,
                endpoint.insertion_code,
                endpoint.atom_name,
            )
            if key not in atom_keys:
                raise GlycanStructureError(f"LINK endpoint is absent from atom inventory: {key}")


def structural_identity(atoms: Iterable[GlycanAtom], links: Iterable[GlycanLink]) -> str:
    atoms = tuple(atoms)
    links = tuple(links)
    validate_link_atoms(atoms, links)
    payload = {
        "atoms": [atom.stable_dict() for atom in sorted(atoms)],
        "links": [link.stable_dict() for link in sorted(links)],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
