from __future__ import annotations

import numpy as np

try:
    from rdkit import Chem, DataStructs
    from rdkit.Chem import rdFingerprintGenerator
except ImportError as exc:
    Chem = None
    DataStructs = None
    rdFingerprintGenerator = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class MorganFeaturizer:
    """ML-only molecular representation kept separate from deterministic properties."""

    schema_id = "MOL-MORGAN-R2-2048-v1"

    def __init__(self, radius: int = 2, n_bits: int = 2048):
        self.radius = radius
        self.n_bits = n_bits

    def transform_one(self, smiles: str) -> np.ndarray:
        if Chem is None:
            raise RuntimeError("RDKit unavailable") from _IMPORT_ERROR
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"invalid SMILES: {smiles!r}")
        generator = rdFingerprintGenerator.GetMorganGenerator(radius=self.radius, fpSize=self.n_bits)
        fp = generator.GetFingerprint(mol)
        arr = np.zeros((self.n_bits,), dtype=np.uint8)
        DataStructs.ConvertToNumpyArray(fp, arr)
        return arr
