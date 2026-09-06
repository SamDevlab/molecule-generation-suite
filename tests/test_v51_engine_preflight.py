from research_os.engines.preflight import EnginePreflight, EnginePreflightStatus, register_external_research_adapters
from research_os.engines.registry import EngineRegistry


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
