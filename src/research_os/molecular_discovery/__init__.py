"""Molecular Discovery vertical for Research OS 5.1.

The package composes existing Research OS capabilities. It is intentionally not
another orchestration layer.
"""

from research_os.molecular_discovery.aqsoldb_coverage import (
    AqSolDBCoverageError,
    AqSolDBCoverageReport,
    CandidateCoverage,
    run_public_aqsoldb_coverage,
)
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
from research_os.molecular_discovery.moldisc002 import (
    MOLDISC002Error,
    MOLDISC002Result,
    run_moldisc_002,
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
    "AqSolDBCoverageError",
    "AqSolDBCoverageReport",
    "CandidateAssessment",
    "CandidateCoverage",
    "GENERATOR_ID",
    "GeneratedCandidate",
    "GenerationReport",
    "MOLDISC001Result",
    "MOLDISC002Error",
    "MOLDISC002Result",
    "MolecularDiscoveryProgramError",
    "MolecularGenerationError",
    "FrozenESOLSolubilityPredictor",
    "MolecularDiscoveryReport",
    "MolecularDiscoveryWorkflow",
    "SolubilityCapabilityError",
    "SolubilityPrediction",
    "generate_halogen_analogs",
    "run_moldisc_001",
    "run_moldisc_002",
    "run_public_aqsoldb_coverage",
]
