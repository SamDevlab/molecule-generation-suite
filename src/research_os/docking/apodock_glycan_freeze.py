"""Frozen APD-010 remediated glycan structural identity.

Captured before any APD-010 chemistry adapter or APODOCK Vina execution.
"""
from __future__ import annotations

from typing import Any

from research_os.docking.apodock_glycan import (
    GlycanLinkEndpoint,
    parse_glycan_atoms,
    parse_glycan_links,
    structural_identity,
)

PREFLIGHT_RUN_ID = 34650546849
PREFLIGHT_HEAD_SHA = "38e9abfc3f4e5888dac93fa12716c040faf35947"
PREFLIGHT_ARTIFACT_ID = 10283961092
PREFLIGHT_ARTIFACT_ZIP_SHA256 = "af403c0be9842e956d714b2dc5751a0583af9dbb87a7919fd666a35250bf61af"
PDB_SHA256 = "d524b4932316fdaf7fbea162aae79285639010f51bfb4a09c169127aa0248c8f"
GLYCAN_STRUCTURAL_IDENTITY = "468c8052ff213fbb3a11f6198b61170e41d4b92353a44461a90326b157bdf306"
REPORT_IDENTITY = "473933410cd6834b5d6b1c72479ad7729ee23132d85e07a75b596cff0cb712e6"
EXPECTED_TOTAL_HEAVY_ATOMS = 24
EXPECTED_COMPONENT_HEAVY_ATOM_COUNTS = {"BEM": 11, "MAV": 13}
EXPECTED_LINK_ENDPOINTS = (
    GlycanLinkEndpoint("BEM", 2, "", "C1", "B"),
    GlycanLinkEndpoint("MAV", 1, "", "O4", "B"),
)


def validate_frozen_glycan_report(report: dict[str, Any]) -> None:
    if report.get("pdb_sha256") != PDB_SHA256:
        raise ValueError("APD-010 frozen 1Y3N PDB identity changed")
    if report.get("total_heavy_atoms") != EXPECTED_TOTAL_HEAVY_ATOMS:
        raise ValueError("APD-010 glycan heavy-atom count changed")
    if report.get("component_heavy_atom_counts") != EXPECTED_COMPONENT_HEAVY_ATOM_COUNTS:
        raise ValueError("APD-010 component heavy-atom inventory changed")
    if report.get("adapter_implemented") is not False:
        raise ValueError("glycan freeze must precede chemistry adapter implementation")
    if report.get("chemistry_ready_for_vina") is not False:
        raise ValueError("glycan freeze must remain pre-chemistry")
    if report.get("docking_executed") is not False:
        raise ValueError("glycan freeze must not execute docking")
    if report.get("vina_imported_or_invoked") is not False:
        raise ValueError("glycan freeze must not import or invoke Vina")

    atoms = report.get("atoms")
    links = report.get("links")
    if not isinstance(atoms, list) or not isinstance(links, list):
        raise ValueError("glycan report lacks atom/link inventories")
    if len(links) != 1:
        raise ValueError("APD-010 must have exactly one frozen inter-component link")

    observed_endpoints = tuple(
        GlycanLinkEndpoint(**endpoint)
        for endpoint in (links[0]["first"], links[0]["second"])
    )
    if observed_endpoints != EXPECTED_LINK_ENDPOINTS:
        raise ValueError(
            f"APD-010 glycosidic LINK changed: {observed_endpoints} != {EXPECTED_LINK_ENDPOINTS}"
        )

    # Rebuild the structural identity from the report's own atom and LINK inventory.
    # Coordinates are written to six decimals by the preflight, matching the parser's
    # stable representation.
    from research_os.docking.apodock_glycan import GlycanAtom, GlycanLink

    rebuilt_atoms = tuple(
        sorted(
            GlycanAtom(
                component_id=item["component_id"],
                auth_seq_id=item["auth_seq_id"],
                insertion_code=item["insertion_code"],
                atom_name=item["atom_name"],
                element=item["element"],
                xyz=tuple(item["xyz"]),
            )
            for item in atoms
        )
    )
    rebuilt_links = (
        GlycanLink(
            GlycanLinkEndpoint(**links[0]["first"]),
            GlycanLinkEndpoint(**links[0]["second"]),
        ),
    )
    rebuilt_identity = structural_identity(rebuilt_atoms, rebuilt_links)
    if rebuilt_identity != GLYCAN_STRUCTURAL_IDENTITY:
        raise ValueError(
            f"APD-010 glycan structural identity changed: {rebuilt_identity} != {GLYCAN_STRUCTURAL_IDENTITY}"
        )
    if report.get("glycan_structural_identity") != GLYCAN_STRUCTURAL_IDENTITY:
        raise ValueError("reported APD-010 glycan structural identity changed")
    if report.get("report_identity") != REPORT_IDENTITY:
        raise ValueError("reported APD-010 preflight identity changed")
