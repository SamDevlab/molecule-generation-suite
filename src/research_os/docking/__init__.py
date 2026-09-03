from .schema import DockingRequest, DockingResult, GridBox
from .campaign import DockingCampaign, DockingCampaignResult
from .preparation import LigandPreparationLab, LigandPreparationManifest, LigandPreparationRequest, ReceptorPreparationLab, ReceptorPreparationManifest, ReceptorPreparationRequest, prepare_ligand, prepare_receptor
__all__ = ["DockingLab", "DockingRequest", "DockingResult", "GridBox", "DockingCampaign", "DockingCampaignResult", "LigandPreparationLab", "LigandPreparationManifest", "LigandPreparationRequest", "ReceptorPreparationLab", "ReceptorPreparationManifest", "ReceptorPreparationRequest", "prepare_ligand", "prepare_receptor"]


def __getattr__(name):
    if name == "DockingLab":
        from .lab import DockingLab
        return DockingLab
    raise AttributeError(name)
