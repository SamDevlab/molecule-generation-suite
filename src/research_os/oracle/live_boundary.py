"""Bounded, auditable control plane for the local Codex live boundary.

This module deliberately contains no scientific authority.  It records the
lifecycle of a live reasoning subprocess and prevents a Codex-owned process
from recursively starting another live Codex turn.  The boundary is kept
separate from the provider's scientific contracts so that failures remain
visible instead of being converted into Evidence, Claims, or Decisions.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import os
from threading import Lock
from typing import Any, Mapping
import uuid


CODEX_LIVE_REENTRANCY = "CODEX_LIVE_REENTRANCY"


class LiveReentrancyState(str, Enum):
    ALLOWED_TOP_LEVEL = "ALLOWED_TOP_LEVEL"
    QUEUED = "QUEUED"
    SERIALIZED = "SERIALIZED"
    REJECTED_REENTRANT = "REJECTED_REENTRANT"
    TIMED_OUT = "TIMED_OUT"
    COMPLETED = "COMPLETED"


class LiveFailureCode(str, Enum):
    PROVIDER_START_TIMEOUT = "PROVIDER_START_TIMEOUT"
    MODEL_EXECUTION_TIMEOUT = "MODEL_EXECUTION_TIMEOUT"
    NESTED_REENTRANCY_TIMEOUT = "NESTED_REENTRANCY_TIMEOUT"
    PIPE_IO_TIMEOUT = "PIPE_IO_TIMEOUT"
    OUTPUT_VALIDATION_TIMEOUT = "OUTPUT_VALIDATION_TIMEOUT"
    TOOL_EXECUTION_TIMEOUT = "TOOL_EXECUTION_TIMEOUT"
    UNKNOWN_TIMEOUT = "UNKNOWN_TIMEOUT"
    REENTRANT_INVOCATION_REJECTED = "REENTRANT_INVOCATION_REJECTED"
    LIVE_TURN_BUDGET_EXCEEDED = "LIVE_TURN_BUDGET_EXCEEDED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROCESS_START_ERROR = "PROCESS_START_ERROR"
    PROCESS_ERROR = "PROCESS_ERROR"
    PIPE_IO_ERROR = "PIPE_IO_ERROR"
    OUTPUT_TOO_LARGE = "OUTPUT_TOO_LARGE"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    SCIENTIFIC_VALIDATION_FAILURE = "SCIENTIFIC_VALIDATION_FAILURE"


class LiveFailureStage(str, Enum):
    ADMISSION = "ADMISSION"
    PROVIDER_START = "PROVIDER_START"
    MODEL_EXECUTION = "MODEL_EXECUTION"
    PIPE_IO = "PIPE_IO"
    OUTPUT_VALIDATION = "OUTPUT_VALIDATION"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    COMPLETION = "COMPLETION"
    NONE = "NONE"


_ACTIVE_INVOCATION: ContextVar["LiveInvocationDiagnostic | None"] = ContextVar(
    "research_os_live_invocation", default=None
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


@dataclass(frozen=True)
class LiveExecutionBudget:
    """Explicit upper bounds for one bounded live research operation."""

    total_timeout: float = 120.0
    planning_budget: float = 30.0
    execution_budget: float = 60.0
    review_budget: float = 30.0
    output_validation_budget: float = 5.0
    max_live_turns: int = 16
    max_retries: int = 0

    def __post_init__(self) -> None:
        for name in (
            "total_timeout",
            "planning_budget",
            "execution_budget",
            "review_budget",
            "output_validation_budget",
        ):
            value = float(getattr(self, name))
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if int(self.max_live_turns) < 1:
            raise ValueError("max_live_turns must be at least one")
        if int(self.max_retries) < 0:
            raise ValueError("max_retries cannot be negative")

    def timeout_for(self, operation: str) -> float:
        operation_name = str(operation)
        if operation_name in {"generate_plan", "repair_plan", "discover_problems", "generate_research_program", "prioritize_research"}:
            stage_budget = self.planning_budget
        elif operation_name in {"final_exam_followup", "final_exam_followups", "final_autonomous_exam", "summarize_results"}:
            stage_budget = self.review_budget
        elif operation_name in {"execute", "run_engine", "tool_execution"}:
            stage_budget = self.execution_budget
        else:
            stage_budget = self.planning_budget
        return min(float(self.total_timeout), float(stage_budget))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiveInvocationDiagnostic:
    """One immutable-at-completion record for a live subprocess attempt."""

    invocation_id: str
    parent_invocation_id: str | None
    depth: int
    provider: str
    model: str
    command_contract: str
    started_at: str
    completed_at: str | None
    elapsed: float | None
    timeout_budget: float
    exit_status: str
    stdout_bytes: int
    stderr_bytes: int
    schema_status: str
    failure_code: str | None
    failure_stage: str
    reentrancy_state: str = LiveReentrancyState.ALLOWED_TOP_LEVEL.value
    operation: str = ""
    attempt: int = 1
    max_attempts: int = 1
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {key: _enum_value(value) for key, value in asdict(self).items()}

    def completed(self, **changes: Any) -> "LiveInvocationDiagnostic":
        changes.setdefault("completed_at", _utc_now())
        if self.elapsed is None:
            started = datetime.fromisoformat(self.started_at)
            completed = datetime.fromisoformat(str(changes["completed_at"]))
            changes["elapsed"] = max(0.0, (completed - started).total_seconds())
        return replace(self, **changes)


@dataclass
class LiveInvocationHandle:
    """Admission handle; completion emits exactly one diagnostic."""

    diagnostic: LiveInvocationDiagnostic
    admitted: bool
    _controller: "LiveInvocationController"
    _token: Token[LiveInvocationDiagnostic | None] | None = None
    _finished: bool = False

    def finish(self, **changes: Any) -> LiveInvocationDiagnostic:
        if self._finished:
            return self.diagnostic
        self._finished = True
        completed = self.diagnostic.completed(**changes)
        self.diagnostic = completed
        self._controller._finish(self, completed)
        return completed


class LiveInvocationController:
    """Admit only bounded top-level invocations in the current host.

    ``CODEX_THREAD_ID``/``CODEX_SESSION_ID`` identify a Codex-owned host.  A
    trusted external runner may explicitly set ``allow_codex_host_context``;
    the default is fail-closed because launching ``codex exec`` from inside a
    Codex turn is a recursive session boundary and can deadlock or time out.
    """

    _lock = Lock()

    def __init__(
        self,
        budget: LiveExecutionBudget | None = None,
        *,
        environment: Mapping[str, str] | None = None,
        allow_codex_host_context: bool = False,
        command_contract: str = "codex exec --ephemeral --skip-git-repo-check --sandbox read-only --color never --output-schema <fixed-schema> -",
        diagnostic_sink: list[LiveInvocationDiagnostic] | None = None,
    ) -> None:
        self.budget = budget or LiveExecutionBudget()
        self.environment = dict(environment if environment is not None else os.environ)
        self.allow_codex_host_context = bool(allow_codex_host_context)
        self.command_contract = str(command_contract)
        self.diagnostics = diagnostic_sink if diagnostic_sink is not None else []
        self._live_turns = 0
        self._active_invocations = 0

    @property
    def active(self) -> LiveInvocationDiagnostic | None:
        return _ACTIVE_INVOCATION.get()

    @property
    def live_turns(self) -> int:
        return self._live_turns

    def _host_parent(self) -> tuple[str | None, int]:
        active = self.active
        if active is not None:
            return active.invocation_id, active.depth + 1
        thread_id = self.environment.get("CODEX_THREAD_ID")
        session_id = self.environment.get("CODEX_SESSION_ID")
        if thread_id or session_id:
            identity = thread_id or session_id
            return f"CODEX_CONTEXT:{identity}", 1
        return None, 0

    def begin(self, *, provider: str, model: str, operation: str, timeout_budget: float | None = None) -> LiveInvocationHandle:
        parent_id, depth = self._host_parent()
        invocation_id = f"LIVE-{uuid.uuid4().hex[:16].upper()}"
        timeout = float(timeout_budget if timeout_budget is not None else self.budget.total_timeout)
        base = LiveInvocationDiagnostic(
            invocation_id=invocation_id,
            parent_invocation_id=parent_id,
            depth=depth,
            provider=str(provider),
            model=str(model),
            command_contract=self.command_contract,
            started_at=_utc_now(),
            completed_at=None,
            elapsed=None,
            timeout_budget=timeout,
            exit_status="RUNNING",
            stdout_bytes=0,
            stderr_bytes=0,
            schema_status="NOT_CHECKED",
            failure_code=None,
            failure_stage=LiveFailureStage.NONE.value,
            reentrancy_state=(
                LiveReentrancyState.REJECTED_REENTRANT.value
                if parent_id is not None
                else LiveReentrancyState.ALLOWED_TOP_LEVEL.value
            ),
            operation=str(operation),
            max_attempts=self.budget.max_retries + 1,
        )
        if parent_id is not None and not self.allow_codex_host_context:
            return LiveInvocationHandle(base, False, self)
        with self._lock:
            if self._active_invocations:
                serialized = replace(
                    base,
                    parent_invocation_id=parent_id or "CONTROLLER_ACTIVE",
                    depth=max(depth, 1),
                    reentrancy_state=LiveReentrancyState.REJECTED_REENTRANT.value,
                )
                return LiveInvocationHandle(serialized, False, self)
            if self._live_turns >= self.budget.max_live_turns:
                exhausted = base.completed(
                    exit_status="BUDGET_EXHAUSTED",
                    failure_code=LiveFailureCode.LIVE_TURN_BUDGET_EXCEEDED.value,
                    failure_stage=LiveFailureStage.ADMISSION.value,
                    reentrancy_state=LiveReentrancyState.REJECTED_REENTRANT.value,
                )
                self.diagnostics.append(exhausted)
                return LiveInvocationHandle(exhausted, False, self, _finished=True)
            self._live_turns += 1
            self._active_invocations += 1
        token = _ACTIVE_INVOCATION.set(base)
        return LiveInvocationHandle(base, True, self, token)

    def _finish(self, handle: LiveInvocationHandle, diagnostic: LiveInvocationDiagnostic) -> None:
        if handle._token is not None:
            _ACTIVE_INVOCATION.reset(handle._token)
            with self._lock:
                self._active_invocations = max(0, self._active_invocations - 1)
        self.diagnostics.append(diagnostic)


def classify_timeout(*, nested: bool = False, stage: LiveFailureStage | str = LiveFailureStage.MODEL_EXECUTION) -> LiveFailureCode:
    """Map a bounded timeout to a stable audit code without retry advice."""

    stage_value = _enum_value(stage)
    if nested:
        return LiveFailureCode.NESTED_REENTRANCY_TIMEOUT
    if stage_value == LiveFailureStage.PROVIDER_START.value:
        return LiveFailureCode.PROVIDER_START_TIMEOUT
    if stage_value == LiveFailureStage.PIPE_IO.value:
        return LiveFailureCode.PIPE_IO_TIMEOUT
    if stage_value == LiveFailureStage.OUTPUT_VALIDATION.value:
        return LiveFailureCode.OUTPUT_VALIDATION_TIMEOUT
    if stage_value == LiveFailureStage.TOOL_EXECUTION.value:
        return LiveFailureCode.TOOL_EXECUTION_TIMEOUT
    if stage_value == LiveFailureStage.MODEL_EXECUTION.value:
        return LiveFailureCode.MODEL_EXECUTION_TIMEOUT
    return LiveFailureCode.UNKNOWN_TIMEOUT


def retryable_live_failure(failure_code: LiveFailureCode | str | None) -> bool:
    """Only transport/process-start transients may be retried.

    A timeout, schema error, scientific validation error, reentrancy rejection,
    and any evidence/PlanValidator failure are intentionally non-retryable.
    """

    code = _enum_value(failure_code)
    return code in {LiveFailureCode.PROVIDER_START_TIMEOUT.value, LiveFailureCode.PROCESS_START_ERROR.value, LiveFailureCode.PIPE_IO_ERROR.value}


def codex_host_context(environment: Mapping[str, str] | None = None) -> bool:
    env = environment if environment is not None else os.environ
    return bool(env.get("CODEX_THREAD_ID") or env.get("CODEX_SESSION_ID") or env.get("CODEX_INTERNAL_ORIGINATOR_OVERRIDE"))
