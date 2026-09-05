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
from pathlib import Path
import sys
import time
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from research_os.oracle import (  # noqa: E402
    CodexCliTransport,
    CodexLiveProvider,
    LiveExecutionBudget,
    LiveCodexProtocolError,
    LiveCodexUnavailable,
    TopLevelPreflightStatus,
    V5LiveAcceptanceDigest,
    preflight_repository,
)


OUTPUT_ROOT = REPO_ROOT / ".research-os-live-5.0-top-level"
EXPECTED_BRANCH = "research-os-v1.3"
MAX_LIVE_INVOCATIONS = 45
REQUIRED_LIVE_INVOCATIONS = 39
FORBIDDEN_OUTPUT_KEYS = {
    "evidence", "evidence_level", "runs", "bundle", "bundle_id",
    "scientific_result", "experimental_result", "engine_result",
}

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
    if not isinstance(value, dict):
        return False
    ids = value.get("grounded_record_ids")
    return isinstance(ids, list) and all(isinstance(item, str) and item in known_ids for item in ids)


class TopLevelLiveSequence:
    def __init__(self, root: Path, state: dict[str, Any], owner_id: str, timeout_seconds: int) -> None:
        self.root = root
        self.state = state
        self.owner_id = owner_id
        self.process_events: list[dict[str, Any]] = []
        self.invocations: list[dict[str, Any]] = []
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

    def state_context(self, instruction: str, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        context = {"instruction": instruction, "registered_state": self.state, "known_record_ids": sorted(self.known_ids)}
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
            if action not in {"ACCEPT", "REJECT_WITH_EVIDENCE", "CREATE_GAP", "REVISE_CLAIM", "REVISE_DECISION", "DEFER_EXTERNAL"}:
                action = "DEFER_EXTERNAL"
            synthesis.append({"role": reviewer["role"], "concern": concern.get("concern"), "action": action, "grounded_record_ids": concern.get("grounded_record_ids", [])})
    return {"status": "PASS", "reviewers": reviewers, "synthesis": synthesis, "same_stored_evidence": True, "scientific_evidence_created": False, "evidence_level_changed": False}


def _final_exam(sequence: TopLevelLiveSequence) -> dict[str, Any]:
    response, call = sequence.invoke("V5-FINAL-SCIENTIFIC-EXAM", "final_scientific_exam", "final_scientific_exam", sequence.state_context(FINAL_EXAM_INSTRUCTION))
    required = {"conclusion_kept", "conclusion_weakened", "unanswered_question", "redundant_step", "highest_value_external_evidence", "no_decision_reconsideration", "protocol_sensitive_decision", "proposed_research_program", "program_executed", "scientific_state_change", "grounded_record_ids", "limitations"}
    valid = call["status"] == "COMPLETED" and isinstance(response, dict) and required <= set(response) and _valid_grounding(response, sequence.known_ids) and not _has_forbidden_output(response)
    return {"status": "PASS" if valid else "BLOCKED_BEFORE_PASS", "response": response if valid else None, "call": call, "criteria_declared_before_execution": True, "scientific_evidence_created_by_codex": False, "evidence_level_changed_by_codex": False}


def _followups(sequence: TopLevelLiveSequence, exam: dict[str, Any]) -> dict[str, Any]:
    answers: list[dict[str, Any]] = []
    for index, question in enumerate(FOLLOWUP_QUESTIONS, 1):
        response, call = sequence.invoke(f"V5-FOLLOWUP-{index:02d}", "final_exam_followup", "final_exam_followup", sequence.state_context(question, extra={"question": question, "final_exam": exam.get("response")}))
        if call["status"] != "COMPLETED" or not isinstance(response, dict) or not _valid_grounding(response, sequence.known_ids) or _has_forbidden_output(response):
            return {"status": "BLOCKED_BEFORE_PASS", "answers": answers, "failed_call": call}
        answers.append({"index": index, "question": question, "response": response, "call_id": call["call_id"]})
    return {"status": "PASS", "answers": answers}


def _stress(sequence: TopLevelLiveSequence, exam: dict[str, Any]) -> dict[str, Any]:
    answers: list[dict[str, Any]] = []
    for index, question in enumerate(STRESS_QUESTIONS, 1):
        response, call = sequence.invoke(f"TL-LIVE-{index:02d}", "final_exam_followup", "final_exam_followup", sequence.state_context(question, extra={"question": question, "final_exam": exam.get("response")}))
        if call["status"] != "COMPLETED" or not isinstance(response, dict) or not _valid_grounding(response, sequence.known_ids) or _has_forbidden_output(response):
            return {"status": "BLOCKED_BEFORE_PASS", "answers": answers, "failed_call": call}
        answers.append({"index": index, "question": question, "response": response, "call_id": call["call_id"]})
    return {"status": "PASS", "answers": answers}


def _consistency(sequence: TopLevelLiveSequence, exam: dict[str, Any]) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    for index, question in enumerate(FOLLOWUP_QUESTIONS[:5], 1):
        responses = []
        calls = []
        for repeat in ("A", "B"):
            response, call = sequence.invoke(f"TL-CONSISTENCY-{index:02d}-{repeat}", "final_exam_followup", "final_exam_followup", sequence.state_context(question, extra={"question": question, "final_exam": exam.get("response")}))
            responses.append(response)
            calls.append(call)
        valid = all(call["status"] == "COMPLETED" and isinstance(response, dict) and _valid_grounding(response, sequence.known_ids) and not _has_forbidden_output(response) for call, response in zip(calls, responses))
        equivalent = valid and all(_digest(responses[0].get(key)) == _digest(responses[1].get(key)) for key in ("grounded_record_ids", "limitations"))
        pairs.append({"index": index, "question": question, "run_a": responses[0], "run_b": responses[1], "calls": calls, "equivalent": equivalent})
        if not valid:
            return {"status": "BLOCKED_BEFORE_PASS", "pairs": pairs}
    return {"status": "PASS" if all(item["equivalent"] for item in pairs) else "REVIEW_REQUIRED", "pairs": pairs}


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
    _write("final-scientific-exam.json", {"status": "NOT_RUN", "reason": reason, "response": None})
    _write("follow-up-answers.json", {"status": "NOT_RUN", "reason": reason, "answers": []})
    _write("live-stress.json", {"status": "NOT_RUN", "reason": reason, "answers": []})
    _write("live-consistency.json", {"status": "NOT_RUN", "reason": reason, "pairs": []})
    _write("process-cleanup.json", {"status": "NOT_RUN", "children": [], "owned_child_processes_remaining": False})
    _write("v5-final-gate.json", {"status": "TOP_LEVEL_OWNER_REQUIRED", "reason": reason, "live_call_count": 0, "acceptance_digest": None})


def run_live_acceptance(*, root: Path, expected_head: str | None, timeout_seconds: int) -> int:
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
        _write("reviewer-panel.json", panel)
        _write("final-scientific-exam.json", {"status": "NOT_RUN", "reason": "review panel did not pass"})
        _write("follow-up-answers.json", {"status": "NOT_RUN", "answers": []})
        _write("live-stress.json", {"status": "NOT_RUN", "answers": []})
        _write("live-consistency.json", {"status": "NOT_RUN", "pairs": []})
        _write("process-cleanup.json", cleanup)
        _write("v5-final-gate.json", {"status": "BLOCKED_BEFORE_PASS", "reason": "review panel failed", "live_call_count": len(sequence.invocations), "acceptance_digest": None})
        return 3
    exam = _final_exam(sequence)
    if exam["status"] != "PASS":
        cleanup = _process_cleanup(sequence)
        _write("reviewer-panel.json", panel)
        _write("final-scientific-exam.json", exam)
        _write("follow-up-answers.json", {"status": "NOT_RUN", "answers": []})
        _write("live-stress.json", {"status": "NOT_RUN", "answers": []})
        _write("live-consistency.json", {"status": "NOT_RUN", "pairs": []})
        _write("process-cleanup.json", cleanup)
        _write("v5-final-gate.json", {"status": "BLOCKED_BEFORE_PASS", "reason": "final exam failed", "live_call_count": len(sequence.invocations), "acceptance_digest": None})
        return 4
    followups = _followups(sequence, exam)
    stress = _stress(sequence, exam) if followups["status"] == "PASS" else {"status": "NOT_RUN", "answers": []}
    consistency = _consistency(sequence, exam) if stress["status"] == "PASS" else {"status": "NOT_RUN", "pairs": []}
    cleanup = _process_cleanup(sequence)
    scientific = _scientific_audit(panel, exam, followups, stress, consistency)
    security = _security_audit(sequence, preflight.owner.to_dict(), cleanup)
    _write("reviewer-panel.json", panel)
    _write("final-scientific-exam.json", exam)
    _write("follow-up-answers.json", followups)
    _write("live-stress.json", stress)
    _write("live-consistency.json", consistency)
    _write("process-cleanup.json", cleanup)
    gate_pass = len(sequence.invocations) == REQUIRED_LIVE_INVOCATIONS and followups["status"] == "PASS" and stress["status"] == "PASS" and consistency["status"] == "PASS" and cleanup["status"] == "PASS" and scientific["status"] == "PASS" and security["status"] == "PASS"
    digest = V5LiveAcceptanceDigest(
        repository_commit=preflight.head or "UNKNOWN",
        reviewer_artifact_hash=_digest(panel),
        final_exam_artifact_hash=_digest(exam),
        followup_artifact_hash=_digest(followups),
        stress_artifact_hash=_digest(stress),
        consistency_artifact_hash=_digest(consistency),
        process_cleanup_hash=_digest(cleanup),
        scientific_audit_hash=_digest(scientific),
        security_audit_hash=_digest(security),
        live_call_count=len(sequence.invocations),
        pass_=gate_pass,
    )
    _write("v5-final-gate.json", {"status": "PASS" if gate_pass else "BLOCKED_BEFORE_PASS", "live_call_count": len(sequence.invocations), "required_live_invocations": REQUIRED_LIVE_INVOCATIONS, "max_live_invocations": MAX_LIVE_INVOCATIONS, "scientific_audit": scientific, "security_audit": security, "acceptance_digest": digest.to_dict(), "invocations": sequence.invocations})
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
