from research_os.engines.preflight import EnginePreflight, EnginePreflightStatus, register_external_research_adapters
from research_os.engines.registry import EngineRegistry
from types import SimpleNamespace


def test_external_engine_adapters_are_registered_and_unavailable_is_fail_closed(tmp_path):
    registry = EngineRegistry(root=tmp_path / "engines")
    register_external_research_adapters(registry)
    results = EnginePreflight(registry).check_many(("autodock-vina", "openbabel"))
    assert {item.adapter_name for item in results} == {"VinaEngine", "OpenBabelEngine"}
    assert all(item.status in {EnginePreflightStatus.NOT_CONFIGURED, EnginePreflightStatus.UNAVAILABLE} for item in results)
    assert all(not item.can_execute for item in results)


def test_unregistered_engine_adapter_cannot_pass_preflight(tmp_path):
    result = EnginePreflight(EngineRegistry(root=tmp_path / "engines")).check("autodock-vina")
    assert result.status == EnginePreflightStatus.NOT_REGISTERED
    assert not result.can_execute


def test_engine_preflight_distinguishes_version_input_timeout_and_output_failures(tmp_path):
    registry = EngineRegistry(root=tmp_path / "engines")
    register_external_research_adapters(registry)
    preflight = EnginePreflight(registry)
    assert preflight.check("autodock-vina", expected_version="vina-expected").status == EnginePreflightStatus.ENGINE_VERSION_MISMATCH
    assert preflight.check("autodock-vina", input_kind="sdf").status == EnginePreflightStatus.ENGINE_INPUT_UNSUPPORTED
    assert preflight.classify_execution(SimpleNamespace(timed_out=True, returncode=-1)) == EnginePreflightStatus.ENGINE_TIMEOUT
    assert preflight.classify_execution(SimpleNamespace(timed_out=False, returncode=2, output_path=None)) == EnginePreflightStatus.ENGINE_EXECUTION_FAILED
    assert preflight.classify_execution(SimpleNamespace(timed_out=False, returncode=0, output_path=str(tmp_path / "missing.pdbqt"))) == EnginePreflightStatus.ENGINE_OUTPUT_INVALID
