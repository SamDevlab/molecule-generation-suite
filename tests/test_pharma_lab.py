from pathlib import Path
from research_os.core.types import EvidenceLevel, GateStatus
from research_os.docking import DockingResult
from research_os.docking.lab import DockingLab
from research_os.knowledge.claims import ClaimStatus
from research_os.pharma import PharmaLab
class FakeVina:
    available=True; version="test-vina"
    def run(self, request):
        out=Path(request.output_path or Path(request.ligand_path).with_name("out.pdbqt")); out.write_text("MODEL 1\nENDMDL\n"); return DockingResult(-7.7,str(out),"1 -7.7 0.0 0.0","",0,"Fake Vina",self.version,("fake-vina",))
def docking_input(tmp_path):
    r=tmp_path/"r.pdbqt"; l=tmp_path/"l.pdbqt"; r.write_text("RECEPTOR"); l.write_text("LIGAND"); return {"receptor_path":r,"ligand_path":l,"grid":{"center_x":0,"center_y":0,"center_z":0,"size_x":20,"size_y":20,"size_z":20},"output_path":tmp_path/"out.pdbqt"}
def test_pharma_molecule_only_creates_attributable_computational_evidence():
    lab=PharmaLab(docking_lab=DockingLab(engine=FakeVina())); run=lab.run({"smiles":"CCO","name":"ethanol","provenance":{"source_id":"local-note"}}); assert run.passed; assert run.provenance[0].source_id=="local-note"; assert run.evidence[0].level==EvidenceLevel.E2_COMPUTATIONAL; claim=lab.molecular_claim(run); assert claim.status==ClaimStatus.SUPPORTED; assert "efficacy" in claim.limitations[0]
def test_requested_docking_is_nested_and_not_called_clinical_efficacy(tmp_path):
    lab=PharmaLab(docking_lab=DockingLab(engine=FakeVina())); run=lab.run({"smiles":"CCO","docking":docking_input(tmp_path)}); assert run.passed; ev=next(e for e in run.evidence if e.kind=="pharma_docking_result"); assert ev.payload["result"]["best_affinity_kcal_mol"]==-7.7; assert "not clinical efficacy" in ev.payload["interpretation_limit"]
def test_invalid_smiles_propagates_first_loss():
    run=PharmaLab(docking_lab=DockingLab(engine=FakeVina())).run({"smiles":"not a smiles"}); assert not run.passed; assert run.first_loss.rule_id=="PHARMA-MOL-002"; assert run.first_loss.status in {GateStatus.FAIL,GateStatus.INDETERMINATE}
