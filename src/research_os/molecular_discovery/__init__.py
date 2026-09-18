"""Molecular Discovery vertical for Research OS 5.1.

The package composes existing Research OS capabilities. It is intentionally not
another orchestration layer.
"""

from research_os.molecular_discovery.generation import (
    GENERATOR_ID,
    GeneratedCandidate,
    GenerationReport,
    MolecularGenerationError,
    generate_halogen_analogs,
)
from research_os.molecular_discovery.moldisc001 import (
    MOLDISC001Result,
    MolecularDiscoveryProgramError,
    run_moldisc_001,
)
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
    "GENERATOR_ID",
    "GeneratedCandidate",
    "GenerationReport",
    "MOLDISC001Result",
    "MolecularDiscoveryProgramError",
    "MolecularGenerationError",
    "FrozenESOLSolubilityPredictor",
    "MolecularDiscoveryReport",
    "MolecularDiscoveryWorkflow",
    "SolubilityCapabilityError",
    "SolubilityPrediction",
    "generate_halogen_analogs",
    "run_moldisc_001",
]
