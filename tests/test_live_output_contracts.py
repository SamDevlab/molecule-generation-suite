from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from research_os.oracle import CodexCliTransport, CodexLiveProvider, LiveCodexProtocolError, LiveCodexUnavailable, LiveFailureCode, LiveFailureStage, LiveOutputContract


CONSISTENCY_CONTEXT = {"consistency_contract": {"allowed_limitation_codes": ["PROTOCOL_SENSITIVITY"]}}


def _consistency_response(**overrides):
    response = {
        "answer": "bounded E3 result",
        "grounding_status": "GROUNDED",
        "grounded_record_ids": ["RUN-1"],
        "primary_record_id": "RUN-1",
        "limitation_codes": ["PROTOCOL_SENSITIVITY"],
        "limitations": [],
    }
    response.update(overrides)
    return response


def _transport(monkeypatch, stdout: str):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr("research_os.oracle.provider.subprocess.run", fake_run)
    transport = CodexCliTransport(executable="codex", environment={})
    transport.executable = "codex"
    return transport


def _envelope(inner: dict) -> str:
    return json.dumps({"result": json.dumps(inner, separators=(",", ":"))})


def _direct(value: dict) -> str:
    return json.dumps(value, separators=(",", ":"))


def test_route_01_ordinary_followup_uses_envelope_contract(monkeypatch):
    transport = _transport(monkeypatch, _envelope({"answer": "ordinary"}))
    result = transport("final_exam_followup", {}, {})
    assert result["result"]
    assert transport.last_output_contract == LiveOutputContract.ENVELOPE.value
    assert transport.last_output_schema_name == "live_output.schema.json"
    assert transport.last_invocation_diagnostic.output_contract == "ENVELOPE"
    assert "schema requires a string field named result" in transport._prompt({"operation": "final_exam_followup", "payload": {}, "context": {}})


def test_route_02_consistency_run_a_uses_consistency_schema(monkeypatch):
    transport = _transport(monkeypatch, _direct(_consistency_response()))
    result = transport("final_exam_followup", {}, {**CONSISTENCY_CONTEXT, "consistency_run": "A"})
    assert result == _consistency_response()
    assert transport.last_output_contract == LiveOutputContract.CONSISTENCY.value
    assert transport.last_output_schema_name == "live_consistency.schema.json"
    assert transport.last_invocation_diagnostic.output_schema_name == "live_consistency.schema.json"
    prompt = transport._prompt({"operation": "final_exam_followup", "payload": {}, "context": CONSISTENCY_CONTEXT})
    assert "Do not wrap the response in a result string" in prompt
    assert "schema requires a string field named result" not in prompt


def test_route_03_consistency_run_b_uses_same_fixed_schema(monkeypatch):
    transport = _transport(monkeypatch, _direct(_consistency_response()))
    result = transport("final_exam_followup", {}, {**CONSISTENCY_CONTEXT, "consistency_run": "B"})
    assert result["primary_record_id"] == "RUN-1"
    assert transport.last_invocation_diagnostic.output_contract == "CONSISTENCY"
    assert transport.last_invocation_diagnostic.output_schema_name == "live_consistency.schema.json"


def test_route_04_arbitrary_schema_path_is_rejected():
    with pytest.raises(ValueError):
        CodexCliTransport(executable="codex", schema_path=str(Path(__file__).resolve()), environment={})


@pytest.mark.parametrize(
    "mutator",
    [
        lambda response: response.pop("primary_record_id"),
        lambda response: response.pop("limitation_codes"),
    ],
)
def test_route_05_and_06_missing_consistency_fields_fail_at_transport(monkeypatch, mutator):
    response = _consistency_response()
    mutator(response)
    transport = _transport(monkeypatch, _direct(response))
    with pytest.raises(LiveCodexProtocolError):
        transport("final_exam_followup", {}, CONSISTENCY_CONTEXT)
    assert transport.last_invocation_diagnostic.schema_status == "FAIL"
    assert transport.last_invocation_diagnostic.failure_code == "SCHEMA_INVALID"


def test_route_07_invalid_limitation_code_fails_at_transport(monkeypatch):
    transport = _transport(monkeypatch, _direct(_consistency_response(limitation_codes=["NOT_CANONICAL"])))
    with pytest.raises(LiveCodexProtocolError):
        transport("final_exam_followup", {}, CONSISTENCY_CONTEXT)


def test_route_08_grounded_empty_ids_fail_at_transport(monkeypatch):
    transport = _transport(monkeypatch, _direct(_consistency_response(grounded_record_ids=[], primary_record_id=None)))
    with pytest.raises(LiveCodexProtocolError):
        transport("final_exam_followup", {}, CONSISTENCY_CONTEXT)


def test_route_09_no_grounded_answer_with_null_primary_passes(monkeypatch):
    transport = _transport(monkeypatch, _direct(_consistency_response(
        grounding_status="NO_GROUNDED_ANSWER",
        grounded_record_ids=[],
        primary_record_id=None,
        limitation_codes=["NO_ELIGIBLE_EXTERNAL_DATA"],
        limitations=["external record unavailable"],
    )))
    result = transport("final_exam_followup", {}, CONSISTENCY_CONTEXT)
    assert result["grounding_status"] == "NO_GROUNDED_ANSWER"


def test_route_10_extra_consistency_field_fails_at_transport(monkeypatch):
    response = _consistency_response()
    response["extra"] = "reject"
    transport = _transport(monkeypatch, _direct(response))
    with pytest.raises(LiveCodexProtocolError):
        transport("final_exam_followup", {}, CONSISTENCY_CONTEXT)


def test_route_11_ordinary_scientific_review_still_returns_result_string(monkeypatch):
    transport = _transport(monkeypatch, _envelope({"summary": "review"}))
    result = transport("scientific_review", {}, {})
    assert set(result) == {"result"}
    assert transport.last_output_schema_name == "live_output.schema.json"


def test_route_12_followup_without_consistency_context_is_not_forced_direct(monkeypatch):
    transport = _transport(monkeypatch, _envelope({"answer": "ordinary"}))
    result = transport("final_exam_followup", {}, {"consistency_run": "A"})
    assert set(result) == {"result"}
    assert transport.last_output_contract == "ENVELOPE"


def test_route_13_provider_does_not_unwrap_direct_consistency_json():
    direct = _consistency_response()

    class DirectConsistencyTransport:
        last_output_contract = "CONSISTENCY"
        last_output_schema_name = "live_consistency.schema.json"

        def __call__(self, operation, payload, context):
            return direct

    provider = CodexLiveProvider(transport=DirectConsistencyTransport())
    provider.set_request_context(CONSISTENCY_CONTEXT)
    assert provider.final_exam_followup({}) == direct


def test_route_14_consistency_contract_rejects_normal_envelope(monkeypatch):
    transport = _transport(monkeypatch, _envelope(_consistency_response()))
    with pytest.raises(LiveCodexProtocolError):
        transport("final_exam_followup", {}, CONSISTENCY_CONTEXT)


def test_route_15_normal_operation_rejects_direct_consistency_object(monkeypatch):
    transport = _transport(monkeypatch, _direct(_consistency_response()))
    with pytest.raises(LiveCodexProtocolError):
        transport("scientific_review", {}, {})


def test_schema_compat_01_provider_schema_keeps_exact_structural_contract():
    schema_path = Path(__file__).resolve().parents[1] / "src" / "research_os" / "oracle" / "live_consistency.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["required"] == [
        "answer", "grounding_status", "grounded_record_ids",
        "primary_record_id", "limitation_codes", "limitations",
    ]
    assert schema["additionalProperties"] is False
    assert not {"allOf", "if", "then", "uniqueItems", "minItems", "maxItems"}.intersection(schema)
    CodexCliTransport._validate_transport_output(_consistency_response(), contract=LiveOutputContract.CONSISTENCY)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda response: response.pop("primary_record_id"),
        lambda response: response.pop("limitation_codes"),
        lambda response: response.__setitem__("extra", True),
        lambda response: response.__setitem__("grounding_status", "INVALID"),
        lambda response: response.__setitem__("limitation_codes", ["NOT_CANONICAL"]),
    ],
)
def test_schema_compat_02_to_06_invalid_structures_fail_closed(monkeypatch, mutator):
    response = _consistency_response()
    mutator(response)
    transport = _transport(monkeypatch, _direct(response))
    with pytest.raises(LiveCodexProtocolError):
        transport("final_exam_followup", {}, CONSISTENCY_CONTEXT)


def test_route_16_provider_schema_admission_error_is_typed_and_bounded(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="invalid_json_schema: unsupported keyword allOf; secret=redacted")

    monkeypatch.setattr("research_os.oracle.provider.subprocess.run", fake_run)
    transport = CodexCliTransport(executable="codex", environment={})
    transport.executable = "codex"
    with pytest.raises(LiveCodexUnavailable, match="provider_error_code=invalid_json_schema"):
        transport("final_exam_followup", {}, CONSISTENCY_CONTEXT)
    diagnostic = transport.last_invocation_diagnostic
    assert diagnostic.failure_code == LiveFailureCode.OUTPUT_SCHEMA_ADMISSION_ERROR.value
    assert diagnostic.failure_stage == LiveFailureStage.OUTPUT_SCHEMA_ADMISSION.value
    assert diagnostic.schema_status == "NOT_CHECKED"
    assert diagnostic.provider_error_code == "invalid_json_schema"


class _RecordingProviderTransport:
    """Provider integration double that exposes the context it receives."""

    def __init__(self):
        self.calls = []
        self.last_output_contract = None
        self.last_output_schema_name = None

    def __call__(self, operation, payload, context):
        self.calls.append((operation, payload, dict(context)))
        if isinstance(context.get("consistency_contract"), dict):
            self.last_output_contract = LiveOutputContract.CONSISTENCY.value
            self.last_output_schema_name = "live_consistency.schema.json"
            return _consistency_response()
        self.last_output_contract = LiveOutputContract.ENVELOPE.value
        self.last_output_schema_name = "live_output.schema.json"
        return {"result": json.dumps({"answer": "ordinary"})}


def _provider_consistency_context(run="A"):
    context = {
        "consistency_run": run,
        "consistency_contract": {
            "CONSISTENCY_GROUNDING_BASIS": ["RUN-1"],
            "allowed_limitation_codes": ["PROTOCOL_SENSITIVITY"],
        },
        "ALLOWED_GROUNDED_RECORD_IDS": ["RUN-1"],
        "known_record_ids": ["RUN-1"],
    }
    if run == "B":
        signature = {
            "grounding_status": "GROUNDED",
            "grounded_record_ids": ["RUN-1"],
            "primary_record_id": "RUN-1",
            "limitation_codes": ["PROTOCOL_SENSITIVITY"],
        }
        context["CONSISTENCY_SIGNATURE_BASIS"] = signature
        context["consistency_contract"]["CONSISTENCY_SIGNATURE_BASIS"] = signature
    return context


def test_integration_01_ordinary_followup_uses_global_context_only():
    transport = _RecordingProviderTransport()
    provider = CodexLiveProvider(transport=transport)

    assert provider.final_exam_followup({"question": "ordinary"}) == {"answer": "ordinary"}
    assert transport.last_output_contract == "ENVELOPE"
    assert transport.last_output_schema_name == "live_output.schema.json"
    assert "consistency_contract" not in transport.calls[-1][2]


@pytest.mark.parametrize("run", ["A", "B"])
def test_integration_02_and_03_consistency_followups_propagate_per_call_context(run):
    transport = _RecordingProviderTransport()
    provider = CodexLiveProvider(transport=transport)
    context = _provider_consistency_context(run)

    result = provider.final_exam_followup(context)

    assert result == _consistency_response()
    assert transport.last_output_contract == "CONSISTENCY"
    assert transport.last_output_schema_name == "live_consistency.schema.json"
    assert transport.calls[-1][2]["consistency_run"] == run
    if run == "B":
        assert transport.calls[-1][2]["CONSISTENCY_SIGNATURE_BASIS"]["primary_record_id"] == "RUN-1"


def test_integration_04_security_global_context_cannot_be_overwritten_per_call():
    transport = _RecordingProviderTransport()
    provider = CodexLiveProvider(transport=transport)
    provider.set_request_context({
        "top_level_owner_id": "OWNER-REAL",
        "stored_state_digest": "DIGEST-REAL",
    })
    context = {
        **_provider_consistency_context("A"),
        "top_level_owner_id": "OWNER-FAKE",
        "stored_state_digest": "DIGEST-FAKE",
    }

    provider.final_exam_followup(context)
    observed = transport.calls[-1][2]
    assert observed["top_level_owner_id"] == "OWNER-REAL"
    assert observed["stored_state_digest"] == "DIGEST-REAL"
    assert observed["consistency_run"] == "A"


def test_integration_05_normal_per_call_context_remains_envelope():
    transport = _RecordingProviderTransport()
    provider = CodexLiveProvider(transport=transport)

    provider.final_exam_followup({"question": "ordinary", "known_record_ids": ["RUN-1"]})

    assert transport.last_output_contract == "ENVELOPE"
    assert transport.last_output_schema_name == "live_output.schema.json"


def test_integration_06_payload_context_alone_cannot_select_consistency_schema():
    transport = _RecordingProviderTransport()
    provider = CodexLiveProvider(transport=transport)
    payload_context = _provider_consistency_context("A")

    result = provider._call(
        "final_exam_followup",
        {"followup_context": payload_context},
    )

    assert result == {"answer": "ordinary"}
    assert transport.last_output_contract == "ENVELOPE"
    assert "consistency_contract" not in transport.calls[-1][2]


def test_integration_07_explicit_invocation_context_controls_schema_without_payload():
    transport = _RecordingProviderTransport()
    provider = CodexLiveProvider(transport=transport)
    invocation_context = _provider_consistency_context("A")

    result = provider._call(
        "final_exam_followup",
        {"followup_context": {"scientific_payload_only": True}},
        invocation_context=invocation_context,
    )

    assert result == _consistency_response()
    assert transport.last_output_contract == "CONSISTENCY"
    assert transport.calls[-1][1]["followup_context"] == {"scientific_payload_only": True}


def test_integration_08_09_per_call_context_does_not_contaminate_later_calls():
    transport = _RecordingProviderTransport()
    provider = CodexLiveProvider(transport=transport)
    provider.set_request_context({
        "top_level_owner_id": "OWNER-REAL",
        "stored_state_digest": "DIGEST-REAL",
    })

    provider.final_exam_followup(_provider_consistency_context("A"))
    provider.final_exam_followup({"question": "ordinary"})

    assert transport.calls[-2][2]["consistency_run"] == "A"
    assert transport.calls[-1][2]["top_level_owner_id"] == "OWNER-REAL"
    assert "consistency_contract" not in transport.calls[-1][2]
    assert transport.last_output_contract == "ENVELOPE"


@pytest.mark.parametrize("run", ["A", "B"])
def test_integration_10_and_11_consistency_prompt_uses_direct_framing(run):
    context = _provider_consistency_context(run)
    prompt = CodexCliTransport._prompt({"operation": "final_exam_followup", "payload": {}, "context": context})

    assert "Do not wrap the response in a result string" in prompt
    assert "schema requires a string field named result" not in prompt


def test_integration_12_13_final_exam_followups_use_same_per_call_route():
    transport = _RecordingProviderTransport()
    provider = CodexLiveProvider(transport=transport)

    provider.final_exam_followups(_provider_consistency_context("B"))

    assert transport.last_output_contract == "CONSISTENCY"
    assert transport.last_output_schema_name == "live_consistency.schema.json"
