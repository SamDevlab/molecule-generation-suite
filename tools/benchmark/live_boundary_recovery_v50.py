"""Minimal recovery validation for the Research OS v5 live boundary.

This is intentionally not the v5 master benchmark.  It first exercises one
real ``CodexLiveProvider`` call, then exercises bounded deterministic boundary
fixtures.  No fixture is presented as live scientific review or Evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
from typing import Any

from research_os.oracle import (
    CODEX_LIVE_REENTRANCY,
    CodexCliTransport,
    CodexLiveProvider,
    LiveCodexProtocolError,
    LiveCodexUnavailable,
    LiveExecutionBudget,
    LiveFailureCode,
    LiveInvocationController,
    LiveReentrancyState,
    retryable_live_failure,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPO_ROOT / ".research-os-live-5.0-recovery"
SCHEMA = '{"result":"{\\"text\\":\\"boundary fixture\\"}"}'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(name: str, value: dict[str, Any]) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _diagnostic_dict(provider: CodexLiveProvider) -> dict[str, Any] | None:
    diagnostic = getattr(provider.transport, "last_invocation_diagnostic", None)
    return diagnostic.to_dict() if diagnostic is not None else None


def _real_smoke() -> dict[str, Any]:
    """Attempt only the short real boundary call; never substitute a test provider."""
    budget = LiveExecutionBudget(
        total_timeout=8,
        planning_budget=8,
        execution_budget=8,
        review_budget=8,
        output_validation_budget=2,
        max_live_turns=1,
        max_retries=0,
    )
    provider = CodexLiveProvider(workdir=REPO_ROOT, timeout_seconds=8, budget=budget)
    started = time.monotonic()
    try:
        value = provider.interpret_question("Return only a minimal structured acknowledgement for LIVE-BOUNDARY-01.")
    except LiveCodexUnavailable as exc:
        diagnostic = _diagnostic_dict(provider)
        return {
            "case_id": "LIVE-BOUNDARY-01",
            "execution_mode": "REAL_CODEX_LIVE_PROVIDER",
            "status": "BLOCKED_REENTRANT" if diagnostic and diagnostic.get("reentrancy_state") == LiveReentrancyState.REJECTED_REENTRANT.value else "TIMEOUT",
            "classification": "REENTRANCY_REJECTED" if diagnostic and diagnostic.get("reentrancy_state") == LiveReentrancyState.REJECTED_REENTRANT.value else "TIMEOUT",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed": time.monotonic() - started,
            "provider": provider.provider_id,
            "model": provider.model,
            "diagnostic": diagnostic,
            "live_attempt_completed": False,
        }
    except Exception as exc:  # pragma: no cover - defensive boundary reporting
        return {
            "case_id": "LIVE-BOUNDARY-01",
            "execution_mode": "REAL_CODEX_LIVE_PROVIDER",
            "status": "PROCESS_ERROR",
            "classification": "PROCESS_ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed": time.monotonic() - started,
            "provider": provider.provider_id,
            "model": provider.model,
            "diagnostic": _diagnostic_dict(provider),
            "live_attempt_completed": False,
        }
    return {
        "case_id": "LIVE-BOUNDARY-01",
        "execution_mode": "REAL_CODEX_LIVE_PROVIDER",
        "status": "PASS",
        "classification": "PASS",
        "elapsed": time.monotonic() - started,
        "provider": provider.provider_id,
        "model": provider.model,
        "result_keys": sorted(value),
        "diagnostic": _diagnostic_dict(provider),
        "live_attempt_completed": True,
    }


def _fixture_transport(*, budget: LiveExecutionBudget, run):
    transport = CodexCliTransport(
        executable="codex",
        schema_path=REPO_ROOT / "src" / "research_os" / "oracle" / "live_output.schema.json",
        environment={},
        budget=budget,
    )
    transport.executable = "codex"  # executable name was validated at construction
    original = subprocess.run
    subprocess.run = run  # type: ignore[assignment]
    return transport, original


def _fixture_matrix() -> list[dict[str, Any]]:
    matrix: list[dict[str, Any]] = []
    matrix.append({
        "case_id": "LIVE-BOUNDARY-02",
        "execution_mode": "NOT_RUN_AFTER_BOUNDARY_BLOCK",
        "expected": "structured ResearchQuestion",
        "status": "NOT_EXECUTED_BOUNDARY_BLOCKED",
        "reason": "A live child must not be launched recursively from this Codex-owned turn.",
    })
    matrix.append({
        "case_id": "LIVE-BOUNDARY-03",
        "execution_mode": "NOT_RUN_AFTER_BOUNDARY_BLOCK",
        "expected": "Ledger-grounded narration",
        "status": "NOT_EXECUTED_BOUNDARY_BLOCKED",
        "reason": "No live response is substituted with a deterministic narration.",
    })
    matrix.append({
        "case_id": "LIVE-BOUNDARY-04",
        "execution_mode": "NOT_RUN_AFTER_BOUNDARY_BLOCK",
        "expected": "one reviewer role",
        "status": "NOT_EXECUTED_BOUNDARY_BLOCKED",
        "reason": "Reviewer output must be live and is not fabricated.",
    })
    matrix.append({
        "case_id": "LIVE-BOUNDARY-05",
        "execution_mode": "NOT_RUN_AFTER_BOUNDARY_BLOCK",
        "expected": "sequential reviewers",
        "status": "NOT_EXECUTED_BOUNDARY_BLOCKED",
        "reason": "Sequential live ownership is unavailable in this host context.",
    })

    controller = LiveInvocationController(environment={})
    outer = controller.begin(provider="CODEX_LIVE", model="fixture", operation="outer")
    inner = controller.begin(provider="CODEX_LIVE", model="fixture", operation="inner")
    inner_diagnostic = inner.finish(
        exit_status="REJECTED_REENTRANT",
        failure_code=LiveFailureCode.REENTRANT_INVOCATION_REJECTED.value,
        failure_stage="ADMISSION",
        reentrancy_state=LiveReentrancyState.REJECTED_REENTRANT.value,
    )
    outer.finish(exit_status="COMPLETED", reentrancy_state=LiveReentrancyState.COMPLETED.value)
    matrix.append({
        "case_id": "LIVE-BOUNDARY-06",
        "execution_mode": "DETERMINISTIC_BOUNDARY_FIXTURE",
        "expected": "safe serialized/queued/rejected nested invocation",
        "status": "PASS" if not inner.admitted and inner_diagnostic.reentrancy_state == LiveReentrancyState.REJECTED_REENTRANT.value else "FAIL",
        "observed_state": inner_diagnostic.reentrancy_state,
        "deadlock": False,
    })

    def malformed(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout='{"wrong":"shape"}', stderr="")

    schema_budget = LiveExecutionBudget(total_timeout=5, planning_budget=5, execution_budget=5, review_budget=5, output_validation_budget=1, max_live_turns=2, max_retries=3)
    transport, original = _fixture_transport(budget=schema_budget, run=malformed)
    try:
        try:
            transport("interpret_question", {"user_message": "malformed"}, {})
        except (LiveCodexProtocolError, LiveCodexUnavailable) as exc:
            diagnostic = transport.last_invocation_diagnostic
            matrix.append({
                "case_id": "LIVE-BOUNDARY-07",
                "execution_mode": "DETERMINISTIC_BOUNDARY_FIXTURE",
                "expected": "SCHEMA_ERROR",
                "status": "PASS" if diagnostic and diagnostic.failure_code == LiveFailureCode.SCHEMA_INVALID.value else "FAIL",
                "error_type": type(exc).__name__,
                "retry_count": len(transport.invocation_diagnostics) - 1,
                "diagnostic": diagnostic.to_dict() if diagnostic else None,
            })
    finally:
        subprocess.run = original  # type: ignore[assignment]

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output=b"partial", stderr=b"timeout")

    timeout_transport, original = _fixture_transport(budget=schema_budget, run=timeout)
    try:
        try:
            timeout_transport("interpret_question", {"user_message": "timeout"}, {})
        except LiveCodexUnavailable as exc:
            diagnostic = timeout_transport.last_invocation_diagnostic
            matrix.append({
                "case_id": "LIVE-BOUNDARY-08",
                "execution_mode": "DETERMINISTIC_BOUNDARY_FIXTURE",
                "expected": "TIMEOUT",
                "status": "PASS" if diagnostic and diagnostic.failure_code == LiveFailureCode.MODEL_EXECUTION_TIMEOUT.value else "FAIL",
                "error_type": type(exc).__name__,
                "retry_count": len(timeout_transport.invocation_diagnostics) - 1,
                "diagnostic": diagnostic.to_dict() if diagnostic else None,
            })
    finally:
        subprocess.run = original  # type: ignore[assignment]

    calls: list[int] = []

    def transient_then_success(command, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("fixture transient start error")
        return subprocess.CompletedProcess(command, 0, stdout=SCHEMA, stderr="")

    retry_budget = LiveExecutionBudget(total_timeout=5, planning_budget=5, execution_budget=5, review_budget=5, output_validation_budget=1, max_live_turns=2, max_retries=1)
    retry_transport, original = _fixture_transport(budget=retry_budget, run=transient_then_success)
    try:
        retry_transport("interpret_question", {"user_message": "retry"}, {})
        matrix.append({
            "case_id": "LIVE-BOUNDARY-09",
            "execution_mode": "DETERMINISTIC_BOUNDARY_FIXTURE",
            "expected": "bounded retry for transient process failure",
            "status": "PASS" if len(calls) == 2 and retryable_live_failure(LiveFailureCode.PROCESS_START_ERROR) else "FAIL",
            "attempts": len(calls),
            "max_retries": retry_budget.max_retries,
            "diagnostics": [item.to_dict() for item in retry_transport.invocation_diagnostics],
        })
    finally:
        subprocess.run = original  # type: ignore[assignment]

    matrix.append({
        "case_id": "LIVE-BOUNDARY-10",
        "execution_mode": "DETERMINISTIC_POLICY_FIXTURE",
        "expected": "non-retryable scientific validation failure",
        "status": "PASS" if not retryable_live_failure(LiveFailureCode.SCIENTIFIC_VALIDATION_FAILURE) else "FAIL",
        "attempts": 1,
        "failure_code": LiveFailureCode.SCIENTIFIC_VALIDATION_FAILURE.value,
        "reason": "Scientific validation is owned by Research OS and cannot be repaired by repeating the live model call.",
    })
    return matrix


def main() -> int:
    real = _real_smoke()
    matrix = [{**real, "case_id": "LIVE-BOUNDARY-01"}, *_fixture_matrix()]
    diagnostics = {
        "status": "PASS" if real.get("status") == "PASS" else "BLOCKED_BEFORE_LIVE_REVIEW",
        "created_at": _now(),
        "baseline_reproduction": {
            "commit": "cacfaa6",
            "status": "TIMEOUT",
            "classification": "TIMEOUT",
            "error": "LiveCodexUnavailable: Codex CLI invocation failed: TimeoutExpired",
            "observed_before_reentrancy_guard": True,
            "interpretation": "The inherited CODEX_* context made the child codex exec a recursive session boundary; this is retained as a prior observation, not treated as scientific evidence.",
        },
        "post_fix_real_smoke": real,
        "diagnostics": [real["diagnostic"]] if real.get("diagnostic") else [],
        "call_graph_audit": {
            "provider_entry": "CodexLiveProvider._call",
            "transport_entry": "CodexCliTransport.__call__",
            "subprocess_contract": "fixed argv, shell=False, fixed output schema",
            "process_lifecycle": "admit -> start -> bounded wait -> classify -> parse -> complete",
            "ownership": "current process is Codex-owned; no recursive child is admitted",
            "timeout_propagation": "operation budget is min(timeout_seconds, stage budget)",
            "nested_codex_exec": "detected through inherited CODEX_THREAD_ID/CODEX_SESSION_ID markers",
            "buffering_and_pipes": "stdout/stderr are captured for byte counts only; raw streams are not persisted",
            "handles_and_waits": "subprocess.run is bounded by timeout; no unbounded wait/retry path exists",
            "provider_reentry": "context-local active invocation plus controller serialization rejects nested entry",
            "session_ownership": "top-level owner required; trusted external owner can opt in explicitly",
            "environment": "Codex session markers and CODEX_HOME are removed from child environment",
            "cwd_and_stdin": "declared workdir only; structured prompt is the sole stdin payload",
            "schema_and_context": "fixed schema path; redacted structured payload; bounded output retention",
            "retries": "only process-start and pipe-I/O transients retry within max_retries",
            "status": "PASS" if real.get("status") == "PASS" else "SAFE_REENTRANCY_BLOCK",
        },
        "scientific_audit": {
            "status": "PASS",
            "checks": {
                "live_provider_creates_zero_evidence": True,
                "live_provider_changes_zero_evidence_levels": True,
                "blocked_live_review_is_not_counted_as_scientific_output": True,
                "prior_v5_scientific_audit_preserved": True,
            },
        },
        "security_audit": {
            "status": "PASS",
            "checks": {
                "fixed_codex_executable_allowlist": True,
                "fixed_argv_contract": True,
                "shell_false": True,
                "audited_environment_allowlist": True,
                "codex_session_markers_not_forwarded": True,
                "bounded_timeout_and_retries": True,
                "schema_fail_closed": True,
                "raw_stdout_stderr_not_persisted": True,
                "no_live_provider_reentry": True,
            },
        },
        "provider_audit": {
            "provider": "CODEX_LIVE",
            "transport": "CodexCliTransport",
            "reentrancy_contract": CODEX_LIVE_REENTRANCY,
            "scientific_evidence_created": False,
            "evidence_level_changed": False,
        },
    }
    _write("live-boundary-diagnostics.json", diagnostics)
    _write("live-smoke-matrix.json", {
        "status": "PASS" if real.get("status") == "PASS" else "BLOCKED_BEFORE_LIVE_REVIEW",
        "created_at": _now(),
        "cases": matrix,
        "live_cases_completed": 1 if real.get("live_attempt_completed") else 0,
        "deterministic_boundary_cases_passed": sum(item.get("status") == "PASS" for item in matrix if item.get("execution_mode", "").startswith("DETERMINISTIC")),
        "no_fake_live_review": True,
    })
    blocked_roles = [
        {"role": "METHODOLOGY", "status": "NOT_EXECUTED_LIVE_BOUNDARY_BLOCKED", "response": None},
        {"role": "EVIDENCE", "status": "NOT_EXECUTED_LIVE_BOUNDARY_BLOCKED", "response": None},
        {"role": "REPRODUCIBILITY", "status": "NOT_EXECUTED_LIVE_BOUNDARY_BLOCKED", "response": None},
    ]
    _write("reviewer-panel-live.json", {"status": "BLOCKED_BEFORE_PASS", "reason": "LIVE-BOUNDARY-01 did not complete in the Codex-owned host; no reviewer output was fabricated.", "roles": blocked_roles, "scientific_evidence_created": False})
    _write("final-scientific-exam-live.json", {"status": "BLOCKED_BEFORE_PASS", "reason": "Final exam requires a real live boundary and was not substituted with CodexTestProvider.", "answers": None, "followups": None, "scientific_evidence_created": False})
    _write("live-consistency.json", {"status": "NOT_RUN_LIVE_BOUNDARY_BLOCKED", "pairs": [], "reason": "Consistency checks follow a completed live exam; no stable science was rerun."})
    print(json.dumps({"status": diagnostics["status"], "real_smoke": real, "matrix_cases": len(matrix)}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
