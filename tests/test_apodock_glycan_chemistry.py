from __future__ import annotations

import pytest

Chem = pytest.importorskip("rdkit.Chem")

from research_os.docking import apodock001_freeze
from research_os.docking.apodock_glycan_chemistry import (
    BEM_COMPONENT_ID,
    BEM_HEAVY_ATOM_NAMES,
    BEM_LEAVING_ATOM,
    CHEMISTRY_GATE_ID,
    MAV_COMPONENT_ID,
    MAV_HEAVY_ATOM_NAMES,
    NamedAtomKey,
    APD010ChemistryError,
    adapt_apd010,
    chemistry_identity,
    coordinate_mapping_diagnostic,
    load_named_ccd_mol2,
)


BEM_SMILES = "O=C(O)[C@H]1O[C@@H](O)[C@@H](O)[C@@H](O)[C@@H]1O"
MAV_SMILES = "O=C(O)[C@H]1O[C@H](O)[C@@H](O)[C@@H](O)[C@@H]1O"


def _named_component(component_id: str):
    molecule = Chem.MolFromSmiles(BEM_SMILES if component_id == BEM_COMPONENT_ID else MAV_SMILES)
    assert molecule is not None
    carbon_atoms = [atom for atom in molecule.GetAtoms() if atom.GetSymbol() == "C"]
    oxygen_atoms = [atom for atom in molecule.GetAtoms() if atom.GetSymbol() == "O"]
    if component_id == BEM_COMPONENT_ID:
        carbonyl_carbon = next(
            atom
            for atom in carbon_atoms
            if any(
                neighbor.GetSymbol() == "O" and molecule.GetBondBetweenAtoms(atom.GetIdx(), neighbor.GetIdx()).GetBondType() == Chem.BondType.DOUBLE
                for neighbor in atom.GetNeighbors()
            )
        )
        leaving_oxygen = next(
            neighbor
            for neighbor in carbonyl_carbon.GetNeighbors()
            if neighbor.GetSymbol() == "O"
            and molecule.GetBondBetweenAtoms(carbonyl_carbon.GetIdx(), neighbor.GetIdx()).GetBondType() == Chem.BondType.SINGLE
        )
        carbon_names = {carbonyl_carbon.GetIdx(): "C1"}
        oxygen_names = {leaving_oxygen.GetIdx(): "O1"}
    else:
        carbon_names = {}
        oxygen_names = {}
        for index, atom in enumerate(carbon_atoms, start=1):
            carbon_names[atom.GetIdx()] = f"C{index}"

    if component_id == BEM_COMPONENT_ID:
        for name, atom in zip(
            ["C2", "C3", "C4", "C5", "C6"],
            [atom for atom in carbon_atoms if atom.GetIdx() != carbonyl_carbon.GetIdx()],
        ):
            carbon_names[atom.GetIdx()] = name
        for name, atom in zip(
            ["O2", "O3", "O4", "O5", "O6A", "O6B"],
            [atom for atom in oxygen_atoms if atom.GetIdx() != leaving_oxygen.GetIdx()],
        ):
            oxygen_names[atom.GetIdx()] = name
    else:
        # A hydroxyl oxygen is the experimental glycosidic acceptor.
        acceptor = next(
            atom
            for atom in oxygen_atoms
            if atom.GetDegree() == 1
            and molecule.GetBondBetweenAtoms(atom.GetIdx(), atom.GetNeighbors()[0].GetIdx()).GetBondType() == Chem.BondType.SINGLE
        )
        oxygen_names[acceptor.GetIdx()] = "O4"
        remaining = [atom for atom in oxygen_atoms if atom.GetIdx() != acceptor.GetIdx()]
        remaining_names = ["O1", "O2", "O3", "O5", "O6A", "O6B"]
        for name, atom in zip(remaining_names, remaining):
            oxygen_names[atom.GetIdx()] = name

    for atom in molecule.GetAtoms():
        atom.SetProp("research_os_component_id", component_id)
        atom.SetProp(
            "research_os_atom_name",
            carbon_names.get(atom.GetIdx()) or oxygen_names[atom.GetIdx()],
        )
        atom.SetProp(
            "research_os_leaving_atom_flag",
            "Y" if component_id == BEM_COMPONENT_ID and oxygen_names.get(atom.GetIdx()) == "O1" else "N",
        )
        atom.SetIntProp("research_os_ccd_charge", 0)
    return molecule


@pytest.fixture()
def bem_mav():
    return _named_component(BEM_COMPONENT_ID), _named_component(MAV_COMPONENT_ID)


def test_previous_frozen_state_keeps_apd010_out_of_direct_chemistry_gate():
    assert apodock001_freeze.CHEMISTRY_READY_FOR_VINA_COUNT == 9
    apd010 = next(row for row in apodock001_freeze.FROZEN_STRUCTURAL_IDENTITIES if row["case_id"] == "APD-010")
    assert apd010["chemistry_ready_for_vina"] is False
    assert CHEMISTRY_GATE_ID.startswith("research-os.apodock001")


def test_adapter_resolves_bem_mav_with_explicit_chemical_invariants(bem_mav):
    result = adapt_apd010(*bem_mav)
    assert result.chemistry_ready is True
    assert result.diagnostics["formula"] == "C12H18O13"
    assert result.diagnostics["heavy_atoms"] == 25
    assert result.diagnostics["fragment_count"] == 1
    assert result.diagnostics["intercomponent_bond"]["order"] == "SING"
    assert result.diagnostics["intercomponent_bond"]["atom_a"] == ["BEM", "C1"]
    assert result.diagnostics["intercomponent_bond"]["atom_b"] == ["MAV", "O4"]


def test_adapter_is_deterministic_and_does_not_mutate_inputs(bem_mav):
    before = tuple(chemistry_identity(molecule) for molecule in bem_mav)
    first = adapt_apd010(*bem_mav)
    second = adapt_apd010(*bem_mav)
    assert first.input_identity == second.input_identity
    assert first.output_identity == second.output_identity
    assert first.to_dict() == second.to_dict()
    assert tuple(chemistry_identity(molecule) for molecule in bem_mav) == before


def test_operational_metadata_and_serialization_do_not_change_chemical_identity(bem_mav):
    result = adapt_apd010(*bem_mav)
    original_identity = chemistry_identity(result.molecule)
    result.molecule.SetProp("operational_timestamp", "2099-01-01T00:00:00Z")
    result.molecule.SetProp("serialization_format", "test-only")
    round_trip = Chem.MolFromSmiles(Chem.MolToSmiles(result.molecule, canonical=True, isomericSmiles=True))
    assert round_trip is not None
    assert chemistry_identity(result.molecule) == original_identity
    assert chemistry_identity(round_trip) == original_identity


def test_coordinate_mapping_reports_only_the_known_missing_bem_o4(bem_mav):
    result = adapt_apd010(*bem_mav)
    observed = {
        NamedAtomKey(atom.GetProp("research_os_component_id"), atom.GetProp("research_os_atom_name"))
        for atom in result.molecule.GetAtoms()
    }
    observed.remove(NamedAtomKey("BEM", "O4"))
    diagnostic = coordinate_mapping_diagnostic(result.molecule, observed)
    assert diagnostic["missing_coordinate_keys"] == [["BEM", "O4"]]
    assert diagnostic["observed_heavy_atoms"] == 24
    assert diagnostic["starting_conformer_generated"] is False


def test_invalid_or_wrong_compound_fails_closed(bem_mav):
    bem, mav = bem_mav
    wrong = Chem.Mol(mav)
    for atom in wrong.GetAtoms():
        atom.SetProp("research_os_component_id", "WRONG")
    with pytest.raises(APD010ChemistryError):
        adapt_apd010(bem, wrong)

    invalid = Chem.RWMol(bem)
    invalid.AddAtom(Chem.Atom("N"))
    with pytest.raises(APD010ChemistryError):
        adapt_apd010(invalid.GetMol(), mav)

    fragmented = Chem.CombineMols(bem, Chem.MolFromSmiles("CO"))
    with pytest.raises(APD010ChemistryError):
        adapt_apd010(fragmented, mav)


def test_mol2_is_not_an_implicit_fallback():
    with pytest.raises(APD010ChemistryError):
        load_named_ccd_mol2("not-a-real-file.mol2", "BEM")


def test_chemical_change_changes_identity(bem_mav):
    result = adapt_apd010(*bem_mav)
    changed = Chem.MolFromSmiles("CCO")
    assert changed is not None
    assert chemistry_identity(changed) != result.output_identity


def test_only_correct_adaptation_moves_apodock_cohort_from_nine_to_ten(bem_mav):
    direct_case_ids = [
        record["case_id"]
        for record in apodock001_freeze.FROZEN_STRUCTURAL_IDENTITIES
        if record["chemistry_ready_for_vina"]
    ]
    result = adapt_apd010(*bem_mav)
    chemistry_ready_case_ids = direct_case_ids + ["APD-010"] if result.chemistry_ready else direct_case_ids
    assert len(direct_case_ids) == 9
    assert chemistry_ready_case_ids == [f"APD-{index:03d}" for index in range(1, 11)]
