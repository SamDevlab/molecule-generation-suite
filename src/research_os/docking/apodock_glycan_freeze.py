"""Frozen APD-010 structural inputs for the chemical-gate preflight."""

from __future__ import annotations

from typing import Any, Iterable

from research_os.docking.apodock_glycan import GlycanLink, GlycanStructureError, structural_identity


PDB_ID = "1Y3N"
PDB_URL = "https://files.rcsb.org/download/1Y3N.pdb"
PDB_SHA256 = "d524b4932316fdaf7fbea162aae79285639010f51bfb4a09c169127aa0248c8f"
AUTHOR_CHAIN = "B"
COMPONENT_IDS = ("BEM", "MAV")
EXPECTED_COMPONENT_HEAVY_ATOM_COUNTS = {"BEM": 11, "MAV": 13}
EXPECTED_STRUCTURAL_HEAVY_ATOMS = 24
STRUCTURAL_IDENTITY = "468c8052ff213fbb3a11f6198b61170e41d4b92353a44461a90326b157bdf306"
EXPECTED_LINK_ENDPOINTS = {
    ("BEM", 2, "", "C1", "B"),
    ("MAV", 1, "", "O4", "B"),
}


def validate_frozen_structure(atoms: Iterable[Any], links: Iterable[GlycanLink]) -> None:
    atoms = tuple(atoms)
    links = tuple(links)
    counts: dict[str, int] = {}
    for atom in atoms:
        counts[atom.component_id] = counts.get(atom.component_id, 0) + 1
    if counts != EXPECTED_COMPONENT_HEAVY_ATOM_COUNTS:
        raise GlycanStructureError(f"APD-010 component counts changed: {counts}")
    if len(atoms) != EXPECTED_STRUCTURAL_HEAVY_ATOMS:
        raise GlycanStructureError(f"APD-010 structural heavy-atom count changed: {len(atoms)}")
    if len(links) != 1:
        raise GlycanStructureError(f"APD-010 LINK count changed: {len(links)}")
    observed_endpoints = {
        (
            endpoint.component_id,
            endpoint.auth_seq_id,
            endpoint.insertion_code,
            endpoint.atom_name,
            endpoint.author_chain,
        )
        for endpoint in (links[0].first, links[0].second)
    }
    if observed_endpoints != EXPECTED_LINK_ENDPOINTS:
        raise GlycanStructureError(f"APD-010 LINK endpoints changed: {observed_endpoints}")
    observed_identity = structural_identity(atoms, links)
    if observed_identity != STRUCTURAL_IDENTITY:
        raise GlycanStructureError(
            f"APD-010 structural identity changed: {observed_identity} != {STRUCTURAL_IDENTITY}"
        )
