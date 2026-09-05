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
    ConsistencyFailureCode,
    ConsistencyGroundingAssessment,
    ConsistencySignature,
    GroundingFailureCode,
    GroundingStatus,
    GroundingValidationResult,
    LiveCodexProtocolError,
    LiveExecutionBudget,
    LiveFailureCode,
    LiveInvocationController,
    LiveReentrancyState,
    LiveResponseValidationFailure,
    validate_grounding,
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
    assert launcher.OUTPUT_ROOT.name == ".research-os-live-5.0-top-level-attempt-2"
    assert launcher.OUTPUT_ROOT.name != ".research-os-live-5.0-recovery"


def test_previous_blocked_recovery_artifact_is_not_overwritten():
    recovery = Path(__file__).resolve().parents[1] / ".research-os-live-5.0-recovery" / "reviewer-panel-live.json"
    data = json.loads(recovery.read_text(encoding="utf-8"))
    assert data["status"] == "BLOCKED_BEFORE_PASS"


def test_acceptance_digest_has_content_addressed_fields():
    digest = V5LiveAcceptanceDigest("start", "live", "r", "s", "e", "f", "st", "c", "p", "sa", "se", 39, 0, 0, 0, 0, True)
    value = digest.to_dict()
    assert value["pass"] is True
    assert len(value["digest"]) == 64
    assert value["live_call_count"] == 39
    assert value["starting_commit"] == "start"
    assert value["live_execution_commit"] == "live"
    assert value["reviewer_panel_hash"] == "r"
    assert value["cleanup_hash"] == "p"


def test_grounding_result_has_explicit_diagnostic_contract():
    names = {item.name for item in fields(GroundingValidationResult)}
    assert names == {"valid", "failure_code", "returned_ids", "unknown_ids", "known_ids_count", "missing_grounding_field", "grounding_status", "forbidden_fields", "response_type", "response_hash"}


def test_failed_response_diagnostic_has_explicit_safe_contract():
    names = {item.name for item in fields(LiveResponseValidationFailure)}
    assert names == {"call_id", "label", "operation", "response_hash", "schema_status", "grounding_validation", "forbidden_field_validation", "returned_grounded_ids", "unknown_grounded_ids", "response_keys", "grounding_status", "failure_code"}


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


def test_ground_01_valid_known_id_passes():
    result = validate_grounding({"answer": "recorded", "grounding_status": "GROUNDED", "grounded_record_ids": ["RUN-1"]}, {"RUN-1"})
    assert result.valid and result.failure_code == GroundingFailureCode.NONE.value


def test_ground_02_unknown_id_fails_with_code():
    result = validate_grounding({"grounding_status": "GROUNDED", "grounded_record_ids": ["RUN-X"]}, {"RUN-1"})
    assert result.failure_code == GroundingFailureCode.UNKNOWN_GROUNDED_RECORD_ID.value
    assert result.unknown_ids == ("RUN-X",)


def test_ground_03_missing_ids_fails_with_code():
    result = validate_grounding({"grounding_status": "GROUNDED"}, {"RUN-1"})
    assert result.failure_code == GroundingFailureCode.MISSING_GROUNDED_RECORD_IDS.value


def test_ground_04_ids_string_fails_with_code():
    result = validate_grounding({"grounding_status": "GROUNDED", "grounded_record_ids": "RUN-1"}, {"RUN-1"})
    assert result.failure_code == GroundingFailureCode.INVALID_GROUNDED_RECORD_IDS_TYPE.value


def test_ground_05_grounded_empty_ids_fails_with_code():
    result = validate_grounding({"grounding_status": "GROUNDED", "grounded_record_ids": []}, {"RUN-1"})
    assert result.failure_code == GroundingFailureCode.EMPTY_GROUNDING_FOR_GROUNDED_ANSWER.value


def test_ground_06_no_grounded_answer_empty_ids_passes():
    result = validate_grounding({"answer": "not supported", "grounding_status": "NO_GROUNDED_ANSWER", "grounded_record_ids": [], "limitations": ["missing record"]}, {"RUN-1"})
    assert result.valid and result.failure_code == GroundingFailureCode.NONE.value


def test_ground_07_no_grounded_answer_with_id_fails():
    result = validate_grounding({"grounding_status": "NO_GROUNDED_ANSWER", "grounded_record_ids": ["RUN-X"]}, {"RUN-1"})
    assert not result.valid and result.failure_code == GroundingFailureCode.INVALID_GROUNDING_STATUS.value


def test_ground_08_evidence_field_fails_with_code():
    result = validate_grounding({"evidence": [], "grounding_status": "GROUNDED", "grounded_record_ids": ["RUN-1"]}, {"RUN-1"})
    assert result.failure_code == GroundingFailureCode.FORBIDDEN_SCIENTIFIC_FIELD.value
    assert result.forbidden_fields == ("evidence",)


def test_ground_09_evidence_level_field_fails_with_code():
    result = validate_grounding({"evidence_level": "E5_VALIDATED_EXPERIMENTAL", "grounding_status": "GROUNDED", "grounded_record_ids": ["RUN-1"]}, {"RUN-1"})
    assert result.failure_code == GroundingFailureCode.FORBIDDEN_SCIENTIFIC_FIELD.value


def test_ground_10_multiple_known_ids_passes():
    result = validate_grounding({"grounding_status": GroundingStatus.GROUNDED.value, "grounded_record_ids": ["RUN-1", "GAP-1"]}, {"RUN-1", "GAP-1"})
    assert result.valid and result.unknown_ids == ()


def test_empty_grounding_compatibility_wrapper_is_not_truthy():
    assert launcher._valid_grounding({"grounding_status": "GROUNDED", "grounded_record_ids": []}, {"RUN-1"}) is False


def test_grounding_prompt_exposes_literal_allowlist_and_status_contract():
    prompt = CodexCliTransport._prompt({"operation": "final_exam_followup", "payload": {}, "context": {"ALLOWED_GROUNDED_RECORD_IDS": ["RUN-1"]}})
    assert "ALLOWED_GROUNDED_RECORD_IDS" in prompt
    assert "NO_GROUNDED_ANSWER" in prompt
    assert "Never invent identifiers" in prompt


def test_consistency_prompt_freezes_basis_and_forbids_reference_composition():
    prompt = CodexCliTransport._prompt({
        "operation": "final_exam_followup",
        "payload": {},
        "context": {
            "ALLOWED_GROUNDED_RECORD_IDS": ["A", "B"],
            "consistency_contract": {"CONSISTENCY_GROUNDING_BASIS": ["A", "B"]},
        },
    })
    assert "This is the second run of a controlled scientific consistency test" in prompt
    assert "Do not invent, derive, compose, abbreviate, expand or rename record IDs" in prompt
    assert '"A", "B"' in prompt


def test_inner_grounding_schema_declares_both_status_contracts():
    schema_path = Path(__file__).resolve().parents[1] / "src" / "research_os" / "oracle" / "live_grounding.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["required"] == ["grounding_status", "grounded_record_ids"]
    assert schema["properties"]["grounding_status"]["enum"] == ["GROUNDED", "NO_GROUNDED_ANSWER"]
    assert schema["oneOf"][0]["properties"]["grounded_record_ids"]["minItems"] == 1
    assert schema["oneOf"][1]["properties"]["grounded_record_ids"]["maxItems"] == 0


def test_followup_failure_persists_structured_unknown_id_without_raw_trace():
    sequence = launcher.TopLevelLiveSequence(Path(__file__).resolve().parents[1], {"state_digest": "fixture"}, "OWNER-1", 1)
    sequence.known_ids = {"RUN-1", "GAP-1"}
    calls = {"count": 0}

    def response(_context):
        calls["count"] += 1
        if calls["count"] == 13:
            return {"answer": "unsupported", "grounding_status": "GROUNDED", "grounded_record_ids": ["INVENTED-13"], "limitations": ["test failure"]}
        return {"answer": "supported", "grounding_status": "GROUNDED", "grounded_record_ids": ["RUN-1"], "limitations": []}

    sequence.provider.final_exam_followup = response
    result = launcher._followups(sequence, {"response": {}})
    assert result["status"] == "BLOCKED_BEFORE_PASS"
    assert len(result["answers"]) == 12
    assert result["failed_call"]["status"] == "COMPLETED"
    assert result["failed_call"]["diagnostic"] is None
    assert result["failed_response_validation"]["failure_code"] == "UNKNOWN_GROUNDED_RECORD_ID"
    assert result["failed_response_validation"]["unknown_grounded_ids"] == ["INVENTED-13"]
    assert result["failed_response"] == {"answer": "unsupported", "grounding_status": "GROUNDED", "grounded_record_ids": ["INVENTED-13"], "limitations": ["test failure"]}
    assert "evidence" not in json.dumps(result["failed_response"])
    assert len(sequence.response_validation_failures) == 1


def test_worktree_policy_allows_only_recognized_acceptance_json():
    allowed = launcher.evaluate_worktree_acceptance(Path("."), "?? .research-os-live-5.0-top-level-attempt-2/follow-up-answers.json\n")
    assert allowed.valid and allowed.allowed_paths == (".research-os-live-5.0-top-level-attempt-2/follow-up-answers.json",)


def test_worktree_policy_rejects_unknown_acceptance_file():
    result = launcher.evaluate_worktree_acceptance(Path("."), "!! .research-os-live-5.0-top-level-attempt-2/unknown.txt\n")
    assert not result.valid and result.unexpected_paths == (".research-os-live-5.0-top-level-attempt-2/unknown.txt",)


def test_worktree_policy_rejects_source_change():
    result = launcher.evaluate_worktree_acceptance(Path("."), " M src/research_os/oracle/grounding.py\n")
    assert not result.valid


def test_worktree_policy_rejects_arbitrary_untracked_file():
    result = launcher.evaluate_worktree_acceptance(Path("."), "?? notes.txt\n")
    assert not result.valid


def test_worktree_policy_accepts_clean_status():
    result = launcher.evaluate_worktree_acceptance(Path("."), "")
    assert result.valid and result.unexpected_paths == ()


def test_worktree_policy_rejects_unknown_changed_file_outside_namespace():
    result = launcher.evaluate_worktree_acceptance(Path("."), " M README.md\n")
    assert not result.valid and result.unexpected_paths == ("README.md",)


def test_next_attempt_namespace_never_reuses_nonempty_attempt(tmp_path: Path):
    attempt_2 = tmp_path / ".research-os-live-5.0-top-level-attempt-2"
    attempt_2.mkdir()
    (attempt_2 / "v5-final-gate.json").write_text("{}", encoding="utf-8")
    assert launcher._next_output_root(tmp_path).name == ".research-os-live-5.0-top-level-attempt-3"


class _ConsistencyFixtureSequence:
    def __init__(self, responses, known_ids):
        self.responses = iter(responses)
        self.known_ids = set(known_ids)
        self.contexts = []
        self.calls = []

    def state_context(self, instruction, *, extra=None):
        context = {
            "instruction": instruction,
            "known_record_ids": sorted(self.known_ids),
            "ALLOWED_GROUNDED_RECORD_IDS": sorted(self.known_ids),
        }
        if extra:
            context.update(extra)
        return context

    def invoke(self, label, operation, method_name, context):
        self.contexts.append(context)
        call = {"call_id": len(self.calls) + 1, "label": label, "operation": operation, "status": "COMPLETED", "diagnostic": None}
        self.calls.append(call)
        return next(self.responses), call

    def validate_grounded_response(self, response, call, *, require_grounded=True):
        validation = validate_grounding(response, self.known_ids)
        valid = validation.valid and (not require_grounded or validation.grounding_status == GroundingStatus.GROUNDED.value)
        return valid, validation, None


def _consistency_response(ids, *, primary=None, codes=None, status="GROUNDED", answer="answer", limitations=None):
    return {
        "answer": answer,
        "grounding_status": status,
        "grounded_record_ids": list(ids),
        "primary_record_id": primary if status == "GROUNDED" else None,
        "limitation_codes": list(codes or []),
        "limitations": list(limitations or []),
    }


def _run_consistency_pair(response_a, response_b, *, known_ids=("A", "B", "C")):
    sequence = _ConsistencyFixtureSequence(tuple(item for _ in range(5) for item in (response_a, response_b)), known_ids)
    result = launcher._consistency(sequence, {"response": {}})
    return result, sequence


def test_cons_01_exact_frozen_basis_passes():
    result, _ = _run_consistency_pair(_consistency_response(("A", "B", "C"), primary="A"), _consistency_response(("A", "B", "C"), primary="A"))
    assert result["status"] == "PASS"
    assert result["pairs"][0]["consistency_assessment"]["failure_code"] == ConsistencyFailureCode.NONE.value


def test_cons_02_order_is_ignored():
    result, _ = _run_consistency_pair(_consistency_response(("A", "B", "C"), primary="A"), _consistency_response(("C", "A", "B"), primary="A"))
    assert result["status"] == "PASS"
    assert result["pairs"][0]["consistency_assessment"]["support_basis_equal"] is True


def test_cons_03_new_unknown_id_fails_with_consistency_code():
    result, _ = _run_consistency_pair(_consistency_response(("A", "B", "C"), primary="A"), _consistency_response(("A", "B", "C", "FAKE"), primary="A"))
    assessment = result["pairs"][0]["consistency_assessment"]
    assert result["status"] == "BLOCKED_BEFORE_PASS"
    assert assessment["failure_code"] == ConsistencyFailureCode.CONSISTENCY_NEW_GROUNDED_RECORD_ID.value
    assert assessment["new_ids_in_b"] == ["FAKE"]


def test_cons_04_unknown_id_preserves_underlying_grounding_failure():
    result, sequence = _run_consistency_pair(_consistency_response(("A", "B", "C"), primary="A"), _consistency_response(("A", "B", "C", "FAKE"), primary="A"))
    underlying = sequence.validate_grounded_response(result["pairs"][0]["run_b"], result["pairs"][0]["calls"][1], require_grounded=False)[1]
    assert underlying.failure_code == GroundingFailureCode.UNKNOWN_GROUNDED_RECORD_ID.value
    assert result["pairs"][0]["consistency_assessment"]["failure_code"] == ConsistencyFailureCode.CONSISTENCY_NEW_GROUNDED_RECORD_ID.value


def test_cons_05_globally_known_id_outside_frozen_basis_still_fails():
    result, _ = _run_consistency_pair(_consistency_response(("A", "B", "C"), primary="A"), _consistency_response(("A", "B", "C", "D"), primary="A"), known_ids=("A", "B", "C", "D"))
    assert result["pairs"][0]["consistency_assessment"]["failure_code"] == ConsistencyFailureCode.CONSISTENCY_NEW_GROUNDED_RECORD_ID.value


def test_cons_06_missing_frozen_id_fails():
    result, _ = _run_consistency_pair(_consistency_response(("A", "B", "C"), primary="A"), _consistency_response(("A", "B"), primary="A"))
    assert result["pairs"][0]["consistency_assessment"]["failure_code"] == ConsistencyFailureCode.CONSISTENCY_MISSING_GROUNDED_RECORD_ID.value


def test_cons_07_same_ids_different_order_signature_matches():
    result, _ = _run_consistency_pair(_consistency_response(("A", "B", "C"), primary="A"), _consistency_response(("B", "C", "A"), primary="A"))
    pair = result["pairs"][0]
    assert pair["consistency_signature_a"]["digest"] == pair["consistency_signature_b"]["digest"]


def test_cons_08_prose_difference_does_not_fail():
    result, _ = _run_consistency_pair(_consistency_response(("A",), primary="A", answer="first"), _consistency_response(("A",), primary="A", answer="second"))
    assert result["status"] == "PASS"


def test_cons_09_limitation_prose_difference_does_not_fail():
    result, _ = _run_consistency_pair(_consistency_response(("A",), primary="A", codes=("PROTOCOL_SENSITIVITY",), limitations=("wording one",)), _consistency_response(("A",), primary="A", codes=("PROTOCOL_SENSITIVITY",), limitations=("wording two",)))
    assert result["status"] == "PASS"


def test_cons_10_limitation_code_drift_fails():
    result, _ = _run_consistency_pair(_consistency_response(("A",), primary="A", codes=("PROTOCOL_SENSITIVITY",)), _consistency_response(("A",), primary="A", codes=("OUT_OF_DOMAIN",)))
    assert result["pairs"][0]["consistency_assessment"]["failure_code"] == ConsistencyFailureCode.LIMITATION_DRIFT.value


def test_cons_11_primary_record_drift_fails():
    result, _ = _run_consistency_pair(_consistency_response(("A", "B"), primary="A"), _consistency_response(("A", "B"), primary="B"))
    assert result["pairs"][0]["consistency_assessment"]["failure_code"] == ConsistencyFailureCode.PRIMARY_RECORD_DRIFT.value


def test_cons_12_grounding_status_drift_fails():
    result, _ = _run_consistency_pair(_consistency_response(("A",), primary="A"), _consistency_response((), status="NO_GROUNDED_ANSWER", limitations=("not supported",)))
    assert result["pairs"][0]["consistency_assessment"]["failure_code"] == ConsistencyFailureCode.GROUNDING_STATUS_DRIFT.value


def test_cons_13_no_grounded_answer_to_grounded_fails():
    result, _ = _run_consistency_pair(_consistency_response((), status="NO_GROUNDED_ANSWER", limitations=("not supported",)), _consistency_response(("A",), primary="A"))
    assert result["pairs"][0]["consistency_assessment"]["failure_code"] == ConsistencyFailureCode.GROUNDING_STATUS_DRIFT.value


def test_cons_14_plausible_reference_is_not_corrected():
    fake = "CH-V45-SOLUBILITY-EXTERNAL-BOUNDARY"
    result, _ = _run_consistency_pair(_consistency_response(("A", "B", "C"), primary="A"), _consistency_response(("A", "B", "C", fake), primary="A"))
    assert result["pairs"][0]["consistency_assessment"]["new_ids_in_b"] == [fake]
    assert fake not in result["pairs"][0]["consistency_grounding_basis"]


def test_cons_15_run_b_receives_only_frozen_basis_and_not_run_a_prose():
    result, sequence = _run_consistency_pair(_consistency_response(("A", "B", "C"), primary="A", answer="run A private prose"), _consistency_response(("A", "B", "C"), primary="A"))
    assert result["status"] == "PASS"
    context_b = sequence.contexts[1]
    assert context_b["CONSISTENCY_GROUNDING_BASIS"] == ["A", "B", "C"]
    assert context_b["ALLOWED_GROUNDED_RECORD_IDS"] == ["A", "B", "C"]
    assert context_b["known_record_ids"] == ["A", "B", "C"]
    assert "run A private prose" not in json.dumps(context_b)


def test_consistency_signature_excludes_narrative_and_is_canonical():
    first = ConsistencySignature("GROUNDED", "A", ("C", "A", "B"), ("OUT_OF_DOMAIN", "PROTOCOL_SENSITIVITY"))
    second = ConsistencySignature("GROUNDED", "A", ("A", "B", "C"), ("PROTOCOL_SENSITIVITY", "OUT_OF_DOMAIN"))
    assert first.digest == second.digest
    assert first.to_dict()["grounded_record_ids"] == ["A", "B", "C"]


def test_consistency_types_are_exported_with_required_assessment_fields():
    assert {item.name for item in fields(ConsistencyGroundingAssessment)} == {
        "valid", "pair_index", "question", "run_a_call_id", "run_b_call_id", "run_a_grounding_status", "run_b_grounding_status",
        "run_a_ids", "run_b_ids", "normalized_run_a_ids", "normalized_run_b_ids", "new_ids_in_b", "missing_ids_in_b",
        "support_basis_equal", "limitation_codes_equal", "primary_record_equal", "failure_code",
    }
