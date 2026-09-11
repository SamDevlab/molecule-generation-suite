"""Prospective APD-010 glycan chemistry construction.

The chemical graph is assembled from named RCSB CCD ideal MOL2 components and
an already-frozen experimental LINK.  This module does not dock, score, fit,
or use APODOCK outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from research_os.core.hashing import sha256_json


@dataclass(frozen=True)
class NamedAtomKey:
    component_id: str
    atom_name: str


DONOR_COMPONENT = "BEM"
ACCEPTOR_COMPONENT = "MAV"
DONOR_LEAVING_ATOM = NamedAtomKey(DONOR_COMPONENT, "O1")
DONOR_LINK_ATOM = NamedAtomKey(DONOR_COMPONENT, "C1")
ACCEPTOR_LINK_ATOM = NamedAtomKey(ACCEPTOR_COMPONENT, "O4")
EXPECTED_FORMULA = "C12H18O13"
EXPECTED_HEAVY_ATOMS = 25
EXPECTED_CRYSTAL_MISSING = (NamedAtomKey(DONOR_COMPONENT, "O4"),)


def _tripos_atom_name(atom: Chem.Atom) -> str:
    if not atom.HasProp("_TriposAtomName"):
        raise ValueError("RCSB ideal MOL2 atom is missing _TriposAtomName")
    name = atom.GetProp("_TriposAtomName").strip()
    if not name:
        raise ValueError("RCSB ideal MOL2 contains an empty atom name")
    return name


def load_named_ccd_mol2(path: str | Path, component_id: str) -> Chem.Mol:
    source = Path(path)
    mol = Chem.MolFromMol2File(str(source), sanitize=True, removeHs=False)
    if mol is None:
        raise ValueError(f"could not parse CCD MOL2: {source}")
    mol = Chem.RemoveHs(mol, sanitize=True)
    mol.RemoveAllConformers()
    seen: set[str] = set()
    for atom in mol.GetAtoms():
        name = _tripos_atom_name(atom)
        if name in seen:
            raise ValueError(f"duplicate atom name in {component_id}: {name}")
        seen.add(name)
        atom.SetProp("research_os_component_id", component_id)
        atom.SetProp("research_os_atom_name", name)
    return mol


def _key(atom: Chem.Atom) -> NamedAtomKey:
    return NamedAtomKey(
        atom.GetProp("research_os_component_id"),
        atom.GetProp("research_os_atom_name"),
    )


def _find_unique_atom_index(mol: Chem.Mol, key: NamedAtomKey) -> int:
    matches = [atom.GetIdx() for atom in mol.GetAtoms() if _key(atom) == key]
    if len(matches) != 1:
        raise ValueError(f"expected one atom {key}, found {len(matches)}")
    return matches[0]


def _remove_named_atom(mol: Chem.Mol, key: NamedAtomKey) -> Chem.Mol:
    index = _find_unique_atom_index(mol, key)
    rw = Chem.RWMol(mol)
    rw.RemoveAtom(index)
    result = rw.GetMol()
    Chem.SanitizeMol(result)
    return result


def assemble_apd010_disaccharide(bem: Chem.Mol, mav: Chem.Mol) -> Chem.Mol:
    """Return the full 25-heavy-atom BEM-(1->4)-MAV graph.

    BEM O1 is the donor leaving hydroxyl oxygen.  MAV O4 is retained as the
    glycosidic bridge oxygen, consistent with the frozen 1Y3N LINK.
    """
    bem_linking = _remove_named_atom(Chem.Mol(bem), DONOR_LEAVING_ATOM)
    combined = Chem.CombineMols(bem_linking, Chem.Mol(mav))
    rw = Chem.RWMol(combined)
    donor_idx = _find_unique_atom_index(rw, DONOR_LINK_ATOM)
    acceptor_idx = _find_unique_atom_index(rw, ACCEPTOR_LINK_ATOM)
    if rw.GetBondBetweenAtoms(donor_idx, acceptor_idx) is not None:
        raise ValueError("frozen glycosidic bond already exists unexpectedly")
    rw.AddBond(donor_idx, acceptor_idx, Chem.BondType.SINGLE)
    result = rw.GetMol()
    Chem.SanitizeMol(result)
    result.RemoveAllConformers()
    validate_apd010_chemistry(result)
    return result


def validate_apd010_chemistry(mol: Chem.Mol) -> None:
    if mol.GetNumHeavyAtoms() != EXPECTED_HEAVY_ATOMS:
        raise ValueError(
            f"APD-010 glycan must contain {EXPECTED_HEAVY_ATOMS} heavy atoms, found {mol.GetNumHeavyAtoms()}"
        )
    formula = rdMolDescriptors.CalcMolFormula(mol)
    if formula != EXPECTED_FORMULA:
        raise ValueError(f"APD-010 glycan formula changed: {formula} != {EXPECTED_FORMULA}")
    keys = [_key(atom) for atom in mol.GetAtoms()]
    if len(keys) != len(set(keys)):
        raise ValueError("APD-010 assembled atom identities are not unique")
    if DONOR_LEAVING_ATOM in keys:
        raise ValueError("BEM O1 must not remain in the linked disaccharide graph")
    donor_idx = _find_unique_atom_index(mol, DONOR_LINK_ATOM)
    acceptor_idx = _find_unique_atom_index(mol, ACCEPTOR_LINK_ATOM)
    bond = mol.GetBondBetweenAtoms(donor_idx, acceptor_idx)
    if bond is None or bond.GetBondType() != Chem.BondType.SINGLE:
        raise ValueError("APD-010 frozen BEM:C1-MAV:O4 bond is absent")


def atom_keys(mol: Chem.Mol) -> tuple[NamedAtomKey, ...]:
    return tuple(sorted(_key(atom) for atom in mol.GetAtoms()))


def coordinate_mapping_diagnostic(
    mol: Chem.Mol,
    observed_keys: Iterable[NamedAtomKey],
) -> dict[str, object]:
    chemical = set(atom_keys(mol))
    observed = set(observed_keys)
    unexpected = observed - chemical
    missing = chemical - observed
    if unexpected:
        raise ValueError(f"crystallographic atoms absent from assembled chemistry: {sorted(unexpected)}")
    if tuple(sorted(missing)) != EXPECTED_CRYSTAL_MISSING:
        raise ValueError(
            f"APD-010 chemical/crystal atom gap changed: {tuple(sorted(missing))} != {EXPECTED_CRYSTAL_MISSING}"
        )
    return {
        "chemical_heavy_atoms": len(chemical),
        "coordinate_bearing_heavy_atoms": len(observed),
        "missing_coordinate_atoms": [
            {"component_id": item.component_id, "atom_name": item.atom_name}
            for item in sorted(missing)
        ],
    }


def chemistry_identity(mol: Chem.Mol) -> str:
    validate_apd010_chemistry(mol)
    atoms = sorted(
        (
            _key(atom),
            atom.GetSymbol(),
            atom.GetFormalCharge(),
            int(atom.GetChiralTag()),
        )
        for atom in mol.GetAtoms()
    )
    bonds = []
    for bond in mol.GetBonds():
        first = _key(bond.GetBeginAtom())
        second = _key(bond.GetEndAtom())
        low, high = sorted((first, second))
        bonds.append(
            {
                "first": {"component_id": low.component_id, "atom_name": low.atom_name},
                "second": {"component_id": high.component_id, "atom_name": high.atom_name},
                "bond_type": str(bond.GetBondType()),
            }
        )
    atom_payload = [
        {
            "component_id": key.component_id,
            "atom_name": key.atom_name,
            "element": element,
            "formal_charge": charge,
            "chiral_tag": chiral_tag,
        }
        for key, element, charge, chiral_tag in atoms
    ]
    return sha256_json(
        {
            "formula": rdMolDescriptors.CalcMolFormula(mol),
            "heavy_atoms": mol.GetNumHeavyAtoms(),
            "isomeric_smiles": Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True),
            "atoms": atom_payload,
            "bonds": sorted(bonds, key=lambda item: (item["first"]["component_id"], item["first"]["atom_name"], item["second"]["component_id"], item["second"]["atom_name"])),
        }
    )
