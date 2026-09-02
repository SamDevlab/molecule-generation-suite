from research_os.combustion import CombustionLab
from research_os.docking import DockingLab
from research_os.fuel import FuelLab
from research_os.knowledge import KnowledgeLab
from research_os.metal import MetalLab
from research_os.molecule import MoleculeLab
from research_os.orchestration.registry import LabRegistry
from research_os.pharma import PharmaLab
from research_os.propulsion import PropulsionLab
from research_os.thermal import ThermalLab
from research_os.degradation import DegradationLab
def default_registry():
    r=LabRegistry(); r.register(MoleculeLab(),aliases=("molecule","molecular")); r.register(FuelLab(),aliases=("fuel","fuels")); r.register(CombustionLab(),aliases=("combustion",)); r.register(DockingLab(),aliases=("docking",)); r.register(PharmaLab(),aliases=("pharma","biolab")); r.register(PropulsionLab(),aliases=("propulsion",)); r.register(MetalLab(),aliases=("metal","metallurgy")); r.register(KnowledgeLab(),aliases=("knowledge","zettelkasten")); r.register(ThermalLab(),aliases=("thermal","heat")); r.register(DegradationLab(),aliases=("degradation","corrosion")); return r
