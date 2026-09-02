from pathlib import Path
from research_os.core.types import GateStatus
from research_os.docking import DockingLab, DockingResult

class FakeVina:
    available=True; version="test-vina"
    def run(self, request):
        out=Path(request.output_path or Path(request.ligand_path).with_name("out.pdbqt")); out.write_text("MODEL 1\nENDMDL\n")
        return DockingResult(-8.4,str(out),"1 -8.4 0.0 0.0","",0,"Fake Vina",self.version,("fake-vina",))
class MissingVina:
    available=False; version=None
    def run(self, request): raise AssertionError("must not execute")
def request(tmp_path):
    r=tmp_path/"receptor.pdbqt"; l=tmp_path/"ligand.pdbqt"; r.write_text("RECEPTOR"); l.write_text("LIGAND")
    return {"receptor_path":r,"ligand_path":l,"grid":{"center_x":1,"center_y":2,"center_z":3,"size_x":20,"size_y":20,"size_z":20},"seed":123,"output_path":tmp_path/"dock_out.pdbqt"}
def test_docking_run_binds_artifact_hashes_grid_seed_and_result(tmp_path):
    run=DockingLab(engine=FakeVina()).run(request(tmp_path)); assert run.passed; assert run.gates[-1].rule_id=="DOCK-RUN-001"; assert run.evidence[0].payload["receptor"]["sha256"]; assert run.evidence[0].payload["seed"]==123; assert run.evidence[-1].payload["best_affinity_kcal_mol"]==-8.4; assert run.evidence[-1].payload["output_sha256"]
def test_missing_vina_is_indeterminate_not_fake_success(tmp_path):
    run=DockingLab(engine=MissingVina()).run(request(tmp_path)); assert not run.passed; assert run.first_loss.rule_id=="DOCK-ENGINE-001"; assert run.first_loss.status==GateStatus.INDETERMINATE
def test_missing_receptor_fails_before_engine(tmp_path):
    raw=request(tmp_path); Path(raw["receptor_path"]).unlink(); run=DockingLab(engine=FakeVina()).run(raw); assert not run.passed; assert run.first_loss.rule_id=="DOCK-FILE-001"
