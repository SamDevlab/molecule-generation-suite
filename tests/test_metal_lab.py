from research_os.core.types import GateStatus
from research_os.engines.calphad import CalphadResult
from research_os.metal import MetalLab
class FakeCalphad:
    available=True; version="test-calphad"
    def calculate(self,request): return CalphadResult("FakeCALPHAD",self.version,request.database or "test.tdb",request.temperature_k,request.pressure_pa,{"FCC_A1":0.9,"BCC_A2":0.1},{"gibbs_energy_j_mol":-1234.0})
def test_atomic_alloy_catalog_is_not_smiles_and_computes_entropy():
    run=MetalLab().run({"name":"NiCr","composition":{"Ni":0.8,"Cr":0.2},"fraction_basis":"atomic"}); assert run.passed; ev=run.evidence[-1]; assert ev.payload["composition"]=={"Cr":0.2,"Ni":0.8}; assert ev.payload["descriptors"]["configurational_entropy_j_mol_k"]>0
def test_weight_percent_is_normalized_but_not_silently_converted_to_atomic():
    run=MetalLab().run({"composition":{"Fe":98,"C":2},"fraction_basis":"wt%"}); assert run.passed; d=run.evidence[-1].payload["descriptors"]; assert d["configurational_entropy_j_mol_k"] is None; assert "without silent conversion" in d["configurational_entropy_note"]
def test_bad_fraction_sum_fails_closed():
    run=MetalLab().run({"composition":{"Ni":0.8,"Cr":0.3},"fraction_basis":"atomic"}); assert not run.passed; assert run.first_loss.rule_id=="MET-COMP-002"
def test_requested_calphad_without_engine_is_indeterminate():
    run=MetalLab().run({"composition":{"Ni":0.8,"Cr":0.2},"fraction_basis":"atomic","calphad":{"temperature_k":1200,"database":"demo.tdb"}}); assert not run.passed; assert run.first_loss.rule_id=="MET-CALPHAD-001"; assert run.first_loss.status==GateStatus.INDETERMINATE
def test_calphad_result_is_e3_only_when_real_engine_path_completes():
    run=MetalLab(calphad_engine=FakeCalphad()).run({"composition":{"Ni":0.8,"Cr":0.2},"fraction_basis":"atomic","calphad":{"temperature_k":1200,"database":"test.tdb"}}); assert run.passed; assert run.evidence[-1].level.value=="E3_PHYSICS"; assert run.evidence[-1].payload["phase_fractions"]["FCC_A1"]==0.9
