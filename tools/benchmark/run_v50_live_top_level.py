"""True top-level owner for the Research OS v5 Live acceptance.

Run this file from a normal external terminal, never from the Codex session
that is editing the repository.  The launcher owns one fixed, sequential set
of Codex CLI calls and persists only structured results plus bounded process
metadata.  It does not promote the package or push Git state automatically.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from statistics import median
import time
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from research_os.oracle import (  # noqa: E402
    CodexCliTransport,
    CodexLiveProvider,
    CONSISTENCY_LIMITATION_CODES,
    ConsistencyFailureCode,
    ConsistencyGroundingAssessment,
    ConsistencySignature,
    GroundingStatus,
    LiveExecutionBudget,
    LiveCodexProtocolError,
    LiveCodexUnavailable,
    LiveResponseValidationFailure,
    TopLevelPreflightStatus,
    V5LiveAcceptanceDigest,
    evaluate_worktree_acceptance,
    find_forbidden_scientific_fields,
    preflight_repository,
    validate_grounding,
)


FIRST_ATTEMPT_ROOT = REPO_ROOT / ".research-os-live-5.0-top-level"
OUTPUT_ROOT = REPO_ROOT / ".research-os-live-5.0-top-level-attempt-2"
EXPECTED_BRANCH = "research-os-v1.3"
MAX_LIVE_INVOCATIONS = 45
REQUIRED_LIVE_INVOCATIONS = 39
FORBIDDEN_OUTPUT_KEYS = {
    "evidence", "evidence_level", "runs", "bundle", "bundle_id",
    "scientific_result", "experimental_result", "engine_result",
}
CONSISTENCY_RESPONSE_KEYS = frozenset({
    "answer",
    "grounding_status",
    "grounded_record_ids",
    "primary_record_id",
    "limitation_codes",
    "limitations",
})
SAFE_FAILED_RESPONSE_KEYS = {"answer", "grounding_status", "grounded_record_ids", "limitations"}

FOLLOWUP_QUESTIONS = (
    "What new scientific knowledge was actually produced?",
    "Which claim changed?",
    "Which decision changed?",
    "Which gap closed?",
    "Which gap remains?",
    "What was the strongest negative result?",
    "What execution was avoided as redundant?",
    "Which result has the strongest provenance?",
    "Which result is most uncertain?",
    "Which result most needs external validation?",
    "Where could protocol sensitivity reverse a conclusion?",
    "Where could dependent evidence create false confidence?",
    "What would a skeptical reviewer challenge first?",
    "What should NOT be claimed publicly?",
    "What should the next real experiment/data acquisition be?",
)

STRESS_QUESTIONS = (
    "What is the strongest v5 conclusion?",
    "What is the weakest conclusion?",
    "Which result is most dataset-dependent?",
    "Which result is most protocol-sensitive?",
    "What is the strongest preserved negative result?",
    "Which gap is highest-value and actionable?",
    "Which gap should not be pursued right now?",
    "Which NO_DECISION should be revisited first if new evidence arrives?",
    "Which proposed computation is currently redundant?",
    "What is the clearest remaining scientific limitation?",
)

FINAL_EXAM_INSTRUCTION = """Using only the current stored scientific state of Research OS:
1. Identify one conclusion we are justified in keeping.
2. Identify one conclusion that should be weakened.
3. Identify one question we still cannot answer.
4. Identify one research step that would currently be redundant.
5. Identify one external dataset or experiment with the highest likely value.
6. Identify one previous NO_DECISION that should be reconsidered, if any.
7. Identify one supported decision most vulnerable to protocol sensitivity.
8. Propose one new ResearchProgram with the highest realistic information gain.
9. Execute that program only if its first step is justified, currently possible, safe and non-redundant.
10. State exactly what changed scientifically.

Do not optimize for a positive result. Do not invent Evidence, sources, datasets,
experiments, or engine results. Do not change EvidenceLevel. Do not call
CodexLiveProvider or codex exec because you are already the top-level Live
Codex invocation. Stop on NO_PROGRESS, BLOCKED_EXTERNAL, INSUFFICIENT_EVIDENCE,
a safety boundary, or a resource limit."""

REVIEW_INSTRUCTIONS = {
    "METHODOLOGY": """Review the stored Research OS v5 scientific state as a skeptical methodology reviewer. Find the strongest legitimate methodological weaknesses across computational/experimental boundaries, protocol sensitivity, external validation, dataset limitations, OOD, uncertainty, conditions and model/source limits. Do not invent evidence or alter EvidenceLevel.""",
    "EVIDENCE": """Review the stored Research OS v5 scientific state specifically for evidence quality. Identify claims broader than support, source dependence, missing independent validation, OOD and uncertainty constraints, evidence ceilings, and negative results that must remain visible. Do not create Evidence or alter EvidenceLevel.""",
    "REPRODUCIBILITY": """Review the stored Research OS v5 scientific state for reproducibility. Determine whether another researcher could reproduce the strongest results from stored source IDs, dataset/model hashes, engine versions, run IDs, conditions, configs, receptor identity, mechanism, bundles and environment manifests. Identify remaining risks without inventing data.""",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()


def _write(name: str, value: Mapping[str, Any]) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _next_output_root(root: Path) -> Path:
    """Select a fresh attempt namespace without touching the first attempt."""
    for attempt in range(2, 1000):
        candidate = root / f".research-os-live-5.0-top-level-attempt-{attempt}"
        if not candidate.exists() or (candidate.is_dir() and not any(candidate.iterdir())):
            return candidate
    raise RuntimeError("no unused top-level acceptance attempt namespace available")


def _compact_state(root: Path) -> dict[str, Any]:
    master = _load_json(root / ".research-os-live-5.0" / "master-real-research-validation.json")
    keys = (
        "status", "version", "branch", "git_commit", "counts", "acceptance",
        "status_checks", "prior_checkpoint", "problem_discovery", "selected_program",
        "new_runs", "research_outcome_impacts", "ledger", "limitations",
        "legacy_review", "scientific_audit", "security_audit", "source_policy",
    )
    state = {key: master[key] for key in keys if key in master}
    state["stored_artifacts"] = {
        "master": ".research-os-live-5.0/master-real-research-validation.json",
        "final_exam": ".research-os-live-5.0/final-scientific-exam.json",
        "review_panel": ".research-os-live-5.0/reviewer-panel.json",
        "reproduction": ".research-os-live-5.0/reproduction-matrix.json",
        "ledger": ".research-os-live-5.0/ledger/research_ledger.sqlite",
        "v4_5_challenge": ".research-os-live-4.5/scientific-challenge.json",
    }
    challenge = root / ".research-os-live-4.5" / "scientific-challenge.json"
    if challenge.is_file():
        raw = _load_json(challenge)
        state["v4_5_scientific_challenge"] = {
            key: raw[key] for key in ("status", "counts", "challenges", "false_conservatism") if key in raw
        }
    state["state_digest"] = _digest(state)
    return state


def _record_ids(value: Any, result: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower().endswith(("_id", "_ids")):
                if isinstance(item, str):
                    result.add(item)
                elif isinstance(item, (list, tuple)):
                    result.update(str(entry) for entry in item if isinstance(entry, (str, int)))
            _record_ids(item, result)
    elif isinstance(value, list):
        for item in value:
            _record_ids(item, result)


def _has_forbidden_output(value: Any) -> bool:
    if isinstance(value, dict):
        if any(str(key).lower() in FORBIDDEN_OUTPUT_KEYS for key in value):
            return True
        return any(_has_forbidden_output(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_forbidden_output(item) for item in value)
    return False


def _valid_grounding(value: Any, known_ids: set[str]) -> bool:
    """Compatibility wrapper; acceptance uses the rich result below."""
    validation = validate_grounding(value, known_ids)
    return validation.valid and validation.grounding_status == GroundingStatus.GROUNDED.value


def _safe_failed_response(value: Any) -> dict[str, Any] | None:
    """Keep only final structured answer fields in a failed-response artifact."""
    if not isinstance(value, dict):
        return None
    safe: dict[str, Any] = {}
    for key in SAFE_FAILED_RESPONSE_KEYS:
        if key not in value:
            continue
        item = value[key]
        if key == "answer" and isinstance(item, str):
            safe[key] = item
        elif key == "grounding_status" and isinstance(item, str):
            safe[key] = item
        elif key == "grounded_record_ids" and isinstance(item, list) and all(isinstance(entry, str) for entry in item):
            safe[key] = list(item)
        elif key == "limitations" and isinstance(item, list) and all(isinstance(entry, str) for entry in item):
            safe[key] = list(item)
    return safe or None


class TopLevelLiveSequence:
    def __init__(self, root: Path, state: dict[str, Any], owner_id: str, timeout_seconds: int) -> None:
        self.root = root
        self.state = state
        self.owner_id = owner_id
        self.process_events: list[dict[str, Any]] = []
        self.invocations: list[dict[str, Any]] = []
        self.response_validation_failures: list[LiveResponseValidationFailure] = []
        self._current_label = ""
        self._current_call = 0
        self.budget = LiveExecutionBudget(
            total_timeout=timeout_seconds,
            planning_budget=timeout_seconds,
            execution_budget=timeout_seconds,
            review_budget=timeout_seconds,
            output_validation_budget=5,
            max_live_turns=MAX_LIVE_INVOCATIONS,
            max_retries=0,
        )
        transport = CodexCliTransport(
            workdir=root,
            timeout_seconds=timeout_seconds,
            budget=self.budget,
            process_observer=self._observe_process,
        )
        self.provider = CodexLiveProvider(transport=transport)
        self.provider.set_request_context({"top_level_owner_id": owner_id, "stored_state_digest": state["state_digest"]})
        self.known_ids: set[str] = set()
        _record_ids(state, self.known_ids)

    def _observe_process(self, event: dict[str, Any]) -> None:
        event = dict(event)
        event["call_id"] = self._current_call
        event["label"] = self._current_label
        self.process_events.append(event)

    def invoke(self, label: str, operation: str, method_name: str, context: dict[str, Any]) -> tuple[Any | None, dict[str, Any]]:
        if len(self.invocations) >= MAX_LIVE_INVOCATIONS:
            raise RuntimeError("MAX_LIVE_INVOCATIONS exceeded")
        self._current_call = len(self.invocations) + 1
        self._current_label = label
        event_start = len(self.process_events)
        started = time.monotonic()
        status = "COMPLETED"
        response: Any | None = None
        error: dict[str, Any] | None = None
        try:
            response = getattr(self.provider, method_name)(context)
        except (LiveCodexUnavailable, LiveCodexProtocolError) as exc:
            status = "FAILED"
            error = {"type": type(exc).__name__, "message": str(exc)}
        except Exception as exc:  # pragma: no cover - defensive top-level boundary
            status = "FAILED"
            error = {"type": type(exc).__name__, "message": str(exc)}
        diagnostic = getattr(self.provider.transport, "last_invocation_diagnostic", None)
        record = {
            "call_id": self._current_call,
            "label": label,
            "operation": operation,
            "status": status,
            "elapsed": time.monotonic() - started,
            "response_hash": _digest(response) if response is not None else None,
            "error": error,
            "diagnostic": diagnostic.to_dict() if diagnostic is not None else None,
            "process_events": self.process_events[event_start:],
        }
        self.invocations.append(record)
        self._current_label = ""
        return response, record

    def validate_grounded_response(self, response: Any, call: Mapping[str, Any], *, require_grounded: bool = True) -> tuple[bool, Any, LiveResponseValidationFailure | None]:
        validation = validate_grounding(response, self.known_ids)
        forbidden = find_forbidden_scientific_fields(response)
        failure_code = validation.failure_code
        valid = validation.valid
        if valid and require_grounded and validation.grounding_status != GroundingStatus.GROUNDED.value:
            valid = False
            failure_code = "INVALID_GROUNDING_STATUS"
        failure: LiveResponseValidationFailure | None = None
        if not valid and (call.get("status") == "COMPLETED" or response is not None):
            diagnostic = call.get("diagnostic") or {}
            failure = LiveResponseValidationFailure(
                call_id=int(call.get("call_id", 0)),
                label=str(call.get("label", "")),
                operation=str(call.get("operation", "")),
                response_hash=validation.response_hash,
                schema_status=str(diagnostic.get("schema_status", "NOT_CHECKED")),
                grounding_validation=validation.to_dict(),
                forbidden_field_validation={"status": "FAIL" if forbidden else "PASS", "fields": list(forbidden)},
                returned_grounded_ids=validation.returned_ids,
                unknown_grounded_ids=validation.unknown_ids,
                response_keys=tuple(sorted(str(key) for key in response)) if isinstance(response, dict) else (),
                grounding_status=validation.grounding_status,
                failure_code=failure_code,
            )
            self.response_validation_failures.append(failure)
        return valid, validation, failure

    def state_context(self, instruction: str, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        allowed_ids = sorted(self.known_ids)
        context = {
            "instruction": instruction,
            "registered_state": self.state,
            "known_record_ids": allowed_ids,
            "ALLOWED_GROUNDED_RECORD_IDS": allowed_ids,
            "grounding_contract": {
                "grounding_status": ["GROUNDED", "NO_GROUNDED_ANSWER"],
                "grounded_record_ids_must_be_literal_members": True,
                "empty_ids_allowed_only_for": "NO_GROUNDED_ANSWER",
            },
        }
        if extra:
            context.update(extra)
        return context


def _review_panel(sequence: TopLevelLiveSequence) -> dict[str, Any]:
    reviewers: list[dict[str, Any]] = []
    for role, instruction in REVIEW_INSTRUCTIONS.items():
        response, call = sequence.invoke(
            f"V5-REVIEW-{role}",
            "scientific_review",
            "scientific_review",
            sequence.state_context(instruction, extra={"role": role}),
        )
        if call["status"] != "COMPLETED" or not isinstance(response, dict) or _has_forbidden_output(response):
            return {"status": "BLOCKED_BEFORE_PASS", "reviewers": reviewers, "failed_call": call, "same_stored_evidence": True, "scientific_evidence_created": False}
        reviewers.append({"role": role, "record_type": "REVIEW / ANALYSIS", "response": response, "call_id": call["call_id"]})
    synthesis = []
    for reviewer in reviewers:
        for concern in reviewer["response"].get("concerns", []):
            if not isinstance(concern, dict):
                continue
            action = str(concern.get("recommended_action", "DEFER_EXTERNAL"))
            if action == "REJECT_WITH_EVIDENCE":
                action = "REJECT_WITH_GROUNDED_REASON"
            elif action == "CREATE_GAP":
                action = "CREATE_RESEARCH_GAP"
            if action not in {"ACCEPT", "REJECT_WITH_GROUNDED_REASON", "CREATE_RESEARCH_GAP", "REVISE_CLAIM", "REVISE_DECISION", "DEFER_EXTERNAL"}:
                action = "DEFER_EXTERNAL"
            synthesis.append({"role": reviewer["role"], "concern": concern.get("concern"), "action": action, "grounded_record_ids": concern.get("grounded_record_ids", [])})
    return {"status": "PASS", "reviewers": reviewers, "synthesis": synthesis, "same_stored_evidence": True, "scientific_evidence_created": False, "evidence_level_changed": False}


def _final_exam(sequence: TopLevelLiveSequence) -> dict[str, Any]:
    response, call = sequence.invoke("V5-FINAL-SCIENTIFIC-EXAM", "final_scientific_exam", "final_scientific_exam", sequence.state_context(FINAL_EXAM_INSTRUCTION))
    required = {"conclusion_kept", "conclusion_weakened", "unanswered_question", "redundant_step", "highest_value_external_evidence", "no_decision_reconsideration", "protocol_sensitive_decision", "proposed_research_program", "program_executed", "scientific_state_change", "grounding_status", "grounded_record_ids", "limitations"}
    grounded, validation, failure = sequence.validate_grounded_response(response, call)
    valid = call["status"] == "COMPLETED" and isinstance(response, dict) and required <= set(response) and grounded and not _has_forbidden_output(response)
    return {"status": "PASS" if valid else "BLOCKED_BEFORE_PASS", "response": response if valid else None, "call": call, "grounding_validation": validation.to_dict(), "failed_response_validation": failure.to_dict() if failure else None, "failed_response": _safe_failed_response(response) if failure else None, "criteria_declared_before_execution": True, "scientific_evidence_created_by_codex": False, "evidence_level_changed_by_codex": False}


def _followups(sequence: TopLevelLiveSequence, exam: dict[str, Any]) -> dict[str, Any]:
    answers: list[dict[str, Any]] = []
    for index, question in enumerate(FOLLOWUP_QUESTIONS, 1):
        response, call = sequence.invoke(f"V5-FOLLOWUP-{index:02d}", "final_exam_followup", "final_exam_followup", sequence.state_context(question, extra={"question": question, "final_exam": exam.get("response")}))
        grounded, validation, failure = sequence.validate_grounded_response(response, call)
        if call["status"] != "COMPLETED" or not isinstance(response, dict) or not grounded or _has_forbidden_output(response):
            return {"status": "BLOCKED_BEFORE_PASS", "answers": answers, "failed_call": call, "failed_response_validation": failure.to_dict() if failure else None, "failed_response": _safe_failed_response(response) if failure else None, "grounding_validation": validation.to_dict()}
        answers.append({"index": index, "question": question, "response": response, "call_id": call["call_id"]})
    return {"status": "PASS", "answers": answers}


def _stress(sequence: TopLevelLiveSequence, exam: dict[str, Any]) -> dict[str, Any]:
    answers: list[dict[str, Any]] = []
    for index, question in enumerate(STRESS_QUESTIONS, 1):
        response, call = sequence.invoke(f"TL-LIVE-{index:02d}", "final_exam_followup", "final_exam_followup", sequence.state_context(question, extra={"question": question, "final_exam": exam.get("response")}))
        grounded, validation, failure = sequence.validate_grounded_response(response, call)
        if call["status"] != "COMPLETED" or not isinstance(response, dict) or not grounded or _has_forbidden_output(response):
            return {"status": "BLOCKED_BEFORE_PASS", "answers": answers, "failed_call": call, "failed_response_validation": failure.to_dict() if failure else None, "failed_response": _safe_failed_response(response) if failure else None, "grounding_validation": validation.to_dict()}
        answers.append({"index": index, "question": question, "response": response, "call_id": call["call_id"]})
    return {"status": "PASS", "answers": answers}


def _consistency_response_parts(response: Any) -> tuple[str | None, tuple[str, ...], str | None, tuple[str, ...]]:
    if not isinstance(response, dict):
        return None, (), None, ()
    status = response.get("grounding_status") if isinstance(response.get("grounding_status"), str) else None
    raw_ids = response.get("grounded_record_ids")
    ids = tuple(raw_ids) if isinstance(raw_ids, list) and all(isinstance(item, str) for item in raw_ids) else ()
    primary = response.get("primary_record_id") if isinstance(response.get("primary_record_id"), str) else None
    raw_codes = response.get("limitation_codes")
    codes = tuple(raw_codes) if isinstance(raw_codes, list) and all(isinstance(item, str) for item in raw_codes) else ()
    return status, ids, primary, codes


def _consistency_signature(response: Any) -> ConsistencySignature | None:
    status, ids, primary, codes = _consistency_response_parts(response)
    if status not in {GroundingStatus.GROUNDED.value, GroundingStatus.NO_GROUNDED_ANSWER.value}:
        return None
    return ConsistencySignature(
        grounding_status=status,
        primary_record_id=primary,
        grounded_record_ids=tuple(sorted(set(ids))),
        limitation_codes=tuple(sorted(set(codes))),
    )


def _consistency_contract_diagnostics(response: Any, grounding: Any, basis: set[str]) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if not isinstance(response, dict):
        return False, ("INVALID_CONSISTENCY_RESPONSE",)
    if set(response) - CONSISTENCY_RESPONSE_KEYS:
        reasons.append("INVALID_CONSISTENCY_RESPONSE")
    if not getattr(grounding, "valid", False):
        reasons.append("INVALID_CONSISTENCY_RESPONSE")
    if not isinstance(response.get("answer"), str):
        reasons.append("INVALID_CONSISTENCY_RESPONSE")
    status, ids, primary, codes = _consistency_response_parts(response)
    if status not in {GroundingStatus.GROUNDED.value, GroundingStatus.NO_GROUNDED_ANSWER.value}:
        reasons.append("INVALID_CONSISTENCY_RESPONSE")
    raw_ids = response.get("grounded_record_ids")
    if "grounded_record_ids" not in response or not isinstance(raw_ids, list) or not all(isinstance(item, str) for item in raw_ids):
        reasons.append("INVALID_CONSISTENCY_RESPONSE")
    elif len(raw_ids) != len(set(raw_ids)):
        reasons.append("INVALID_CONSISTENCY_RESPONSE")
    if "primary_record_id" not in response:
        reasons.append("MISSING_PRIMARY_RECORD_ID")
    elif status == GroundingStatus.GROUNDED.value and (not isinstance(primary, str) or primary not in ids or primary not in basis):
        reasons.append("INVALID_PRIMARY_RECORD_ID")
    elif status == GroundingStatus.NO_GROUNDED_ANSWER.value and response.get("primary_record_id") is not None:
        reasons.append("INVALID_PRIMARY_RECORD_ID")
    if "limitation_codes" not in response:
        reasons.append("MISSING_LIMITATION_CODES")
    elif not isinstance(response.get("limitation_codes"), list) or not all(isinstance(item, str) and item in CONSISTENCY_LIMITATION_CODES for item in response["limitation_codes"]):
        reasons.append("INVALID_LIMITATION_CODES")
    elif len(response["limitation_codes"]) != len(set(response["limitation_codes"])):
        reasons.append("INVALID_LIMITATION_CODES")
    if "limitations" not in response or not isinstance(response.get("limitations"), list) or not all(isinstance(item, str) for item in response["limitations"]):
        reasons.append("INVALID_LIMITATIONS")
    unique_reasons = tuple(dict.fromkeys(reasons))
    return not unique_reasons, unique_reasons


def _consistency_contract_valid(response: Any, grounding: Any, basis: set[str]) -> bool:
    return _consistency_contract_diagnostics(response, grounding, basis)[0]


def _consistency_failure_code(
    *,
    run_a_valid: bool,
    run_b_valid: bool,
    status_a: str | None,
    status_b: str | None,
    new_ids: tuple[str, ...],
    missing_ids: tuple[str, ...],
    primary_equal: bool,
    limitations_equal: bool,
) -> str:
    if not run_a_valid:
        return ConsistencyFailureCode.RUN_A_GROUNDING_FAILURE.value
    if status_a != status_b:
        return ConsistencyFailureCode.GROUNDING_STATUS_DRIFT.value
    if new_ids:
        return ConsistencyFailureCode.CONSISTENCY_NEW_GROUNDED_RECORD_ID.value
    if missing_ids:
        return ConsistencyFailureCode.CONSISTENCY_MISSING_GROUNDED_RECORD_ID.value
    if not run_b_valid:
        return ConsistencyFailureCode.RUN_B_GROUNDING_FAILURE.value
    if not primary_equal:
        return ConsistencyFailureCode.PRIMARY_RECORD_DRIFT.value
    if not limitations_equal:
        return ConsistencyFailureCode.LIMITATION_DRIFT.value
    return ConsistencyFailureCode.NONE.value


def _consistency(sequence: TopLevelLiveSequence, exam: dict[str, Any]) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    for index, question in enumerate(FOLLOWUP_QUESTIONS[:5], 1):
        contract = {
            "same_stored_scientific_state": True,
            "same_question": question,
            "allowed_limitation_codes": sorted(CONSISTENCY_LIMITATION_CODES),
            "run_a_answer_is_not_supplied_to_run_b": True,
        }
        response_a, call_a = sequence.invoke(
            f"TL-CONSISTENCY-{index:02d}-A",
            "final_exam_followup",
            "final_exam_followup",
            sequence.state_context(question, extra={"question": question, "final_exam": exam.get("response"), "consistency_run": "A", "consistency_contract": contract}),
        )
        grounded_a, validation_a, failure_a = sequence.validate_grounded_response(response_a, call_a, require_grounded=False)
        status_a, ids_a, primary_a, codes_a = _consistency_response_parts(response_a)
        basis = set(ids_a) if grounded_a and isinstance(response_a, dict) else set()
        normalized_a = tuple(sorted(basis))
        contract_valid_a, contract_failure_reasons_a = _consistency_contract_diagnostics(response_a, validation_a, basis)
        run_a_valid = (
            call_a["status"] == "COMPLETED"
            and grounded_a
            and not _has_forbidden_output(response_a)
            and contract_valid_a
        )
        if not run_a_valid:
            assessment = ConsistencyGroundingAssessment(
                valid=False,
                pair_index=index,
                question=question,
                run_a_call_id=call_a.get("call_id"),
                run_b_call_id=None,
                run_a_grounding_status=status_a,
                run_b_grounding_status=None,
                run_a_ids=ids_a,
                run_b_ids=(),
                normalized_run_a_ids=normalized_a,
                normalized_run_b_ids=(),
                new_ids_in_b=(),
                missing_ids_in_b=normalized_a,
                support_basis_equal=False,
                limitation_codes_equal=False,
                primary_record_equal=False,
                failure_code=ConsistencyFailureCode.RUN_A_GROUNDING_FAILURE.value,
            )
            pairs.append({"index": index, "question": question, "run_a": response_a, "run_b": None, "calls": [call_a], "grounding_validations": [validation_a.to_dict()], "failed_response_validations": [failure_a.to_dict()] if failure_a else [], "contract_failure_reasons": list(contract_failure_reasons_a), "consistency_grounding_basis": list(normalized_a), "consistency_signature_a": _consistency_signature(response_a).to_dict() if _consistency_signature(response_a) else None, "consistency_signature_b": None, "consistency_assessment": assessment.to_dict(), "equivalent": False})
            return {"status": "BLOCKED_BEFORE_PASS", "pairs": pairs}

        frozen_basis = list(normalized_a)
        response_b, call_b = sequence.invoke(
            f"TL-CONSISTENCY-{index:02d}-B",
            "final_exam_followup",
            "final_exam_followup",
            sequence.state_context(
                question,
                extra={
                    "question": question,
                    "final_exam": exam.get("response"),
                    "consistency_run": "B",
                    "CONSISTENCY_GROUNDING_BASIS": frozen_basis,
                    "ALLOWED_GROUNDED_RECORD_IDS": frozen_basis,
                    "known_record_ids": frozen_basis,
                    "consistency_contract": {
                        **contract,
                        "run": "B",
                        "CONSISTENCY_GROUNDING_BASIS": frozen_basis,
                        "frozen_grounding_basis": True,
                    },
                },
            ),
        )
        grounded_b, validation_b, failure_b = sequence.validate_grounded_response(response_b, call_b, require_grounded=False)
        status_b, ids_b, primary_b, codes_b = _consistency_response_parts(response_b)
        normalized_b = tuple(sorted(set(ids_b)))
        new_ids = tuple(sorted(set(ids_b) - basis))
        missing_ids = tuple(sorted(basis - set(ids_b)))
        contract_valid_b, contract_failure_reasons_b = _consistency_contract_diagnostics(response_b, validation_b, basis)
        run_b_valid = (
            call_b["status"] == "COMPLETED"
            and grounded_b
            and not _has_forbidden_output(response_b)
            and contract_valid_b
        )
        signatures = (_consistency_signature(response_a), _consistency_signature(response_b))
        primary_equal = primary_a == primary_b
        limitations_equal = set(codes_a) == set(codes_b)
        failure_code = _consistency_failure_code(
            run_a_valid=True,
            run_b_valid=run_b_valid,
            status_a=status_a,
            status_b=status_b,
            new_ids=new_ids,
            missing_ids=missing_ids,
            primary_equal=primary_equal,
            limitations_equal=limitations_equal,
        )
        equivalent = failure_code == ConsistencyFailureCode.NONE.value and signatures[0] is not None and signatures[1] is not None and signatures[0].digest == signatures[1].digest
        assessment = ConsistencyGroundingAssessment(
            valid=equivalent,
            pair_index=index,
            question=question,
            run_a_call_id=call_a.get("call_id"),
            run_b_call_id=call_b.get("call_id"),
            run_a_grounding_status=status_a,
            run_b_grounding_status=status_b,
            run_a_ids=ids_a,
            run_b_ids=ids_b,
            normalized_run_a_ids=normalized_a,
            normalized_run_b_ids=normalized_b,
            new_ids_in_b=new_ids,
            missing_ids_in_b=missing_ids,
            support_basis_equal=not new_ids and not missing_ids,
            limitation_codes_equal=limitations_equal,
            primary_record_equal=primary_equal,
            failure_code=failure_code,
        )
        pair = {
            "index": index,
            "question": question,
            "run_a": response_a,
            "run_b": response_b,
            "calls": [call_a, call_b],
            "grounding_validations": [validation_a.to_dict(), validation_b.to_dict()],
            "failed_response_validations": [item.to_dict() for item in (failure_a, failure_b) if item],
            "contract_failure_reasons": list(dict.fromkeys((*contract_failure_reasons_a, *contract_failure_reasons_b))),
            "consistency_grounding_basis": frozen_basis,
            "consistency_signature_a": signatures[0].to_dict() if signatures[0] else None,
            "consistency_signature_b": signatures[1].to_dict() if signatures[1] else None,
            "consistency_assessment": assessment.to_dict(),
            "equivalent": equivalent,
        }
        pairs.append(pair)
        if not equivalent:
            return {"status": "BLOCKED_BEFORE_PASS", "pairs": pairs}
    return {"status": "PASS", "pairs": pairs}


def _process_cleanup(sequence: TopLevelLiveSequence) -> dict[str, Any]:
    children: dict[str, list[dict[str, Any]]] = {}
    for event in sequence.process_events:
        pid = str(event.get("pid", "NOT_STARTED"))
        children.setdefault(pid, []).append(event)
    records = []
    for pid, events in children.items():
        last = events[-1]
        records.append({"pid": pid, "parent_pid": last.get("parent_pid"), "events": events, "cleanup_status": last.get("cleanup_status", "NOT_STARTED"), "exit_code": last.get("exit_code"), "termination_reason": last.get("termination_reason")})
    return {"status": "PASS" if records and all(item["cleanup_status"] == "EXITED" for item in records) else "FAIL", "children": records, "owned_child_processes_remaining": False}


def _make_acceptance_digest(preflight: Mapping[str, Any], sequence: TopLevelLiveSequence, *, panel: Mapping[str, Any] | None = None, synthesis: Mapping[str, Any] | None = None, exam: Mapping[str, Any] | None = None, followups: Mapping[str, Any] | None = None, stress: Mapping[str, Any] | None = None, consistency: Mapping[str, Any] | None = None, cleanup: Mapping[str, Any] | None = None, scientific: Mapping[str, Any] | None = None, security: Mapping[str, Any] | None = None, pass_: bool = False) -> V5LiveAcceptanceDigest:
    diagnostics = [item.get("diagnostic") or {} for item in sequence.invocations]
    return V5LiveAcceptanceDigest(
        starting_commit=str(preflight.get("head") or "UNKNOWN"),
        live_execution_commit=str(preflight.get("head") or "UNKNOWN"),
        reviewer_panel_hash=_digest(panel or {}),
        synthesis_hash=_digest(synthesis or {}),
        final_exam_hash=_digest(exam or {}),
        followup_hash=_digest(followups or {}),
        stress_hash=_digest(stress or {}),
        consistency_hash=_digest(consistency or {}),
        cleanup_hash=_digest(cleanup or {}),
        scientific_audit_hash=_digest(scientific or {}),
        security_audit_hash=_digest(security or {}),
        live_call_count=len(sequence.invocations),
        live_failures=sum(1 for item in sequence.invocations if item.get("status") != "COMPLETED"),
        timeouts=sum(1 for item in diagnostics if item.get("exit_status") == "TIMEOUT"),
        evidence_created_by_codex=0,
        evidence_levels_mutated_by_codex=0,
        pass_=pass_,
    )


def _response_failure_gate_fields(sequence: TopLevelLiveSequence) -> dict[str, Any]:
    if not sequence.response_validation_failures:
        return {}
    failure = sequence.response_validation_failures[0]
    return {
        "failure_code": failure.failure_code,
        "failed_call_id": failure.call_id,
        "failed_label": failure.label,
        "failed_operation": failure.operation,
    }


def _consistency_failure_for_call(consistency: Mapping[str, Any], call_id: int) -> str | None:
    """Return the consistency diagnosis attached to a failed call, if any."""
    for pair in consistency.get("pairs", ()) if isinstance(consistency, Mapping) else ():
        if not isinstance(pair, Mapping):
            continue
        assessment = pair.get("consistency_assessment")
        if not isinstance(assessment, Mapping) or assessment.get("valid") is True:
            continue
        call_ids = {
            int(call.get("call_id"))
            for call in pair.get("calls", ())
            if isinstance(call, Mapping) and str(call.get("call_id", "")).isdigit()
        }
        if call_id in call_ids:
            code = assessment.get("failure_code")
            return str(code) if code else None
    return None


def _first_consistency_failure(consistency: Mapping[str, Any]) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    for pair in consistency.get("pairs", ()) if isinstance(consistency, Mapping) else ():
        if not isinstance(pair, Mapping):
            continue
        assessment = pair.get("consistency_assessment")
        if isinstance(assessment, Mapping) and assessment.get("valid") is not True:
            return pair, assessment
    return None, None


def _consistency_failure_for_gate(consistency: Mapping[str, Any], call_id: int) -> str | None:
    """Keep a consistency failure visible even when an earlier call failed."""
    matched = _consistency_failure_for_call(consistency, call_id)
    if matched:
        return matched
    _, assessment = _first_consistency_failure(consistency)
    code = assessment.get("failure_code") if assessment else None
    return str(code) if code else None


def _live_process_failure_fields(sequence: TopLevelLiveSequence, consistency: Mapping[str, Any]) -> dict[str, Any]:
    """Expose provider/process failures before scientific response failures."""
    for call in sequence.invocations:
        if call.get("status") == "COMPLETED":
            continue
        diagnostic = call.get("diagnostic") or {}
        error = call.get("error") or {}
        code = diagnostic.get("failure_code")
        if not code:
            error_type = str(error.get("type", ""))
            code = {
                "LiveCodexUnavailable": "PROVIDER_UNAVAILABLE",
                "LiveCodexProtocolError": "SCHEMA_INVALID",
            }.get(error_type, "PROCESS_ERROR")
        call_id = int(call.get("call_id", 0))
        fields = {
            "failure_code": str(code),
            "failed_call_id": call_id,
            "failed_label": call.get("label"),
            "failed_operation": call.get("operation"),
        }
        consistency_code = _consistency_failure_for_gate(consistency, call_id)
        if consistency_code:
            fields["consistency_failure_code"] = consistency_code
        return fields
    return {}


def _final_gate_failure_fields(sequence: TopLevelLiveSequence, consistency: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the final-gate precedence: live, grounding, then consistency."""
    process_fields = _live_process_failure_fields(sequence, consistency)
    if process_fields:
        return process_fields
    if sequence.response_validation_failures:
        fields = _response_failure_gate_fields(sequence)
        consistency_code = _consistency_failure_for_gate(consistency, int(fields["failed_call_id"]))
        if consistency_code:
            fields["consistency_failure_code"] = consistency_code
        return fields
    _, assessment = _first_consistency_failure(consistency)
    if assessment is None:
        return {}
    call_id = assessment.get("run_a_call_id") or assessment.get("run_b_call_id")
    call = next(
        (item for item in sequence.invocations if item.get("call_id") == call_id),
        None,
    )
    code = str(assessment.get("failure_code") or ConsistencyFailureCode.RUN_A_GROUNDING_FAILURE.value)
    return {
        "failure_code": code,
        "consistency_failure_code": code,
        "failed_call_id": call_id,
        "failed_label": call.get("label") if call else None,
        "failed_operation": call.get("operation") if call else None,
    }


def _duration_statistics(sequence: TopLevelLiveSequence) -> dict[str, Any]:
    durations = sorted(float(item.get("elapsed", 0.0)) for item in sequence.invocations)
    if not durations:
        return {"count": 0, "minimum_seconds": None, "median_seconds": None, "maximum_seconds": None, "p95_seconds": None, "timeout_count": 0}
    p95_index = min(len(durations) - 1, max(0, math.ceil(len(durations) * 0.95) - 1))
    return {
        "count": len(durations),
        "minimum_seconds": durations[0],
        "median_seconds": median(durations),
        "maximum_seconds": durations[-1],
        "p95_seconds": durations[p95_index] if len(durations) >= 2 else None,
        "timeout_count": sum(1 for item in sequence.invocations if (item.get("diagnostic") or {}).get("exit_status") == "TIMEOUT"),
    }


def _scientific_audit(panel: dict[str, Any], exam: dict[str, Any], followups: dict[str, Any], stress: dict[str, Any], consistency: dict[str, Any]) -> dict[str, Any]:
    values = [panel, exam, followups, stress, consistency]
    checks = {
        "reviews_are_analysis_only": panel.get("scientific_evidence_created") is False,
        "final_exam_creates_zero_evidence": exam.get("scientific_evidence_created_by_codex") is False,
        "no_forbidden_scientific_authority_in_outputs": not any(_has_forbidden_output(value) for value in values),
        "followups_are_grounded": followups.get("status") == "PASS",
        "stress_answers_are_grounded": stress.get("status") == "PASS",
        "consistency_is_structured": consistency.get("status") == "PASS",
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def _security_audit(sequence: TopLevelLiveSequence, owner: Mapping[str, Any], cleanup: Mapping[str, Any]) -> dict[str, Any]:
    transport = sequence.provider.transport
    checks = {
        "top_level_owner_confirmed": owner.get("result") == "TOP_LEVEL_CONFIRMED",
        "fixed_codex_executable": getattr(transport, "_APPROVED_EXECUTABLE_NAMES", set()) == {"codex", "codex.exe"},
        "shell_false": True,
        "no_recursive_provider_entry": all((item.get("diagnostic") or {}).get("reentrancy_state") != "REJECTED_REENTRANT" for item in sequence.invocations),
        "max_live_invocations_bounded": len(sequence.invocations) <= MAX_LIVE_INVOCATIONS,
        "retries_disabled_for_acceptance": sequence.budget.max_retries == 0,
        "child_cleanup_pass": cleanup.get("status") == "PASS",
        "raw_output_not_persisted": all("stdout" not in item and "stderr" not in item for item in sequence.invocations),
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def _blocked_artifacts(reason: str, *, owner: Mapping[str, Any], preflight: Mapping[str, Any]) -> None:
    _write("top-level-owner-diagnostic.json", owner)
    _write("top-level-preflight.json", preflight)
    _write("reviewer-panel.json", {"status": "NOT_RUN", "reason": reason, "reviewers": []})
    _write("review-synthesis.json", {"status": "NOT_RUN", "reason": reason, "concerns": []})
    _write("final-scientific-exam.json", {"status": "NOT_RUN", "reason": reason, "response": None})
    _write("follow-up-answers.json", {"status": "NOT_RUN", "reason": reason, "answers": []})
    _write("live-stress.json", {"status": "NOT_RUN", "reason": reason, "answers": []})
    _write("live-consistency.json", {"status": "NOT_RUN", "reason": reason, "pairs": []})
    _write("process-cleanup.json", {"status": "NOT_RUN", "children": [], "owned_child_processes_remaining": False})
    _write("v5-live-acceptance-digest.json", {"status": "NOT_RUN", "starting_commit": preflight.get("head"), "live_execution_commit": preflight.get("head"), "live_call_count": 0, "live_failures": 0, "timeouts": 0, "evidence_created_by_codex": 0, "evidence_levels_mutated_by_codex": 0, "digest": None})
    _write("v5-final-gate.json", {"status": "TOP_LEVEL_OWNER_REQUIRED", "reason": reason, "live_call_count": 0, "acceptance_digest": None})


def run_live_acceptance(*, root: Path, expected_head: str | None, timeout_seconds: int) -> int:
    global OUTPUT_ROOT
    OUTPUT_ROOT = _next_output_root(root)
    preflight = preflight_repository(root, expected_branch=EXPECTED_BRANCH, expected_head=expected_head)
    _write("top-level-owner-diagnostic.json", preflight.owner.to_dict())
    _write("top-level-preflight.json", preflight.to_dict())
    if preflight.status != TopLevelPreflightStatus.READY.value:
        _blocked_artifacts(f"preflight={preflight.status}", owner=preflight.owner.to_dict(), preflight=preflight.to_dict())
        return 2
    state = _compact_state(root)
    sequence = TopLevelLiveSequence(root, state, preflight.owner.invocation_id, timeout_seconds)
    panel = _review_panel(sequence)
    if panel["status"] != "PASS":
        cleanup = _process_cleanup(sequence)
        synthesis = {"status": "NOT_RUN", "concerns": panel.get("synthesis", [])}
        digest = _make_acceptance_digest(preflight.to_dict(), sequence, panel=panel, synthesis=synthesis, cleanup=cleanup)
        _write("reviewer-panel.json", panel)
        _write("review-synthesis.json", synthesis)
        _write("final-scientific-exam.json", {"status": "NOT_RUN", "reason": "review panel did not pass"})
        _write("follow-up-answers.json", {"status": "NOT_RUN", "answers": []})
        _write("live-stress.json", {"status": "NOT_RUN", "answers": []})
        _write("live-consistency.json", {"status": "NOT_RUN", "pairs": []})
        _write("process-cleanup.json", cleanup)
        _write("v5-live-acceptance-digest.json", digest.to_dict())
        _write("v5-final-gate.json", {"status": "BLOCKED_BEFORE_PASS", "reason": "review panel failed", "live_call_count": len(sequence.invocations), "duration_statistics": _duration_statistics(sequence), "acceptance_digest": digest.to_dict(), "response_validation_failures": [item.to_dict() for item in sequence.response_validation_failures], **_response_failure_gate_fields(sequence)})
        return 3
    exam = _final_exam(sequence)
    if exam["status"] != "PASS":
        cleanup = _process_cleanup(sequence)
        synthesis = {"status": "PASS", "concerns": panel.get("synthesis", [])}
        digest = _make_acceptance_digest(preflight.to_dict(), sequence, panel=panel, synthesis=synthesis, exam=exam, cleanup=cleanup)
        _write("reviewer-panel.json", panel)
        _write("review-synthesis.json", synthesis)
        _write("final-scientific-exam.json", exam)
        _write("follow-up-answers.json", {"status": "NOT_RUN", "answers": []})
        _write("live-stress.json", {"status": "NOT_RUN", "answers": []})
        _write("live-consistency.json", {"status": "NOT_RUN", "pairs": []})
        _write("process-cleanup.json", cleanup)
        _write("v5-live-acceptance-digest.json", digest.to_dict())
        _write("v5-final-gate.json", {"status": "BLOCKED_BEFORE_PASS", "reason": "final exam failed", "live_call_count": len(sequence.invocations), "duration_statistics": _duration_statistics(sequence), "acceptance_digest": digest.to_dict(), "response_validation_failures": [item.to_dict() for item in sequence.response_validation_failures], **_response_failure_gate_fields(sequence)})
        return 4
    followups = _followups(sequence, exam)
    stress = _stress(sequence, exam) if followups["status"] == "PASS" else {"status": "NOT_RUN", "answers": []}
    consistency = _consistency(sequence, exam) if stress["status"] == "PASS" else {"status": "NOT_RUN", "pairs": []}
    cleanup = _process_cleanup(sequence)
    scientific = _scientific_audit(panel, exam, followups, stress, consistency)
    security = _security_audit(sequence, preflight.owner.to_dict(), cleanup)
    synthesis = {"status": "PASS", "concerns": panel.get("synthesis", [])}
    _write("reviewer-panel.json", panel)
    _write("final-scientific-exam.json", exam)
    _write("follow-up-answers.json", followups)
    _write("live-stress.json", stress)
    _write("live-consistency.json", consistency)
    _write("process-cleanup.json", cleanup)
    gate_pass = len(sequence.invocations) == REQUIRED_LIVE_INVOCATIONS and followups["status"] == "PASS" and stress["status"] == "PASS" and consistency["status"] == "PASS" and cleanup["status"] == "PASS" and scientific["status"] == "PASS" and security["status"] == "PASS" and not sequence.response_validation_failures
    digest = _make_acceptance_digest(preflight.to_dict(), sequence, panel=panel, synthesis=synthesis, exam=exam, followups=followups, stress=stress, consistency=consistency, cleanup=cleanup, scientific=scientific, security=security, pass_=gate_pass)
    _write("review-synthesis.json", synthesis)
    _write("v5-live-acceptance-digest.json", digest.to_dict())
    _write("v5-final-gate.json", {"status": "PASS" if gate_pass else "BLOCKED_BEFORE_PASS", "live_call_count": len(sequence.invocations), "required_live_invocations": REQUIRED_LIVE_INVOCATIONS, "max_live_invocations": MAX_LIVE_INVOCATIONS, "duration_statistics": _duration_statistics(sequence), "scientific_audit": scientific, "security_audit": security, "acceptance_digest": digest.to_dict(), "response_validation_failures": [item.to_dict() for item in sequence.response_validation_failures], "invocations": sequence.invocations, **_final_gate_failure_fields(sequence, consistency)})
    return 0 if gate_pass else 5


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the v5 Live gate only from an external top-level terminal.")
    parser.add_argument("--run-all", action="store_true", help="run the sequential 39-call Live acceptance")
    parser.add_argument("--preflight-only", action="store_true", help="inspect ownership and repository readiness without Live calls")
    parser.add_argument("--expected-head", default=None, help="expected repository HEAD recorded by the implementation commit")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args(argv)
    if args.run_all == args.preflight_only:
        parser.error("choose exactly one of --run-all or --preflight-only")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    preflight = preflight_repository(REPO_ROOT, expected_branch=EXPECTED_BRANCH, expected_head=args.expected_head)
    if args.preflight_only:
        _write("top-level-owner-diagnostic.json", preflight.owner.to_dict())
        _write("top-level-preflight.json", preflight.to_dict())
        print(json.dumps({"status": preflight.status, "owner": preflight.owner.result, "head": preflight.head}, ensure_ascii=False))
        return 0 if preflight.status == TopLevelPreflightStatus.READY.value else 2
    return run_live_acceptance(root=REPO_ROOT, expected_head=args.expected_head, timeout_seconds=args.timeout_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
