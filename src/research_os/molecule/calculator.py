from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

try:
    from rdkit import Chem, rdBase
    from rdkit.Chem import Crippen, Descriptors, Lipinski, QED, rdMolDescriptors
except ImportError as exc:
    Chem = None
    rdBase = None
    _RDKIT_IMPORT_ERROR = exc
else:
    _RDKIT_IMPORT_ERROR = None


class RDKitUnavailableError(RuntimeError):
    pass


class InvalidSmilesError(ValueError):
    pass


@dataclass(frozen=True)
class MolecularProperties:
    canonical_smiles: str
    molecular_weight: float
    exact_molecular_weight: float
    logp: float
    tpsa: float
    qed: float
    h_donors: int
    h_acceptors: int
    rotatable_bonds: int
    aromatic_rings: int
    fraction_csp3: float
    heavy_atoms: int
    formal_charge: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RDKitCalculator:
    """Deterministic molecular-property engine."""

    engine_name = "RDKit"

    @property
    def version(self) -> str | None:
        return getattr(rdBase, "rdkitVersion", None) if rdBase is not None else None

    def _mol(self, smiles: str):
        if Chem is None:
            raise RDKitUnavailableError("RDKit is not installed; install the 'molecule' optional dependencies") from _RDKIT_IMPORT_ERROR
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise InvalidSmilesError(f"invalid or unsanitizable SMILES: {smiles!r}")
        return mol

    def calculate(self, smiles: str) -> MolecularProperties:
        mol = self._mol(smiles)
        return MolecularProperties(
            canonical_smiles=Chem.MolToSmiles(mol, canonical=True),
            molecular_weight=float(Descriptors.MolWt(mol)),
            exact_molecular_weight=float(Descriptors.ExactMolWt(mol)),
            logp=float(Crippen.MolLogP(mol)),
            tpsa=float(rdMolDescriptors.CalcTPSA(mol)),
            qed=float(QED.qed(mol)),
            h_donors=int(Lipinski.NumHDonors(mol)),
            h_acceptors=int(Lipinski.NumHAcceptors(mol)),
            rotatable_bonds=int(Lipinski.NumRotatableBonds(mol)),
            aromatic_rings=int(rdMolDescriptors.CalcNumAromaticRings(mol)),
            fraction_csp3=float(rdMolDescriptors.CalcFractionCSP3(mol)),
            heavy_atoms=int(mol.GetNumHeavyAtoms()),
            formal_charge=int(Chem.GetFormalCharge(mol)),
        )
