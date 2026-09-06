from .schema import DockingRequest, DockingResult, GridBox
from .contract import DockingExecutionContract
from .pose_recovery import PoseAtom, PoseRecoveryResult, PoseRecoveryStatus, recover_pose
from .campaign import DockingCampaign, DockingCampaignResult
from .preparation import LigandPreparationLab, LigandPreparationManifest, LigandPreparationRequest, ReceptorPreparationLab, ReceptorPreparationManifest, ReceptorPreparationRequest, prepare_ligand, prepare_receptor
__all__ = ["DockingLab", "DockingRequest", "DockingResult", "GridBox", "DockingExecutionContract", "PoseAtom", "PoseRecoveryResult", "PoseRecoveryStatus", "recover_pose", "DockingCampaign", "DockingCampaignResult", "LigandPreparationLab", "LigandPreparationManifest", "LigandPreparationRequest", "ReceptorPreparationLab", "ReceptorPreparationManifest", "ReceptorPreparationRequest", "prepare_ligand", "prepare_receptor"]


def __getattr__(name):
    if name == "DockingLab":
        from .lab import DockingLab
        return DockingLab
    raise AttributeError(name)
