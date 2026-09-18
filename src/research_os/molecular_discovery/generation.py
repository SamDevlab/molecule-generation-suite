"""Bounded candidate generators for the Molecular Discovery vertical.

Generation is a candidate-source operation, not scientific evidence of activity.
Generated structures are E0_HEURISTIC until evaluated by downstream capabilities.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from research_os.core.hashing import sha256_json


GENERATOR_ID = "research-os.molecular-discovery.halogen-single-substitution.v1"
_HALOGENS = {"F": 9, "Cl": 17, "Br": 35}
_DEFAULT_REPLACEMENTS: Mapping[str, tuple[str, ...]] = {
    "F": ("Cl", "Br"),
    "Cl": ("F", "Br"),
    "Br": ("F", "Cl"),
}


class MolecularGenerationError(RuntimeError):
    """Fail-closed error for invalid generator inputs or missing chemistry capabilities."""


@dataclass(frozen=True)
class GeneratedCandidate:
    candidate_id: str
    smiles: str
    parent_id: str
    parent_smiles: str
    atom_index: int
    from_element: str
    to_element: str
    generator_id: str = GENERATOR_ID
    evidence_level: str = "E0_HEURISTIC"

    @property
    def generation_hash(self) -> str:
        return sha256_json(self._payload())

    def _payload(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "smiles": self.smiles,
            "parent_id": self.parent_id,
            "parent_smiles": self.parent_smiles,
            "atom_index": self.atom_index,
            "from_element": self.from_element,
            "to_element": self.to_element,
            "generator_id": self.generator_id,
            "evidence_level": self.evidence_level,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "generation_hash": self.generation_hash}

    def to_workflow_candidate(self) -> dict[str, Any]:
        return {
            "id": self.candidate_id,
            "name": f"{self.parent_id} {self.from_element}->{self.to_element} atom {self.atom_index}",
            "smiles": self.smiles,
            "origin": {
                "source_type": "heuristic_generation",
                "evidence_level": self.evidence_level,
                "generator_id": self.generator_id,
                "parent_id": self.parent_id,
                "parent_smiles": self.parent_smiles,
                "operation": "single_halogen_substitution",
                "atom_index": self.atom_index,
                "from_element": self.from_element,
                "to_element": self.to_element,
                "generation_hash": self.generation_hash,
            },
        }


@dataclass(frozen=True)
class GenerationReport:
    generator_id: str
    parent_id: str
    parent_smiles: str
    candidate_count: int
    candidates: tuple[GeneratedCandidate, ...]
    limitations: tuple[str, ...]

    @property
    def scientific_hash(self) -> str:
        return sha256_json(
            {
                "generator_id": self.generator_id,
                "parent_id": self.parent_id,
                "parent_smiles": self.parent_smiles,
                "candidates": [candidate.to_dict() for candidate in self.candidates],
                "limitations": list(self.limitations),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "generator_id": self.generator_id,
            "parent_id": self.parent_id,
            "parent_smiles": self.parent_smiles,
            "candidate_count": self.candidate_count,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "limitations": list(self.limitations),
            "scientific_hash": self.scientific_hash,
        }


def _rdkit():
    try:
        from rdkit import Chem
    except ImportError as exc:
        raise MolecularGenerationError(
            "molecular generation requires RDKit; install the 'discovery' extra"
        ) from exc
    return Chem


def _canonical(smiles: str) -> str:
    Chem = _rdkit()
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise MolecularGenerationError(f"invalid or unsanitizable seed SMILES: {smiles!r}")
    return Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)


def generate_halogen_analogs(
    seed_smiles: str,
    *,
    seed_id: str,
    replacements: Mapping[str, Sequence[str]] | None = None,
    max_candidates: int = 32,
) -> GenerationReport:
    """Enumerate deterministic single-halogen substitutions.

    Exactly one F/Cl/Br atom is replaced per generated molecule. Connectivity is
    otherwise unchanged. Products are sanitized, canonicalized, deduplicated and
    sorted by canonical SMILES before deterministic IDs are assigned.
    """
    if max_candidates < 1:
        raise MolecularGenerationError("max_candidates must be positive")
    Chem = _rdkit()
    seed = Chem.MolFromSmiles(seed_smiles)
    if seed is None:
        raise MolecularGenerationError(f"invalid or unsanitizable seed SMILES: {seed_smiles!r}")
    canonical_seed = Chem.MolToSmiles(seed, canonical=True, isomericSmiles=True)
    rules = replacements or _DEFAULT_REPLACEMENTS

    raw: list[tuple[str, int, str, str]] = []
    for atom in seed.GetAtoms():
        source = atom.GetSymbol()
        if source not in rules:
            continue
        for target in rules[source]:
            if target == source:
                continue
            atomic_number = _HALOGENS.get(str(target))
            if atomic_number is None:
                raise MolecularGenerationError(
                    f"unsupported replacement element {target!r}; allowed values are F, Cl and Br"
                )
            editable = Chem.RWMol(seed)
            replacement = Chem.Atom(atomic_number)
            replacement.SetFormalCharge(atom.GetFormalCharge())
            editable.ReplaceAtom(atom.GetIdx(), replacement)
            product = editable.GetMol()
            try:
                Chem.SanitizeMol(product)
            except Exception:
                continue
            smiles = Chem.MolToSmiles(product, canonical=True, isomericSmiles=True)
            if smiles == canonical_seed:
                continue
            raw.append((smiles, atom.GetIdx(), source, str(target)))

    unique: dict[str, tuple[int, str, str]] = {}
    for smiles, atom_index, source, target in raw:
        unique.setdefault(smiles, (atom_index, source, target))

    candidates: list[GeneratedCandidate] = []
    for smiles in sorted(unique)[:max_candidates]:
        atom_index, source, target = unique[smiles]
        suffix = sha256_json(
            {
                "generator_id": GENERATOR_ID,
                "parent_id": seed_id,
                "parent_smiles": canonical_seed,
                "product_smiles": smiles,
                "atom_index": atom_index,
                "from": source,
                "to": target,
            }
        )[:10].upper()
        candidates.append(
            GeneratedCandidate(
                candidate_id=f"{seed_id}-GEN-{suffix}",
                smiles=smiles,
                parent_id=seed_id,
                parent_smiles=canonical_seed,
                atom_index=atom_index,
                from_element=source,
                to_element=target,
            )
        )

    if not candidates:
        raise MolecularGenerationError(
            "seed contains no supported F/Cl/Br substitution that yields a distinct valid molecule"
        )
    limitations = (
        "Generation is E0_HEURISTIC and provides candidate structures only.",
        "Single-halogen substitution does not establish synthetic accessibility, stability, binding, efficacy or safety.",
        "No docking score, solubility prediction or downstream metric is used to decide which analogs are generated.",
        "Only F/Cl/Br single-atom replacements are explored; the resulting neighborhood is intentionally narrow.",
    )
    return GenerationReport(
        generator_id=GENERATOR_ID,
        parent_id=seed_id,
        parent_smiles=canonical_seed,
        candidate_count=len(candidates),
        candidates=tuple(candidates),
        limitations=limitations,
    )


__all__ = [
    "GENERATOR_ID",
    "GeneratedCandidate",
    "GenerationReport",
    "MolecularGenerationError",
    "generate_halogen_analogs",
]
