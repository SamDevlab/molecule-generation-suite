from research_os.molecule import MoleculeLab
from research_os.orchestration import LabRegistry,PlanStep,ResearchOrchestrator,default_registry
def test_default_registry_exposes_current_labs():
    names=default_registry().names(); assert "MoleculeLab" in names; assert "FuelLab" in names; assert "MetalLab" in names; assert "KnowledgeLab" in names; assert "ThermalLab" in names; assert "DegradationLab" in names
def test_plan_skips_dependent_step_after_upstream_failure():
    r=LabRegistry(); r.register(MoleculeLab(),aliases=("molecule",)); p=ResearchOrchestrator(r).run([PlanStep("bad","molecule",{"smiles":"not smiles"}),PlanStep("dependent","molecule",{"smiles":"CCO"},requires=("bad",))]); assert not p.runs["bad"].passed; assert "dependent" in p.skipped; assert "dependent" not in p.runs
def test_plan_runs_independent_steps_attributably():
    r=LabRegistry(); r.register(MoleculeLab(),aliases=("molecule",)); p=ResearchOrchestrator(r).run([PlanStep("ethanol","molecule",{"smiles":"CCO"}),PlanStep("methane","molecule",{"smiles":"C"})]); assert p.passed; assert p.runs["ethanol"].run_id!=p.runs["methane"].run_id
