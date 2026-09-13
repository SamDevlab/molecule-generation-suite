from .schema import DockingRequest, DockingResult, GridBox
from .campaign import DockingCampaign, DockingCampaignResult
from .preparation import LigandPreparationLab, LigandPreparationManifest, LigandPreparationRequest, ReceptorPreparationLab, ReceptorPreparationManifest, ReceptorPreparationRequest, prepare_ligand, prepare_receptor
from .capability import CapabilityAssessment, CapabilityClassification, DockingCapabilityProfile, DockingContext, capability_claim_gate, capability_metadata, classify_docking_context, load_profile
__all__ = ["DockingLab", "DockingRequest", "DockingResult", "GridBox", "DockingCampaign", "DockingCampaignResult", "LigandPreparationLab", "LigandPreparationManifest", "LigandPreparationRequest", "ReceptorPreparationLab", "ReceptorPreparationManifest", "ReceptorPreparationRequest", "prepare_ligand", "prepare_receptor", "CapabilityAssessment", "CapabilityClassification", "DockingCapabilityProfile", "DockingContext", "capability_claim_gate", "capability_metadata", "classify_docking_context", "load_profile"]


def __getattr__(name):
    if name == "DockingLab":
        from .lab import DockingLab
        return DockingLab
    raise AttributeError(name)
