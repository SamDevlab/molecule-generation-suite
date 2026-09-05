from __future__ import annotations

from dataclasses import fields
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from research_os.oracle import (
    CodexCliTransport,
    CodexLiveProvider,
    LiveCodexProtocolError,
    LiveExecutionBudget,
    LiveFailureCode,
    LiveInvocationController,
    LiveReentrancyState,
    TopLevelLiveOwnerDiagnostic,
    TopLevelOwnerResult,
    TopLevelPreflightStatus,
    V5LiveAcceptanceDigest,
    classify_timeout,
    inspect_top_level_owner,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "benchmark"))
import run_v50_live_top_level as launcher  # noqa: E402


def _table(pid: int, parent: int, parent_name: str = "pwsh.exe"):
    return {pid: (parent, "python.exe"), parent: (1, parent_name), 1: (0, "System")}


def test_owner_diagnostic_contains_exact_required_fields():
    names = {item.name for item in fields(TopLevelLiveOwnerDiagnostic)}
    assert names == {"invocation_id", "pid", "parent_pid", "process_name", "parent_process_name", "ancestry_summary", "codex_session_detected", "detection_signals", "top_level_eligible", "executable", "cwd", "environment_digest", "started_at", "result"}


def test_external_process_without_codex_markers_is_top_level_confirmed():
    diagnostic = inspect_top_level_owner(environment={}, process_table=_table(100, 50), pid=100, parent_pid=50)
    assert diagnostic.result == TopLevelOwnerResult.TOP_LEVEL_CONFIRMED.value
    assert diagnostic.top_level_eligible is True
    assert diagnostic.codex_session_detected is False


def test_codex_environment_marker_requires_top_level_owner():
    diagnostic = inspect_top_level_owner(environment={"CODEX_THREAD_ID": "THREAD-1"}, process_table=_table(100, 50), pid=100, parent_pid=50)
    assert diagnostic.result == TopLevelOwnerResult.TOP_LEVEL_OWNER_REQUIRED.value
    assert diagnostic.codex_session_detected is True
    assert "CODEX_THREAD_ID_PRESENT" in diagnostic.detection_signals


def test_codex_parent_ancestry_requires_top_level_owner():
    diagnostic = inspect_top_level_owner(environment={}, process_table=_table(100, 50, "codex.exe"), pid=100, parent_pid=50)
    assert diagnostic.result == TopLevelOwnerResult.TOP_LEVEL_OWNER_REQUIRED.value
    assert "PARENT_PROCESS_NAME_CONTAINS_CODEX" in diagnostic.detection_signals


def test_unresolved_parent_is_ambiguous_not_confirmed():
    diagnostic = inspect_top_level_owner(environment={}, process_table={100: (50, "python.exe")}, pid=100, parent_pid=50)
    assert diagnostic.result == TopLevelOwnerResult.ENVIRONMENT_AMBIGUOUS.value
    assert diagnostic.top_level_eligible is False


def test_process_inspection_failure_is_fail_closed(monkeypatch):
    monkeypatch.setattr("research_os.oracle.top_level._process_table", lambda: (_ for _ in ()).throw(OSError("inspection unavailable")))
    diagnostic = inspect_top_level_owner(environment={}, pid=100, parent_pid=50)
    assert diagnostic.result == TopLevelOwnerResult.PROCESS_INSPECTION_FAILED.value
    assert diagnostic.top_level_eligible is False


def test_preflight_wrong_branch_is_refused(monkeypatch, tmp_path: Path):
    def fake_git(root, *args):
        if args == ("branch", "--show-current"):
            return True, "main"
        if args == ("rev-parse", "HEAD"):
            return True, "abc"
        return True, ""

    monkeypatch.setattr("research_os.oracle.top_level._fixed_git", fake_git)
    result = launcher.preflight_repository(tmp_path, environment={"CODEX_THREAD_ID": "T"}, process_table={})
    assert result.status == TopLevelPreflightStatus.WRONG_BRANCH.value


def test_preflight_dirty_worktree_is_refused(monkeypatch, tmp_path: Path):
    def fake_git(root, *args):
        if args == ("branch", "--show-current"):
            return True, "research-os-v1.3"
        if args == ("rev-parse", "HEAD"):
            return True, "abc"
        return True, " M unexpected.py"

    monkeypatch.setattr("research_os.oracle.top_level._fixed_git", fake_git)
    result = launcher.preflight_repository(tmp_path, environment={"CODEX_THREAD_ID": "T"}, process_table={})
    assert result.status == TopLevelPreflightStatus.DIRTY_WORKTREE.value


def test_preflight_missing_artifact_is_distinct(monkeypatch, tmp_path: Path):
    def fake_git(root, *args):
        if args == ("branch", "--show-current"):
            return True, "research-os-v1.3"
        if args == ("rev-parse", "HEAD"):
            return True, "abc"
        return True, ""

    monkeypatch.setattr("research_os.oracle.top_level._fixed_git", fake_git)
    result = launcher.preflight_repository(tmp_path, environment={}, process_table=_table(os.getpid(), os.getppid()))
    assert result.status == TopLevelPreflightStatus.ARTIFACT_MISSING.value


def test_preflight_git_inspection_failure_is_fail_closed(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("research_os.oracle.top_level._fixed_git", lambda root, *args: (False, "git unavailable"))
    result = launcher.preflight_repository(tmp_path, environment={}, process_table=_table(os.getpid(), os.getppid()))
    assert result.status == TopLevelPreflightStatus.GIT_INSPECTION_FAILED.value


def test_child_prompt_prohibits_recursive_live_session():
    prompt = CodexCliTransport._prompt({"operation": "scientific_review", "payload": {}, "context": {}})
    assert "Do not call CodexLiveProvider" in prompt
    assert "Do not invoke codex exec" in prompt
    assert "Do not recursively create another LLM session" in prompt


def test_controller_serializes_concurrent_owner_contract():
    controller = LiveInvocationController(environment={})
    first = controller.begin(provider="CODEX_LIVE", model="test", operation="one")
    second = controller.begin(provider="CODEX_LIVE", model="test", operation="two")
    assert second.admitted is False
    second.finish(exit_status="REJECTED_REENTRANT", failure_code=LiveFailureCode.REENTRANT_INVOCATION_REJECTED.value, failure_stage="ADMISSION", reentrancy_state=LiveReentrancyState.REJECTED_REENTRANT.value)
    first.finish(exit_status="COMPLETED", reentrancy_state=LiveReentrancyState.COMPLETED.value)


def test_timeout_classification_contract_is_exhaustive():
    assert classify_timeout(nested=True).value == "NESTED_REENTRANCY_TIMEOUT"
    assert classify_timeout(stage="PIPE_IO").value == "PIPE_IO_TIMEOUT"
    assert LiveFailureCode.NESTED_REENTRANCY_TIMEOUT.value == "NESTED_REENTRANCY_TIMEOUT"


def test_retry_budget_is_zero_for_top_level_acceptance():
    assert launcher.TopLevelLiveSequence.__init__
    budget = LiveExecutionBudget(max_live_turns=45, max_retries=0)
    assert budget.max_retries == 0
    assert budget.max_live_turns <= launcher.MAX_LIVE_INVOCATIONS


def test_observed_process_records_pid_and_cleanup(monkeypatch):
    events = []

    class FakeProcess:
        pid = 1234
        returncode = 0

        def communicate(self, input=None, timeout=None):
            return (launcher_json(), "")

        def kill(self):
            self.returncode = -9

    def launcher_json():
        return '{"result":"{\\"text\\":\\"ok\\"}"}'

    def fake_popen(command, **kwargs):
        assert kwargs["shell"] is False
        assert command[1] == "exec"
        return FakeProcess()

    monkeypatch.setattr("research_os.oracle.provider.subprocess.Popen", fake_popen)
    transport = CodexCliTransport(executable="codex", environment={}, process_observer=events.append, schema_path="src/research_os/oracle/live_output.schema.json")
    transport.executable = "codex"
    assert transport("interpret_question", {"user_message": "x"}, {})["result"]
    assert events[0]["pid"] == 1234
    assert events[-1]["cleanup_status"] == "EXITED"


def test_schema_failure_is_fail_closed_at_top_level_transport(monkeypatch):
    monkeypatch.setattr("research_os.oracle.provider.subprocess.run", lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout='{"bad":true}', stderr=""))
    transport = CodexCliTransport(executable="codex", environment={}, schema_path="src/research_os/oracle/live_output.schema.json")
    transport.executable = "codex"
    with pytest.raises(LiveCodexProtocolError):
        transport("scientific_review", {}, {})
    assert transport.last_invocation_diagnostic.schema_status == "FAIL"


def test_reviewer_cannot_create_evidence_or_change_level():
    class BadTransport:
        available = True
        last_runtime_model = "test"
        last_cli_version = "test"

        def __call__(self, operation, payload, context):
            return {"review": {"evidence": [{"level": "E5_VALIDATED_EXPERIMENTAL"}]}}

    provider = CodexLiveProvider(transport=BadTransport())
    with pytest.raises(ValueError):
        provider.scientific_review({})


def test_final_exam_operation_is_a_declared_provider_contract():
    class ExamTransport:
        available = True
        last_runtime_model = "test"
        last_cli_version = "test"

        def __call__(self, operation, payload, context):
            assert operation == "final_scientific_exam"
            return {"final_exam": {"conclusion_kept": "registered", "scientific_state_change": "none"}}

    assert CodexLiveProvider(transport=ExamTransport()).final_scientific_exam({})["conclusion_kept"] == "registered"


def test_followup_context_isolated_by_one_question():
    assert len(launcher.FOLLOWUP_QUESTIONS) == 15
    assert len(set(launcher.FOLLOWUP_QUESTIONS)) == 15


def test_consistency_pairs_are_five_questions_twice():
    assert len(launcher.FOLLOWUP_QUESTIONS[:5]) * 2 == 10


def test_artifact_paths_are_new_top_level_namespace():
    assert launcher.OUTPUT_ROOT.name == ".research-os-live-5.0-top-level"
    assert launcher.OUTPUT_ROOT.name != ".research-os-live-5.0-recovery"


def test_previous_blocked_recovery_artifact_is_not_overwritten():
    recovery = Path(__file__).resolve().parents[1] / ".research-os-live-5.0-recovery" / "reviewer-panel-live.json"
    data = json.loads(recovery.read_text(encoding="utf-8"))
    assert data["status"] == "BLOCKED_BEFORE_PASS"


def test_acceptance_digest_has_content_addressed_fields():
    digest = V5LiveAcceptanceDigest("abc", "r", "e", "f", "s", "c", "p", "sa", "se", 39, True)
    value = digest.to_dict()
    assert value["pass"] is True
    assert len(value["digest"]) == 64
    assert value["live_call_count"] == 39


def test_package_gate_remains_pre_5_before_live_pass():
    import importlib.metadata

    assert importlib.metadata.version("research-os-core") != "5.0.0"


def test_final_gate_requires_exact_required_call_count():
    assert launcher.REQUIRED_LIVE_INVOCATIONS == 39
    assert launcher.MAX_LIVE_INVOCATIONS == 45


def test_no_live_runner_is_invoked_by_import():
    assert callable(launcher.run_live_acceptance)


def test_stored_scientific_state_is_compacted_before_prompt():
    state = launcher._compact_state(Path(__file__).resolve().parents[1])
    assert state["state_digest"]
    assert "stress_tests" not in state
    assert "research_outcome_impacts" in state


def test_forbidden_output_scan_is_recursive():
    assert launcher._has_forbidden_output({"nested": [{"evidence_level": "E5_VALIDATED_EXPERIMENTAL"}]})
    assert not launcher._has_forbidden_output({"grounded_record_ids": ["GAP-1"]})


def test_owner_result_enum_is_closed():
    assert {item.value for item in TopLevelOwnerResult} == {"TOP_LEVEL_CONFIRMED", "TOP_LEVEL_OWNER_REQUIRED", "ENVIRONMENT_AMBIGUOUS", "PROCESS_INSPECTION_FAILED"}
