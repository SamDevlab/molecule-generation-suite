"""Deterministic APD-010 BEM/MAV chemical adapter.

The adapter consumes the two named RCSB CCD ideal SDF graphs and their CCD
CIF atom/bond definitions.  The PDB is used only for a coordinate-mapping
diagnostic; no PDB geometry is used to invent the chemical graph.

This module has no docking dependency and never creates a PDBQT, conformer,
score, pose, or Vina invocation.  All mutations happen on private RDKit
copies.  A failed check raises :class:`APD010ChemistryError` rather than
falling back to a best-effort molecule.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shlex
from typing import Any, Iterable, Mapping

try:
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors
except ImportError as exc:  # pragma: no cover - exercised in dependency-gated environments
    Chem = None
    rdMolDescriptors = None
    _RDKIT_IMPORT_ERROR = exc
else:
    _RDKIT_IMPORT_ERROR = None

from research_os.core.hashing import sha256_file, sha256_json


ADAPTER_ID = "research-os.apd010.bem-mav"
ADAPTER_VERSION = "1.0.0"
MOLECULE_ID = "APD-010"
CHEMISTRY_GATE_ID = "research-os.apodock001.chemistry-gate"
CHEMISTRY_GATE_VERSION = "1.0.0"

BEM_COMPONENT_ID = "BEM"
MAV_COMPONENT_ID = "MAV"
BEM_LEAVING_ATOM = "O1"
BEM_LINK_ATOM = "C1"
MAV_LINK_ATOM = "O4"
EXPECTED_FORMULA = "C12H18O13"
EXPECTED_HEAVY_ATOMS = 25
EXPECTED_COMPONENT_FORMULA = "C6H10O7"
EXPECTED_CRYSTAL_MISSING = ("BEM", "O4")
SUPPORTED_ELEMENTS = frozenset({"C", "O"})

BEM_HEAVY_ATOM_NAMES = frozenset(
    {"C1", "C2", "O2", "C3", "O3", "C4", "O4", "C5", "O5", "C6", "O6A", "O6B", "O1"}
)
MAV_HEAVY_ATOM_NAMES = frozenset(
    {"C1", "O1", "C2", "O2", "C3", "O3", "C4", "O4", "C5", "O5", "C6", "O6A", "O6B"}
)

# These hashes are part of the adapter input contract.  If RCSB changes the
# bytes behind an endpoint, the preflight must stop instead of silently using
# a new chemical source.
CCD_SOURCES: Mapping[str, Mapping[str, str]] = {
    "BEM": {
        "sdf_url": "https://files.rcsb.org/ligands/download/BEM_ideal.sdf",
        "sdf_sha256": "0c2d5387285bb068a89b226bbc5bc7ce086e47d1474a99a54439700bddaebda6",
        "cif_url": "https://files.rcsb.org/ligands/download/BEM.cif",
        "cif_sha256": "3a27261ff1b78bf232392277cceb3c0b9c8e7c8ff0b5eafccaa70068c10c396f",
    },
    "MAV": {
        "sdf_url": "https://files.rcsb.org/ligands/download/MAV_ideal.sdf",
        "sdf_sha256": "84f154b100861fb9131e5cb7fb0a9b25be289529b0e852bb741e653bcd3340b9",
        "cif_url": "https://files.rcsb.org/ligands/download/MAV.cif",
        "cif_sha256": "7c848be1fef6660ce7fe67c93141669cf073ea71fb5b740b92ed3e257e4c410e",
    },
}


class APD010ChemistryError(ValueError):
    """Raised for any APD-010 chemistry-gate violation."""


@dataclass(frozen=True, order=True)
class NamedAtomKey:
    component_id: str
    atom_name: str

    def as_tuple(self) -> tuple[str, str]:
        return self.component_id, self.atom_name


@dataclass(frozen=True)
class CCDAtomRecord:
    component_id: str
    atom_name: str
    element: str
    charge: int
    leaving_atom_flag: str
    ideal_xyz: tuple[float, float, float]


@dataclass(frozen=True)
class APD010AdaptationResult:
    molecule: Any
    input_identity: str
    output_identity: str
    adapter_id: str
    adapter_version: str
    transformations: tuple[str, ...]
    diagnostics: Mapping[str, Any]
    chemistry_ready: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "molecule_id": MOLECULE_ID,
            "input_identity": self.input_identity,
            "output_identity": self.output_identity,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "transformations": list(self.transformations),
            "diagnostics": dict(self.diagnostics),
            "chemistry_ready": self.chemistry_ready,
        }


def _require_rdkit() -> None:
    if Chem is None:
        raise APD010ChemistryError(
            "RDKit is required for the APD-010 chemical gate; install the 'molecule' optional dependencies"
        ) from _RDKIT_IMPORT_ERROR


def _parse_cif_loop(path: str | Path, prefix: str) -> tuple[dict[str, str], ...]:
    """Read one simple CCD loop without relying on a CIF package.

    RCSB CCD atom/bond loops are whitespace-tokenized after shell-style quote
    removal.  The parser rejects wrapped/incomplete rows instead of guessing.
    """

    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "loop_":
            continue
        header_index = index + 1
        headers: list[str] = []
        while header_index < len(lines) and lines[header_index].strip().startswith(prefix):
            headers.append(lines[header_index].strip())
            header_index += 1
        if not headers:
            continue
        rows: list[dict[str, str]] = []
        tokens: list[str] = []
        row_index = header_index
        while row_index < len(lines):
            stripped = lines[row_index].strip()
            if not stripped or stripped.startswith("#"):
                if tokens:
                    raise APD010ChemistryError(f"wrapped CCD row in {path}")
                if stripped.startswith("#"):
                    break
                row_index += 1
                continue
            if stripped == "loop_" or stripped.startswith("_"):
                break
            tokens.extend(shlex.split(stripped, posix=True))
            while len(tokens) >= len(headers):
                row_tokens = tokens[: len(headers)]
                tokens = tokens[len(headers) :]
                rows.append(dict(zip(headers, row_tokens)))
            row_index += 1
        if tokens:
            raise APD010ChemistryError(f"incomplete CCD loop in {path}")
        return tuple(rows)
    raise APD010ChemistryError(f"CCD loop {prefix!r} not found in {path}")


def _cif_atom_records(path: str | Path, component_id: str) -> tuple[CCDAtomRecord, ...]:
    rows = _parse_cif_loop(path, "_chem_comp_atom.")
    records: list[CCDAtomRecord] = []
    for row in rows:
        if row["_chem_comp_atom.comp_id"] != component_id:
            raise APD010ChemistryError(f"mixed component IDs in CCD atom loop: {path}")
        try:
            charge = int(float(row["_chem_comp_atom.charge"]))
            ideal_xyz = tuple(
                float(row[f"_chem_comp_atom.pdbx_model_Cartn_{axis}_ideal"])
                for axis in ("x", "y", "z")
            )
        except (KeyError, ValueError) as exc:
            raise APD010ChemistryError(f"invalid CCD atom record in {path}: {row}") from exc
        records.append(
            CCDAtomRecord(
                component_id=component_id,
                atom_name=row["_chem_comp_atom.atom_id"],
                element=row["_chem_comp_atom.type_symbol"].upper(),
                charge=charge,
                leaving_atom_flag=row["_chem_comp_atom.pdbx_leaving_atom_flag"],
                ideal_xyz=ideal_xyz,
            )
        )
    if not records or len({record.atom_name for record in records}) != len(records):
        raise APD010ChemistryError(f"CCD atom names are missing or duplicated in {path}")
    return tuple(records)


def _cif_bond_records(path: str | Path, component_id: str) -> tuple[tuple[str, str, str], ...]:
    rows = _parse_cif_loop(path, "_chem_comp_bond.")
    bonds: list[tuple[str, str, str]] = []
    for row in rows:
        if row["_chem_comp_bond.comp_id"] != component_id:
            raise APD010ChemistryError(f"mixed component IDs in CCD bond loop: {path}")
        bonds.append(
            (
                row["_chem_comp_bond.atom_id_1"],
                row["_chem_comp_bond.atom_id_2"],
                row["_chem_comp_bond.value_order"],
            )
        )
    if not bonds:
        raise APD010ChemistryError(f"CCD bond loop is empty in {path}")
    return tuple(bonds)


def _bond_type_name(bond: Any) -> str:
    return {
        Chem.BondType.SINGLE: "SING",
        Chem.BondType.DOUBLE: "DOUB",
        Chem.BondType.TRIPLE: "TRIP",
        Chem.BondType.AROMATIC: "AROM",
    }.get(bond.GetBondType(), "UNKNOWN")


def _controlled_sanitize(mol: Any, *, context: str) -> Any:
    _require_rdkit()
    private = Chem.Mol(mol)
    result = Chem.SanitizeMol(
        private,
        sanitizeOps=Chem.SanitizeFlags.SANITIZE_ALL,
        catchErrors=True,
    )
    if result != Chem.SanitizeFlags.SANITIZE_NONE:
        raise APD010ChemistryError(f"controlled sanitization failed for {context}: {result}")
    return private


def _remove_conformers(mol: Any) -> Any:
    mol.RemoveAllConformers()
    return mol


def _atom_key(atom: Any) -> NamedAtomKey:
    try:
        return NamedAtomKey(atom.GetProp("research_os_component_id"), atom.GetProp("research_os_atom_name"))
    except KeyError as exc:
        raise APD010ChemistryError("molecule atom is missing the CCD identity mapping") from exc


def _atom_index(mol: Any, key: NamedAtomKey) -> int:
    matches = [atom.GetIdx() for atom in mol.GetAtoms() if _atom_key(atom) == key]
    if len(matches) != 1:
        raise APD010ChemistryError(f"expected exactly one mapped atom for {key}: found {len(matches)}")
    return matches[0]


def _validate_component(mol: Any, component_id: str) -> None:
    _require_rdkit()
    expected_names = BEM_HEAVY_ATOM_NAMES if component_id == BEM_COMPONENT_ID else MAV_HEAVY_ATOM_NAMES
    if len(Chem.GetMolFrags(mol, asMols=False, sanitizeFrags=False)) != 1:
        raise APD010ChemistryError(f"{component_id} input is unexpectedly fragmented")
    if mol.GetNumHeavyAtoms() != 13:
        raise APD010ChemistryError(f"{component_id} input must contain 13 heavy atoms")
    formula = rdMolDescriptors.CalcMolFormula(mol)
    if formula != EXPECTED_COMPONENT_FORMULA:
        raise APD010ChemistryError(f"{component_id} input formula changed: {formula}")
    observed_names: set[str] = set()
    for atom in mol.GetAtoms():
        if atom.GetSymbol() == "H":
            continue
        if atom.GetSymbol() not in SUPPORTED_ELEMENTS:
            raise APD010ChemistryError(f"unsupported {component_id} element: {atom.GetSymbol()}")
        if atom.GetAtomicNum() == 0:
            raise APD010ChemistryError(f"dummy atom in {component_id} input")
        key = _atom_key(atom)
        if key.component_id != component_id or key.atom_name in observed_names:
            raise APD010ChemistryError(f"invalid or duplicate {component_id} atom mapping: {key}")
        observed_names.add(key.atom_name)
    if observed_names != expected_names:
        raise APD010ChemistryError(
            f"{component_id} CCD atom inventory changed: {sorted(observed_names)}"
        )
    if Chem.GetFormalCharge(mol) != 0:
        raise APD010ChemistryError(f"{component_id} formal charge is not zero")


def load_named_ccd_sdf(
    sdf_path: str | Path,
    cif_path: str | Path,
    component_id: str,
    *,
    expected_sdf_sha256: str | None = None,
    expected_cif_sha256: str | None = None,
) -> Any:
    """Load an RCSB CCD ideal SDF and verify it against its CCD CIF."""

    _require_rdkit()
    if component_id not in {BEM_COMPONENT_ID, MAV_COMPONENT_ID}:
        raise APD010ChemistryError(f"unsupported APD-010 component: {component_id}")
    if expected_sdf_sha256 and sha256_file(sdf_path) != expected_sdf_sha256:
        raise APD010ChemistryError(f"unexpected {component_id} SDF source hash")
    if expected_cif_sha256 and sha256_file(cif_path) != expected_cif_sha256:
        raise APD010ChemistryError(f"unexpected {component_id} CIF source hash")

    records = _cif_atom_records(cif_path, component_id)
    cif_bonds = _cif_bond_records(cif_path, component_id)
    raw = Chem.MolFromMolFile(str(sdf_path), sanitize=False, removeHs=False)
    if raw is None:
        raise APD010ChemistryError(f"unable to parse {component_id} ideal SDF")
    if raw.GetNumAtoms() != len(records):
        raise APD010ChemistryError(f"{component_id} SDF/CIF atom counts differ")

    # Coordinate matching is only a source-consistency check.  Coordinates are
    # discarded before the molecule leaves this function.
    used_records: set[int] = set()
    for atom in raw.GetAtoms():
        position = raw.GetConformer().GetAtomPosition(atom.GetIdx())
        candidates = [
            index
            for index, record in enumerate(records)
            if index not in used_records
            and record.element == atom.GetSymbol().upper()
            and max(
                abs(position.x - record.ideal_xyz[0]),
                abs(position.y - record.ideal_xyz[1]),
                abs(position.z - record.ideal_xyz[2]),
            ) <= 0.001
        ]
        if len(candidates) != 1:
            raise APD010ChemistryError(
                f"{component_id} SDF/CIF ideal-coordinate mapping is not unique for atom {atom.GetIdx()}"
            )
        record = records[candidates[0]]
        used_records.add(candidates[0])
        atom.SetProp("research_os_component_id", component_id)
        atom.SetProp("research_os_atom_name", record.atom_name)
        atom.SetProp("research_os_leaving_atom_flag", record.leaving_atom_flag)
        atom.SetIntProp("research_os_ccd_charge", record.charge)
        if atom.GetFormalCharge() != record.charge:
            raise APD010ChemistryError(
                f"{component_id} SDF/CIF formal charge differs for {record.atom_name}"
            )

    observed_bonds = {
        tuple(sorted((_atom_key(bond.GetBeginAtom()).atom_name, _atom_key(bond.GetEndAtom()).atom_name)))
        + (_bond_type_name(bond),)
        for bond in raw.GetBonds()
    }
    expected_bonds = {
        tuple(sorted((first, second))) + ({"SING": "SING", "DOUB": "DOUB", "TRIP": "TRIP", "AROM": "AROM"}[order],)
        for first, second, order in cif_bonds
    }
    if observed_bonds != expected_bonds:
        raise APD010ChemistryError(f"{component_id} SDF/CIF bond graph differs")

    sanitized = _controlled_sanitize(raw, context=f"{component_id} CCD input")
    no_hydrogens = Chem.RemoveHs(sanitized)
    no_hydrogens = _remove_conformers(no_hydrogens)
    _validate_component(no_hydrogens, component_id)
    return no_hydrogens


def load_named_ccd_mol2(path: str | Path, component_id: str) -> Any:
    """Compatibility guard: APD-010 does not accept unverified MOL2 input."""

    raise APD010ChemistryError(
        "APD-010 requires a CCD SDF plus matching CCD CIF; unverified MOL2 is rejected"
    )


def _chemical_identity_payload(mol: Any) -> dict[str, Any]:
    _require_rdkit()
    checked = _controlled_sanitize(mol, context="chemical identity")
    if len(Chem.GetMolFrags(checked)) != 1:
        raise APD010ChemistryError("chemical identity cannot represent a fragmented molecule")
    formula = rdMolDescriptors.CalcMolFormula(checked)
    canonical_smiles = Chem.MolToSmiles(checked, canonical=True, isomericSmiles=True)
    return {
        "formula": formula,
        "heavy_atoms": checked.GetNumHeavyAtoms(),
        "formal_charge": Chem.GetFormalCharge(checked),
        "canonical_isomeric_smiles": canonical_smiles,
    }


def chemistry_identity(mol: Any) -> str:
    """Hash only chemical graph information; omit names, coordinates and metadata."""

    return sha256_json(_chemical_identity_payload(mol))


def chemical_identity_payload(mol: Any) -> dict[str, Any]:
    return _chemical_identity_payload(mol)


def assemble_apd010_disaccharide(bem: Any, mav: Any) -> Any:
    """Remove BEM O1 and add the explicit BEM C1--MAV O4 glycosidic bond."""

    _require_rdkit()
    _validate_component(bem, BEM_COMPONENT_ID)
    _validate_component(mav, MAV_COMPONENT_ID)
    bem_copy = Chem.Mol(bem)
    mav_copy = Chem.Mol(mav)
    leaving_index = _atom_index(bem_copy, NamedAtomKey(BEM_COMPONENT_ID, BEM_LEAVING_ATOM))
    leaving_atom = bem_copy.GetAtomWithIdx(leaving_index)
    if leaving_atom.GetProp("research_os_leaving_atom_flag") != "Y":
        raise APD010ChemistryError("BEM O1 is not declared as a CCD leaving atom")

    rw_bem = Chem.RWMol(bem_copy)
    rw_bem.RemoveAtom(leaving_index)
    bem_reduced = _controlled_sanitize(rw_bem.GetMol(), context="BEM leaving-atom removal")
    combined = Chem.CombineMols(bem_reduced, mav_copy)
    rw = Chem.RWMol(combined)
    bem_c1 = _atom_index(rw, NamedAtomKey(BEM_COMPONENT_ID, BEM_LINK_ATOM))
    mav_o4 = _atom_index(rw, NamedAtomKey(MAV_COMPONENT_ID, MAV_LINK_ATOM))
    if rw.GetBondBetweenAtoms(bem_c1, mav_o4) is not None:
        raise APD010ChemistryError("BEM C1--MAV O4 bond already exists")
    rw.AddBond(bem_c1, mav_o4, Chem.BondType.SINGLE)
    assembled = _controlled_sanitize(rw.GetMol(), context="BEM/MAV covalent assembly")
    assembled = _remove_conformers(assembled)
    assembled.SetProp("research_os_adapter_id", ADAPTER_ID)
    assembled.SetProp("research_os_adapter_version", ADAPTER_VERSION)
    assembled.SetProp("research_os_transformation", "remove BEM O1; add single BEM C1-MAV O4")
    return assembled


def validate_apd010_chemistry(mol: Any) -> dict[str, Any]:
    """Validate the complete fail-closed APD-010 chemical gate."""

    _require_rdkit()
    checked = _controlled_sanitize(mol, context="APD-010 output")
    if len(Chem.GetMolFrags(checked)) != 1:
        raise APD010ChemistryError("APD-010 output is fragmented")
    if checked.GetNumHeavyAtoms() != EXPECTED_HEAVY_ATOMS:
        raise APD010ChemistryError(f"APD-010 heavy-atom count is {checked.GetNumHeavyAtoms()}, expected 25")
    if checked.GetNumConformers() != 0:
        raise APD010ChemistryError("APD-010 chemical output must not carry a conformer")
    formula = rdMolDescriptors.CalcMolFormula(checked)
    if formula != EXPECTED_FORMULA:
        raise APD010ChemistryError(f"APD-010 formula is {formula}, expected {EXPECTED_FORMULA}")
    if Chem.GetFormalCharge(checked) != 0:
        raise APD010ChemistryError("APD-010 formal charge is not zero")

    seen_keys: set[NamedAtomKey] = set()
    for atom in checked.GetAtoms():
        if atom.GetAtomicNum() == 0:
            raise APD010ChemistryError("APD-010 output contains a dummy atom")
        if atom.GetSymbol() not in SUPPORTED_ELEMENTS:
            raise APD010ChemistryError(f"unsupported APD-010 output element: {atom.GetSymbol()}")
        if atom.GetIsAromatic():
            raise APD010ChemistryError("unexpected aromatic APD-010 atom")
        key = _atom_key(atom)
        if key in seen_keys:
            raise APD010ChemistryError(f"duplicate APD-010 atom mapping: {key}")
        seen_keys.add(key)
    expected_keys = {
        NamedAtomKey(BEM_COMPONENT_ID, name) for name in BEM_HEAVY_ATOM_NAMES - {BEM_LEAVING_ATOM}
    } | {NamedAtomKey(MAV_COMPONENT_ID, name) for name in MAV_HEAVY_ATOM_NAMES}
    if seen_keys != expected_keys:
        raise APD010ChemistryError("APD-010 output atom inventory is not the declared BEM/MAV inventory")

    intercomponent_bonds: list[tuple[NamedAtomKey, NamedAtomKey, str]] = []
    for bond in checked.GetBonds():
        if bond.GetIsAromatic() or _bond_type_name(bond) not in {"SING", "DOUB"}:
            raise APD010ChemistryError("unsupported or aromatic APD-010 bond order")
        first = _atom_key(bond.GetBeginAtom())
        second = _atom_key(bond.GetEndAtom())
        if first.component_id != second.component_id:
            intercomponent_bonds.append((first, second, _bond_type_name(bond)))
    if len(intercomponent_bonds) != 1:
        raise APD010ChemistryError("APD-010 must have exactly one inter-component bond")
    first, second, bond_order = intercomponent_bonds[0]
    if {first, second} != {
        NamedAtomKey(BEM_COMPONENT_ID, BEM_LINK_ATOM),
        NamedAtomKey(MAV_COMPONENT_ID, MAV_LINK_ATOM),
    } or bond_order != "SING":
        raise APD010ChemistryError("APD-010 inter-component bond is not BEM C1--MAV O4 single")

    return {
        "formula": formula,
        "heavy_atoms": checked.GetNumHeavyAtoms(),
        "formal_charge": Chem.GetFormalCharge(checked),
        "fragment_count": len(Chem.GetMolFrags(checked)),
        "intercomponent_bond": {
            "atom_a": list(first.as_tuple()),
            "atom_b": list(second.as_tuple()),
            "order": bond_order,
        },
        "dummy_atoms": 0,
        "unexpected_elements": [],
        "aromatic_atoms": 0,
    }


def coordinate_mapping_diagnostic(mol: Any, observed_keys: Iterable[NamedAtomKey]) -> dict[str, Any]:
    """Compare adapted heavy-atom names with the PDB inventory.

    The known APD-010 source is expected to lack BEM O4 in the remediated
    experimental inventory.  That missing coordinate is reported explicitly;
    it is not fabricated by the chemical adapter.
    """

    # The PDB inventory is compared with the adapted heavy-atom graph.  BEM O1
    # is intentionally absent because the adapter removed that CCD-declared
    # leaving atom; BEM O4 is the only accepted missing coordinate.
    expected = {_atom_key(atom) for atom in mol.GetAtoms()}
    observed = set(observed_keys)
    missing = sorted(expected - observed)
    unexpected = sorted(observed - expected)
    if tuple(key.as_tuple() for key in missing) != (EXPECTED_CRYSTAL_MISSING,):
        raise APD010ChemistryError(f"unexpected APD-010 coordinate mapping missing keys: {missing}")
    if unexpected:
        raise APD010ChemistryError(f"unexpected APD-010 coordinate mapping keys: {unexpected}")
    return {
        "expected_heavy_atoms": len(expected),
        "observed_heavy_atoms": len(observed),
        "missing_coordinate_keys": [list(key.as_tuple()) for key in missing],
        "unexpected_coordinate_keys": [],
        "adapter_removed_source_keys": [[BEM_COMPONENT_ID, BEM_LEAVING_ATOM]],
        "starting_conformer_generated": False,
    }


def adapt_apd010(
    bem: Any,
    mav: Any,
    *,
    source_hashes: Mapping[str, str] | None = None,
    observed_keys: Iterable[NamedAtomKey] | None = None,
) -> APD010AdaptationResult:
    """Apply the APD-010 adapter deterministically and return provenance."""

    _require_rdkit()
    _validate_component(bem, BEM_COMPONENT_ID)
    _validate_component(mav, MAV_COMPONENT_ID)
    input_identity = sha256_json(
        {
            "BEM": chemistry_identity(bem),
            "MAV": chemistry_identity(mav),
        }
    )
    assembled = assemble_apd010_disaccharide(bem, mav)
    diagnostics = validate_apd010_chemistry(assembled)
    if observed_keys is not None:
        diagnostics = {**diagnostics, "coordinate_mapping": coordinate_mapping_diagnostic(assembled, observed_keys)}
    diagnostics = {
        **diagnostics,
        "source_hashes": dict(sorted((source_hashes or {}).items())),
        "input_components": [BEM_COMPONENT_ID, MAV_COMPONENT_ID],
    }
    return APD010AdaptationResult(
        molecule=assembled,
        input_identity=input_identity,
        output_identity=chemistry_identity(assembled),
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        transformations=(
            "load BEM and MAV from RCSB CCD ideal SDF plus matching CCD CIF",
            "normalize validated explicit CCD hydrogens to implicit valence; no protonation heuristic",
            "remove CCD-declared BEM O1 leaving atom",
            "add one single covalent bond BEM C1--MAV O4",
            "controlled RDKit sanitization with fail-closed validation",
            "discard conformers; retain chemical graph only",
        ),
        diagnostics=diagnostics,
        chemistry_ready=True,
    )


def adapter_report_identity(report: Mapping[str, Any]) -> str:
    """Hash only the scientific gate report, excluding operational metadata."""

    scientific = {
        key: value
        for key, value in report.items()
        if key not in {"generated_at", "runtime", "serialization", "operational_metadata"}
    }
    return hashlib.sha256(json.dumps(scientific, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
