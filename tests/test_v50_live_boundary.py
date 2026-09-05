from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from research_os.oracle import (
    CODEX_LIVE_REENTRANCY,
    CodexCliTransport,
    LiveCodexProtocolError,
    LiveCodexUnavailable,
    LiveExecutionBudget,
    LiveFailureCode,
    LiveInvocationController,
    LiveReentrancyState,
)


SCHEMA = '{"result":"{\\"text\\":\\"ok\\"}"}'


def _transport(monkeypatch, *, budget: LiveExecutionBudget | None = None, environment=None, allow_codex_host_context: bool = False):
    transport = CodexCliTransport(
        executable="codex",
        budget=budget,
        allow_codex_host_context=allow_codex_host_context,
        schema_path="src/research_os/oracle/live_output.schema.json",
        environment=environment or {"PATH": "fixed", "CODEX_THREAD_ID": "", "CODEX_SESSION_ID": ""},
    )
    # The executable identity is validated at construction; availability is
    # independently controlled here so the subprocess contract can be tested
    # without requiring a Codex CLI in CI.
    transport.executable = "codex"
    return transport


def test_live_execution_budget_is_explicit_and_stage_bounded():
    budget = LiveExecutionBudget(total_timeout=40, planning_budget=12, execution_budget=20, review_budget=15, output_validation_budget=3, max_live_turns=4, max_retries=1)
    assert budget.timeout_for("discover_problems") == 12
    assert budget.timeout_for("final_exam_followups") == 15
    assert budget.to_dict()["max_retries"] == 1
    with pytest.raises(ValueError):
        LiveExecutionBudget(total_timeout=0)


def test_codex_host_context_is_rejected_before_recursive_process_start():
    controller = LiveInvocationController(environment={"CODEX_THREAD_ID": "THREAD-1"})
    handle = controller.begin(provider="CODEX_LIVE", model="unknown", operation="smoke")
    diagnostic = handle.finish(
        exit_status="REJECTED_REENTRANT",
        failure_code=LiveFailureCode.REENTRANT_INVOCATION_REJECTED.value,
        failure_stage="ADMISSION",
        reentrancy_state=LiveReentrancyState.REJECTED_REENTRANT.value,
    )
    assert diagnostic.parent_invocation_id == "CODEX_CONTEXT:THREAD-1"
    assert diagnostic.depth == 1
    assert diagnostic.reentrancy_state == "REJECTED_REENTRANT"
    assert diagnostic.to_dict()["invocation_id"].startswith("LIVE-")


def test_nested_invocation_is_rejected_without_deadlock():
    controller = LiveInvocationController(environment={})
    outer = controller.begin(provider="CODEX_LIVE", model="test", operation="outer")
    inner = controller.begin(provider="CODEX_LIVE", model="test", operation="inner")
    assert outer.admitted is True
    assert inner.admitted is False
    inner_result = inner.finish(
        exit_status="REJECTED_REENTRANT",
        failure_code=LiveFailureCode.REENTRANT_INVOCATION_REJECTED.value,
        failure_stage="ADMISSION",
        reentrancy_state=LiveReentrancyState.REJECTED_REENTRANT.value,
    )
    outer_result = outer.finish(exit_status="COMPLETED", reentrancy_state=LiveReentrancyState.COMPLETED.value)
    assert inner_result.parent_invocation_id == outer_result.invocation_id
    assert len(controller.diagnostics) == 2


def test_transport_uses_fixed_argv_shell_false_and_audited_environment(monkeypatch):
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout=SCHEMA, stderr="model: test\n")

    monkeypatch.setattr("research_os.oracle.provider.subprocess.run", fake_run)
    transport = _transport(monkeypatch, environment={"PATH": "fixed", "CODEX_THREAD_ID": "nested", "CODEX_HOME": "private"}, allow_codex_host_context=True)
    result = transport("interpret_question", {"user_message": "smoke"}, {})
    assert result == {"result": '{"text":"ok"}'}
    assert observed["command"][1:3] == ["exec", "--ephemeral"]
    assert observed["command"][-1] == "-"
    assert observed["kwargs"]["shell"] is False
    assert "CODEX_THREAD_ID" not in observed["kwargs"]["env"]
    assert "CODEX_HOME" not in observed["kwargs"]["env"]
    assert transport.last_invocation_diagnostic.schema_status == "PASS"
    assert transport.last_invocation_diagnostic.reentrancy_state == "COMPLETED"


def test_transport_schema_failure_is_fail_closed_and_not_retried(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout='{"not_result":true}', stderr="")

    monkeypatch.setattr("research_os.oracle.provider.subprocess.run", fake_run)
    transport = _transport(
        monkeypatch,
        budget=LiveExecutionBudget(total_timeout=5, planning_budget=5, execution_budget=5, review_budget=5, output_validation_budget=1, max_live_turns=5, max_retries=3),
        environment={},
    )
    with pytest.raises(LiveCodexProtocolError):
        transport("interpret_question", {"user_message": "schema"}, {})
    assert len(calls) == 1
    assert transport.last_invocation_diagnostic.exit_status == "SCHEMA_ERROR"
    assert transport.last_invocation_diagnostic.failure_code == LiveFailureCode.SCHEMA_INVALID.value


def test_transport_timeout_is_classified_without_retry(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output=b"partial", stderr=b"diagnostic")

    monkeypatch.setattr("research_os.oracle.provider.subprocess.run", fake_run)
    transport = _transport(monkeypatch, environment={})
    with pytest.raises(LiveCodexUnavailable, match=LiveFailureCode.MODEL_EXECUTION_TIMEOUT.value):
        transport("interpret_question", {"user_message": "timeout"}, {})
    diagnostic = transport.last_invocation_diagnostic
    assert diagnostic.exit_status == "TIMEOUT"
    assert diagnostic.failure_code == LiveFailureCode.MODEL_EXECUTION_TIMEOUT.value
    assert diagnostic.stdout_bytes == len(b"partial")
    assert diagnostic.stderr_bytes == len(b"diagnostic")


def test_process_start_error_retries_only_with_explicit_bounded_budget(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            raise OSError("transient process start")
        return subprocess.CompletedProcess(command, 0, stdout=SCHEMA, stderr="")

    monkeypatch.setattr("research_os.oracle.provider.subprocess.run", fake_run)
    transport = _transport(
        monkeypatch,
        budget=LiveExecutionBudget(total_timeout=5, planning_budget=5, execution_budget=5, review_budget=5, output_validation_budget=1, max_live_turns=2, max_retries=1),
        environment={},
    )
    assert transport("interpret_question", {"user_message": "retry"}, {})["result"]
    assert len(calls) == 2
    assert transport.invocation_diagnostics[0].failure_code == LiveFailureCode.PROCESS_START_ERROR.value
    assert transport.invocation_diagnostics[1].reentrancy_state == LiveReentrancyState.COMPLETED.value


def test_reentrancy_contract_name_is_stable():
    assert CODEX_LIVE_REENTRANCY == "CODEX_LIVE_REENTRANCY"


def test_transport_rejects_arbitrary_executable_and_schema_paths():
    with pytest.raises(ValueError, match="fixed codex executable"):
        CodexCliTransport(executable="powershell", environment={})
    with pytest.raises(ValueError, match="fixed live output schema"):
        CodexCliTransport(executable="codex", schema_path="tests/test_v50_live_boundary.py", environment={})


def test_recovery_artifacts_keep_live_blocker_and_ten_case_matrix():
    root = Path(__file__).resolve().parents[1] / ".research-os-live-5.0-recovery"
    diagnostics = json.loads((root / "live-boundary-diagnostics.json").read_text(encoding="utf-8"))
    matrix = json.loads((root / "live-smoke-matrix.json").read_text(encoding="utf-8"))
    assert diagnostics["post_fix_real_smoke"]["provider"] == "CODEX_LIVE"
    assert matrix["status"] == "BLOCKED_BEFORE_LIVE_REVIEW"
    assert len(matrix["cases"]) == 10
    assert json.loads((root / "reviewer-panel-live.json").read_text(encoding="utf-8"))["status"] == "BLOCKED_BEFORE_PASS"
    assert json.loads((root / "final-scientific-exam-live.json").read_text(encoding="utf-8"))["status"] == "BLOCKED_BEFORE_PASS"
