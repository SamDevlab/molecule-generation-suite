"""Deterministic mmCIF parsing backed by Gemmi.

The parser returns a normalized, provenance-carrying representation and never
guesses a ligand instance.  Ambiguous chains, malformed coordinates, missing
source integrity, or unsupported parser availability are explicit failures.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from research_os.core.hashing import sha256_file, sha256_json


class MmcifParseStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    SOURCE_NOT_REGISTERED = "SOURCE_NOT_REGISTERED"
    PARSER_UNAVAILABLE = "PARSER_UNAVAILABLE"


class MmcifParseError(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class CanonicalAtom:
    serial: int
    atom_name: str
    element: str
    x: float
    y: float
    z: float
    chain_id: str
    residue_name: str
    residue_number: int
    model_number: int
    entity_id: str | None
    altloc: str | None
    occupancy: float | None
    b_factor: float | None = None

    def __post_init__(self) -> None:
        if not self.atom_name.strip() or not self.element.strip():
            raise ValueError("canonical atom requires atom_name and element")
        if any(not isinstance(value, (int, float)) for value in (self.x, self.y, self.z)):
            raise ValueError("canonical atom coordinates must be numeric")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalLigand:
    component_id: str
    chain_id: str
    model_number: int
    residue_number: int
    entity_id: str | None
    atoms: tuple[CanonicalAtom, ...]

    def __post_init__(self) -> None:
        if not self.component_id.strip() or not self.atoms:
            raise ValueError("canonical ligand requires an ID and at least one atom")
        object.__setattr__(self, "atoms", tuple(self.atoms))

    @property
    def atom_count(self) -> int:
        return len(self.atoms)

    @property
    def ligand_hash(self) -> str:
        return sha256_json({"component_id": self.component_id, "chain_id": self.chain_id, "atoms": [item.to_dict() for item in self.atoms]})

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["atoms"] = [item.to_dict() for item in self.atoms]
        return data


@dataclass(frozen=True)
class CanonicalStructure:
    entry_id: str
    source_id: str | None
    source_path: str
    source_sha256: str
    parser: str
    parser_version: str
    model_count: int
    chain_ids: tuple[str, ...]
    ligand_components: tuple[str, ...]
    revision_dates: tuple[str, ...]
    resolution_angstrom: float | None
    atoms: tuple[CanonicalAtom, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    entity_info: tuple[Mapping[str, Any], ...] = ()
    chemical_components: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.entry_id or not self.source_sha256 or not self.atoms:
            raise ValueError("canonical structure is incomplete")
        object.__setattr__(self, "chain_ids", tuple(self.chain_ids))
        object.__setattr__(self, "ligand_components", tuple(self.ligand_components))
        object.__setattr__(self, "revision_dates", tuple(self.revision_dates))
        object.__setattr__(self, "atoms", tuple(self.atoms))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def select_ligand(self, component_id: str, *, chain_id: str | None = None, model_number: int = 1, altloc: str | None = None, require_resolved_altloc: bool = True) -> CanonicalLigand:
        if self.chemical_components and component_id not in self.chemical_components:
            raise MmcifParseError("CHEMICAL_COMPONENT_MISMATCH", f"component {component_id!r} is absent from the _chem_comp identity table")
        selected = [atom for atom in self.atoms if atom.model_number == model_number and atom.residue_name == component_id and (chain_id is None or atom.chain_id == chain_id)]
        groups = {(atom.chain_id, atom.residue_number, atom.entity_id) for atom in selected}
        if not selected:
            raise MmcifParseError("LIGAND_NOT_FOUND", f"component {component_id!r} was not found in model {model_number}")
        if len(groups) != 1:
            raise MmcifParseError("AMBIGUOUS_LIGAND_INSTANCE", f"component {component_id!r} has {len(groups)} candidate instances; declare chain_id")
        altlocs = {atom.altloc for atom in selected if atom.altloc}
        if altloc is not None:
            selected = [atom for atom in selected if atom.altloc in (None, altloc)]
        elif require_resolved_altloc and len(altlocs) > 1:
            raise MmcifParseError("ALTLOC_UNRESOLVED", f"component {component_id!r} has unresolved alternate locations: {sorted(altlocs)}")
        if not selected:
            raise MmcifParseError("ALTLOC_NOT_FOUND", f"requested alternate location {altloc!r} was not found")
        selected = sorted(selected, key=lambda item: (item.serial, item.atom_name, item.x, item.y, item.z))
        selected_group = next(iter(groups))
        return CanonicalLigand(component_id, selected_group[0], model_number, selected_group[1], selected_group[2], tuple(selected))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["chain_ids"] = list(self.chain_ids)
        data["ligand_components"] = list(self.ligand_components)
        data["revision_dates"] = list(self.revision_dates)
        data["atoms"] = [item.to_dict() for item in self.atoms]
        data["entity_info"] = [dict(item) for item in self.entity_info]
        data["chemical_components"] = list(self.chemical_components)
        return data


@dataclass(frozen=True)
class MmcifParseResult:
    status: MmcifParseStatus
    structure: CanonicalStructure | None
    error_code: str | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return self.status == MmcifParseStatus.VALID and self.structure is not None

    def require_valid(self) -> CanonicalStructure:
        if not self.valid:
            raise MmcifParseError(self.error_code or self.status.value, str(self.diagnostics.get("detail") or "mmCIF parse did not produce a valid structure"))
        return self.structure


def _category_rows(block: Any, prefix: str) -> list[dict[str, Any]]:
    category = block.get_mmcif_category(prefix) or {}
    if not category:
        return []
    keys = list(category)
    length = max((len(category[key]) for key in keys), default=0)
    return [{key: category[key][index] if index < len(category[key]) else None for key in keys} for index in range(length)]


def parse_mmcif(path: str | Path, *, source_id: str | None = None, source_registry: Any | None = None, require_registered_source: bool = False, require_single_model: bool = False) -> MmcifParseResult:
    """Parse one immutable local mmCIF artifact without network access."""

    target = Path(path)
    if not target.is_file():
        return MmcifParseResult(MmcifParseStatus.INVALID, None, "SOURCE_FILE_MISSING", {"detail": str(target)})
    source_hash = sha256_file(target)
    if require_registered_source and (source_registry is None or not source_id):
        return MmcifParseResult(MmcifParseStatus.SOURCE_NOT_REGISTERED, None, "SOURCE_NOT_REGISTERED", {"detail": "source_id and SourceRegistry are required"})
    if source_id and source_registry is not None:
        try:
            registered = source_registry.get(source_id)
        except KeyError:
            return MmcifParseResult(MmcifParseStatus.SOURCE_NOT_REGISTERED, None, "SOURCE_NOT_REGISTERED", {"detail": source_id})
        if not source_registry.verify_document(source_id, target):
            return MmcifParseResult(MmcifParseStatus.INVALID, None, "SOURCE_HASH_MISMATCH", {"detail": source_id, "registered_sha256": registered.document_hash, "actual_sha256": source_hash})
    try:
        import gemmi
    except ImportError:
        return MmcifParseResult(MmcifParseStatus.PARSER_UNAVAILABLE, None, "GEMMI_UNAVAILABLE", {"detail": "install the structure parser dependency"})
    try:
        document = gemmi.cif.read_file(str(target))
        if len(document) != 1:
            raise MmcifParseError("BLOCK_COUNT", "exactly one mmCIF data block is required")
        block = document[0]
        atom_rows = _category_rows(block, "_atom_site.")
        for row in atom_rows:
            if any(row.get(key) in (None, "?", ".") for key in ("Cartn_x", "Cartn_y", "Cartn_z")):
                raise MmcifParseError("MISSING_COORDINATE", "every atom_site row must provide Cartn_x, Cartn_y and Cartn_z")
        structure = gemmi.read_structure(str(target))
        if len(structure) == 0:
            raise MmcifParseError("NO_MODELS", "mmCIF contains no coordinate model")
        if require_single_model and len(structure) != 1:
            raise MmcifParseError("MULTIPLE_MODELS", f"protocol requires one model but source contains {len(structure)}")
        atoms: list[CanonicalAtom] = []
        for model in structure:
            model_number = int(model.num)
            for chain in model:
                for residue in chain:
                    for atom in residue:
                        if not all(float(value) == float(value) for value in (atom.pos.x, atom.pos.y, atom.pos.z)):
                            raise MmcifParseError("INVALID_COORDINATE", "NaN coordinate encountered")
                        atoms.append(CanonicalAtom(int(atom.serial), atom.name.strip(), atom.element.name.strip().upper(), float(atom.pos.x), float(atom.pos.y), float(atom.pos.z), chain.name, residue.name.strip(), int(residue.seqid.num), model_number, residue.entity_id or None, None if atom.altloc in ("\x00", " ", "") else str(atom.altloc), float(atom.occ) if atom.occ == atom.occ else None, float(atom.b_iso) if atom.b_iso == atom.b_iso else None))
        if not atoms:
            raise MmcifParseError("NO_ATOMS", "mmCIF contains no atoms")
        revision_rows = _category_rows(block, "_pdbx_audit_revision_history.")
        revision_dates = tuple(sorted({str(row.get("revision_date")) for row in revision_rows if row.get("revision_date") not in (None, "?", ".")}))
        refine_rows = _category_rows(block, "_refine.")
        resolution = None
        for row in refine_rows:
            raw = row.get("ls_d_res_high")
            if raw not in (None, "?", "."):
                try:
                    resolution = float(raw)
                except (TypeError, ValueError):
                    pass
                break
        ligand_components = tuple(sorted({atom.residue_name for atom in atoms if atom.entity_id and not atom.residue_name in {"HOH", "WAT"}}))
        entity_info = tuple({key: value for key, value in row.items()} for row in _category_rows(block, "_entity."))
        chemical_components = tuple(sorted({str(row.get("id")) for row in _category_rows(block, "_chem_comp.") if row.get("id") not in (None, "?", ".")}))
        parsed = CanonicalStructure(block.name, source_id, str(target.resolve()), source_hash, "gemmi", str(gemmi.__version__), len(structure), tuple(sorted({atom.chain_id for atom in atoms})), ligand_components, revision_dates, resolution, tuple(sorted(atoms, key=lambda item: (item.model_number, item.chain_id, item.residue_number, item.serial, item.atom_name))), {"entry_id": block.name, "source_registered": bool(source_id and source_registry is not None), "source_revision": revision_dates[-1] if revision_dates else None}, entity_info, chemical_components)
        return MmcifParseResult(MmcifParseStatus.VALID, parsed, diagnostics={"atom_count": len(atoms), "model_count": len(structure)})
    except MmcifParseError as exc:
        return MmcifParseResult(MmcifParseStatus.INVALID, None, exc.code, {"detail": exc.detail})
    except Exception as exc:
        return MmcifParseResult(MmcifParseStatus.INVALID, None, "MMCIF_PARSE_ERROR", {"detail": f"{type(exc).__name__}: {exc}"})
