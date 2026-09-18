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
from research_os.molecular_discovery.moldisc003 import (
    MOLDISC003Error,
    MOLDISC003Result,
    RCSBChemicalIdentity,
    SeedSelection,
    run_moldisc_003,
)
from research_os.molecular_discovery.moldisc004 import (
    MOLDISC004Error,
    MOLDISC004Result,
    MeasuredSolubilityAnchor,
    SeedCalibration,
    run_moldisc_004,
)
from research_os.molecular_discovery.moldisc005 import (
    GeneratedAnalogSelection,
    GeneratedNCTAnalog,
    MOLDISC005Error,
    MOLDISC005Result,
    generate_nct_n_alkyl_series,
    run_moldisc_005,
)
from research_os.molecular_discovery.moldisc006 import (
    MOLDISC006Error,
    MOLDISC006Result,
    run_moldisc_006,
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
    "GeneratedAnalogSelection",
    "GeneratedCandidate",
    "GeneratedNCTAnalog",
    "GenerationReport",
    "MOLDISC001Result",
    "MOLDISC006Error",
    "MOLDISC006Result",
    "MOLDISC002Error",
    "MOLDISC002Result",
    "MOLDISC003Error",
    "MOLDISC003Result",
    "MOLDISC004Error",
    "MOLDISC004Result",
    "MOLDISC005Error",
    "MOLDISC005Result",
    "MolecularDiscoveryProgramError",
    "MeasuredSolubilityAnchor",
    "MolecularGenerationError",
    "RCSBChemicalIdentity",
    "SeedCalibration",
    "SeedSelection",
    "FrozenESOLSolubilityPredictor",
    "MolecularDiscoveryReport",
    "MolecularDiscoveryWorkflow",
    "SolubilityCapabilityError",
    "SolubilityPrediction",
    "generate_halogen_analogs",
    "generate_nct_n_alkyl_series",
    "run_moldisc_001",
    "run_moldisc_006",
    "run_moldisc_002",
    "run_moldisc_003",
    "run_moldisc_004",
    "run_moldisc_005",
    "run_public_aqsoldb_coverage",
]
