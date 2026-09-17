from pathlib import Path

import pytest

from research_os.bundles import ResearchBundle, verify_bundle
from research_os.combustion import CombustionLab
from research_os.core.types import GateStatus, RunManifest
from research_os.docking import DockingCampaign, DockingLab, GridBox, LigandPreparationRequest, ReceptorPreparationRequest, prepare_ligand, prepare_receptor
from research_os.docking.claims import docking_claim_gate
from research_os.engines import EngineManifest, EngineRegistry, run_cantera_reference_case
from research_os.engines.calphad import CalphadDatabaseUnavailableError
from research_os.engines.cantera import CanteraMechanismUnavailableError
from research_os.environment import EnvironmentManifest
from research_os.metal import MaterialFeatureSchema, MetalLab
from research_os.ledger import RunRegistry


def test_engine_manifest_has_separate_configuration_and_identity_hashes():
    first = EngineManifest("test", "Test engine", configuration={"timeout": 10}, availability="AVAILABLE")
    second = EngineManifest("test", "Test engine", configuration={"timeout": 10}, availability="AVAILABLE")
    assert first.configuration_hash == second.configuration_hash
    assert first.manifest_hash == second.manifest_hash
    assert first.valid
    assert "secret" not in first.to_dict()


def test_engine_registry_probes_without_executing_scientific_protocols():
    manifests = EngineRegistry().probe_all()
    assert {item.engine_id for item in manifests} == {"rdkit", "cantera", "openbabel", "autodock-vina", "pymatgen", "matminer", "pycalphad"}
    assert all(item.status != "SUPPORTED_AND_EXECUTED" for item in manifests)


def test_missing_cantera_is_indeterminate():
    engine = EngineRegistry().get_engine("cantera")
    if engine.availability == "AVAILABLE":
        pytest.skip("optional Cantera is installed on this host")
    run = CombustionLab().run({"fuel": "CH4:1"})
    assert run.first_loss is not None
    assert run.first_loss.status == GateStatus.INDETERMINATE


@pytest.mark.reference
def test_cantera_reference_case_never_reports_success_when_unavailable():
    result = run_cantera_reference_case()
    if not EngineRegistry().get_engine("cantera").available:
        assert result.result_status == "INDETERMINATE"


def test_missing_mechanism_is_indeterminate_not_simulation_failure():
    class MissingMechanism:
        available = True
        version = "test"
        def simulate_equilibrium(self, request):
            raise CanteraMechanismUnavailableError("missing T yaml")
    run = CombustionLab(engine=MissingMechanism()).run({"fuel": "CH4:1"})
    assert run.first_loss.rule_id == "COMB-MECHANISM-001"
    assert run.first_loss.status == GateStatus.INDETERMINATE


def test_preparation_boundaries_are_separate_and_fail_closed(tmp_path):
    source = tmp_path / "ligand.smi"
    source.write_text("CCO")
    ligand = prepare_ligand(LigandPreparationRequest("candidate-1", str(source), str(tmp_path / "ligand.pdbqt")))
    receptor = prepare_receptor(ReceptorPreparationRequest("target-1", "Homo sapiens", "enzyme", "pdb:1abc", "PDB", str(source), str(tmp_path / "receptor.pdbqt")))
    assert ligand.status == "INDETERMINATE"
    assert receptor.status == "INDETERMINATE"
    assert receptor.species == "Homo sapiens"


def _docking_request(tmp_path, **extra):
    receptor = tmp_path / "receptor.pdbqt"; ligand = tmp_path / "ligand.pdbqt"
    receptor.write_text("RECEPTOR"); ligand.write_text("LIGAND")
    return {"receptor_path": receptor, "ligand_path": ligand, "grid": {"center_x": 0, "center_y": 0, "center_z": 0, "size_x": 20, "size_y": 20, "size_z": 20}, **extra}


def test_invalid_grid_and_species_mismatch_fail_before_vina(tmp_path):
    class Engine:
        available = True; version = "test"
        def run(self, request): raise AssertionError("must not execute")
    invalid = _docking_request(tmp_path, grid={"center_x": 0, "center_y": 0, "center_z": 0, "size_x": 0, "size_y": 20, "size_z": 20})
    assert DockingLab(engine=Engine()).run(invalid).first_loss.rule_id == "DOCK-GRID-001"
    mismatch = _docking_request(tmp_path, target_id="t", species="Mus musculus", require_species=True, receptor_metadata={"species": "Homo sapiens"})
    assert DockingLab(engine=Engine()).run(mismatch).first_loss.rule_id == "DOCK-SPECIES-001"


def test_docking_campaign_keeps_replicates_and_e2_status(tmp_path):
    class MissingVina:
        available = False; version = None
    result = DockingCampaign(target_id="target", replicate_count=3, seed_base=100).run(DockingLab(engine=MissingVina()), _docking_request(tmp_path))
    assert result.seeds == (100, 101, 102)
    assert result.replicate_count == 3
    assert result.status == "INDETERMINATE"
    assert result.evidence_level == "E2_COMPUTATIONAL"


def test_docking_claim_safety_blocks_overclaiming():
    assert docking_claim_gate("Vina score under this protocol").status == GateStatus.PASS
    assert docking_claim_gate("candidate is clinically safe and effective").status == GateStatus.FAIL


def test_calphad_missing_database_boundary():
    class MissingDatabase:
        available = True; version = "test"
        def calculate(self, request): raise CalphadDatabaseUnavailableError("TDB missing")
    run = MetalLab(calphad_engine=MissingDatabase()).run({"composition": {"Ni": 0.8, "Cr": 0.2}, "fraction_basis": "atomic", "calphad": {"database": "missing.tdb"}})
    assert run.first_loss.rule_id == "MET-CALPHAD-002"
    assert run.first_loss.status == GateStatus.INDETERMINATE


def test_material_feature_schema_requires_explicit_basis():
    schema = MaterialFeatureSchema("schema", ("formula",), "atomic", "pymatgen", "test")
    assert schema.to_dict()["fraction_basis"] == "atomic"
    with pytest.raises(ValueError):
        MaterialFeatureSchema("schema", ("formula",), "unknown", "pymatgen", "test")


def test_bundle_engine_manifest_is_sealed_and_tamper_detected(tmp_path):
    run = RunManifest("TestLab", "engine-test", {"x": 1})
    run.start(); run.complete(); run.seal()
    engine = EngineManifest("test", "Test", availability="AVAILABLE", status="SUPPORTED_AND_EXECUTED", readiness="REFERENCE_VALIDATED")
    bundle = ResearchBundle.create(run, tmp_path, environment=EnvironmentManifest(), engine_manifests=[engine])
    assert verify_bundle(bundle.root).passed
    manifest_path = Path(bundle.root) / "engines" / "manifests.json"
    manifest_path.write_text(manifest_path.read_text(encoding="utf-8").replace("SUPPORTED_AND_EXECUTED", "EXECUTION_FAILED"), encoding="utf-8")
    assert verify_bundle(bundle.root).status.value == "FAIL"


def test_ledger_indexes_engine_trace_and_detects_engine_version_change(tmp_path):
    environment = EnvironmentManifest()
    first_run = RunManifest("TestLab", "engine-test", {"x": 1}); first_run.start(); first_run.complete(); first_run.seal()
    second_run = RunManifest("TestLab", "engine-test", {"x": 1}); second_run.start(); second_run.complete(); second_run.seal()
    first = ResearchBundle.create(first_run, tmp_path / "bundles", environment=environment, engine_manifests=[EngineManifest("vina", "Vina", "COMPUTATIONAL_ENGINE", "1.0", "AVAILABLE", "SUPPORTED_AND_EXECUTED", "REFERENCE_VALIDATED")])
    second = ResearchBundle.create(second_run, tmp_path / "bundles", environment=environment, engine_manifests=[EngineManifest("vina", "Vina", "COMPUTATIONAL_ENGINE", "2.0", "AVAILABLE", "SUPPORTED_AND_EXECUTED", "REFERENCE_VALIDATED")])
    ledger = RunRegistry(tmp_path / "ledger")
    try:
        ledger.register_run(first); ledger.register_run(second)
        assert {item.run_id for item in ledger.runs_using_engine("vina")} == {first.run_id, second.run_id}
        assert ledger.trace_engine_run(first.run_id)["engines"][0]["engine_id"] == "vina"
        comparison = ledger.compare_runs(first.run_id, second.run_id)
        assert "ENGINE_VERSION_CHANGED" in comparison.engine_differences
    finally:
        ledger.close()
