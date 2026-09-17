"""Molecular Discovery vertical for Research OS 5.1.

The package composes existing Research OS capabilities. It is intentionally not
another orchestration layer.
"""

from research_os.molecular_discovery.solubility import (
    FrozenESOLSolubilityPredictor,
    SolubilityCapabilityError,
    SolubilityPrediction,
)
from research_os.molecular_discovery.workflow import (
    CandidateAssessment,
    MolecularDiscoveryReport,
    MolecularDiscoveryWorkflow,
)

__all__ = [
    "CandidateAssessment",
    "FrozenESOLSolubilityPredictor",
    "MolecularDiscoveryReport",
    "MolecularDiscoveryWorkflow",
    "SolubilityCapabilityError",
    "SolubilityPrediction",
]
