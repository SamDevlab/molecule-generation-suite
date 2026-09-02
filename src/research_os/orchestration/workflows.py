from __future__ import annotations

from typing import Any

from research_os.orchestration.runner import PlanStep, WorkflowPlan


def build_fuel_combustion_thermal_propulsion_plan(*, fuel: dict[str, Any], combustion: dict[str, Any], thermal: dict[str, Any], propulsion: dict[str, Any]) -> WorkflowPlan:
    """Build a materialized Fuel -> Combustion -> Thermal -> Propulsion plan."""
    return WorkflowPlan((
        PlanStep("fuel", "FuelLab", fuel, experiment="fuel_catalog"),
        PlanStep("combustion", "CombustionLab", combustion, experiment="adiabatic_equilibrium_hp", requires=("fuel",)),
        PlanStep("thermal", "ThermalLab", thermal, experiment="steady_planar_conduction", requires=("combustion",)),
        PlanStep("propulsion", "PropulsionLab", propulsion, experiment="ideal_nozzle_from_combustion", requires=("thermal",)),
    ))


def build_fuel_combustion_thermal_metal_degradation_plan(*, fuel: dict[str, Any], combustion: dict[str, Any], thermal: dict[str, Any], metal: dict[str, Any], degradation: dict[str, Any]) -> WorkflowPlan:
    """Build a materialized Fuel -> Combustion -> Thermal -> Metal -> Degradation plan."""
    return WorkflowPlan((
        PlanStep("fuel", "FuelLab", fuel, experiment="fuel_catalog"),
        PlanStep("combustion", "CombustionLab", combustion, experiment="adiabatic_equilibrium_hp", requires=("fuel",)),
        PlanStep("thermal", "ThermalLab", thermal, experiment="steady_planar_conduction", requires=("combustion",)),
        PlanStep("metal", "MetalLab", metal, experiment="alloy_catalog", requires=("thermal",)),
        PlanStep("degradation", "DegradationLab", degradation, experiment="degradation_evidence", requires=("metal",)),
    ))


fuel_to_propulsion_plan = build_fuel_combustion_thermal_propulsion_plan
fuel_to_degradation_plan = build_fuel_combustion_thermal_metal_degradation_plan
