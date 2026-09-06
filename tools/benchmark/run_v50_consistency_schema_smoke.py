"""Run one bounded Live consistency-schema compatibility smoke.

This script is intended for a genuinely external top-level PowerShell owner.
It never changes scientific state, never retries, and persists only structured
response/diagnostic fields under a fresh smoke namespace.
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
sys.path.insert(0, str(REPO_ROOT / "tools" / "benchmark"))

from research_os.oracle import (  # noqa: E402
    CodexCliTransport,
    CodexLiveProvider,
    CONSISTENCY_LIMITATION_CODES,
    GroundingStatus,
    LiveExecutionBudget,
    LiveFailureCode,
    TopLevelPreflightStatus,
    find_forbidden_scientific_fields,
    preflight_repository,
    validate_grounding,
)
import run_v50_live_top_level as top_level  # noqa: E402


EXPECTED_BRANCH = "research-os-v1.3"
MAX_LIVE_INVOCATIONS = 1
SMOKE_ROOT = REPO_ROOT / ".research-os-live-5.0-consistency-schema-smoke"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _next_output_root() -> Path:
    if not SMOKE_ROOT.exists() or not any(SMOKE_ROOT.iterdir()):
        return SMOKE_ROOT
    for attempt in range(2, 1000):
        candidate = REPO_ROOT / f".research-os-live-5.0-consistency-schema-smoke-attempt-{attempt}"
        if not candidate.exists() or not any(candidate.iterdir()):
            return candidate
    raise RuntimeError("no unused consistency smoke namespace available")


def _write(root: Path, name: str, value: Mapping[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _cleanup(events: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate = top_level._aggregate_process_cleanup(events)
    return {
        "status": aggregate["status"],
        "owned_child_processes_remaining": aggregate["owned_child_processes_remaining"],
        "events_observed": len(events),
        "owned_processes_observed": aggregate["owned_processes_observed"],
    }


def _blocked(root: Path, preflight: Any) -> int:
    owner = preflight.owner.to_dict()
    _write(root, "top-level-owner-diagnostic.json", owner)
    _write(root, "top-level-preflight.json", preflight.to_dict())
    _write(root, "live-consistency.json", {"status": "NOT_RUN", "reason": f"preflight={preflight.status}"})
    _write(root, "process-cleanup.json", {"status": "NOT_RUN", "owned_child_processes_remaining": False, "events_observed": 0})
    _write(root, "v5-live-acceptance-digest.json", {"status": "NOT_RUN", "preflight_status": preflight.status, "live_call_count": 0, "digest": None})
    _write(root, "v5-final-gate.json", {"status": "BLOCKED_BEFORE_PASS", "reason": f"preflight={preflight.status}", "live_call_count": 0, "required_live_invocations": 1})
    print(json.dumps({"status": preflight.status, "owner": preflight.owner.result, "root": str(root)}, ensure_ascii=False))
    return 2


def run_smoke(*, expected_head: str | None, timeout_seconds: int) -> int:
    root = _next_output_root()
    preflight = preflight_repository(REPO_ROOT, expected_branch=EXPECTED_BRANCH, expected_head=expected_head)
    if preflight.status != TopLevelPreflightStatus.READY.value:
        return _blocked(root, preflight)
    _write(root, "top-level-owner-diagnostic.json", preflight.owner.to_dict())
    _write(root, "top-level-preflight.json", preflight.to_dict())

    state = top_level._compact_state(REPO_ROOT)
    all_ids: set[str] = set()
    top_level._record_ids(state, all_ids)
    preferred_id = "RUN-V50-COMB-H2-PHI105"
    basis = [preferred_id] if preferred_id in all_ids else sorted(all_ids)[:1]
    question = "What evidence level is recorded for the registered run RUN-V50-COMB-H2-PHI105?"
    contract = {
        "same_stored_scientific_state": True,
        "same_question": question,
        "CONSISTENCY_GROUNDING_BASIS": basis,
        "allowed_limitation_codes": sorted(CONSISTENCY_LIMITATION_CODES),
    }
    context = {
        "instruction": question,
        "question": question,
        "registered_state": state,
        "known_record_ids": basis,
        "ALLOWED_GROUNDED_RECORD_IDS": basis,
        "consistency_run": "A",
        "consistency_contract": contract,
    }
    events: list[dict[str, Any]] = []
    budget = LiveExecutionBudget(
        total_timeout=timeout_seconds,
        planning_budget=timeout_seconds,
        execution_budget=timeout_seconds,
        review_budget=timeout_seconds,
        output_validation_budget=5,
        max_live_turns=MAX_LIVE_INVOCATIONS,
        max_retries=0,
    )
    transport = CodexCliTransport(
        workdir=REPO_ROOT,
        timeout_seconds=timeout_seconds,
        budget=budget,
        process_observer=events.append,
    )
    provider = CodexLiveProvider(transport=transport)
    provider.set_request_context({
        "top_level_owner_id": preflight.owner.invocation_id,
        "stored_state_digest": state["state_digest"],
    })
    started = time.monotonic()
    response: Any = None
    error: dict[str, Any] | None = None
    try:
        response = provider.final_exam_followup(context)
    except Exception as exc:  # pragma: no cover - exercised by external smoke
        error = {"type": type(exc).__name__, "message": str(exc)[:512]}
    elapsed = max(0.0, time.monotonic() - started)
    diagnostic = getattr(transport, "last_invocation_diagnostic", None)
    grounding = validate_grounding(response, set(basis))
    contract_valid, contract_reasons = top_level._consistency_contract_diagnostics(response, grounding, set(basis))
    forbidden = find_forbidden_scientific_fields(response)
    cleanup = _cleanup(events)
    diagnostic_dict = diagnostic.to_dict() if diagnostic is not None else None
    process_pass = bool(diagnostic_dict and diagnostic_dict.get("exit_status") == "COMPLETED")
    schema_pass = bool(diagnostic_dict and diagnostic_dict.get("schema_status") == "PASS")
    response_safe = response if isinstance(response, dict) else None
    live_consistency = {
        "status": "PASS" if process_pass and schema_pass and grounding.valid and contract_valid and not forbidden else "FAIL",
        "question": question,
        "response": response_safe,
        "grounding_validation": grounding.to_dict(),
        "consistency_validation": {"valid": contract_valid, "failure_reasons": list(contract_reasons)},
        "forbidden_field_validation": {"status": "FAIL" if forbidden else "PASS", "fields": list(forbidden)},
        "diagnostic": diagnostic_dict,
        "error": error,
        "elapsed_seconds": elapsed,
    }
    _write(root, "live-consistency.json", live_consistency)
    _write(root, "process-cleanup.json", cleanup)
    primary_failure = None
    if diagnostic_dict and diagnostic_dict.get("failure_code"):
        primary_failure = diagnostic_dict["failure_code"]
    elif not grounding.valid:
        primary_failure = grounding.failure_code
    elif not contract_valid:
        primary_failure = "CONSISTENCY_CONTRACT_INVALID"
    gate_status = "PASS" if live_consistency["status"] == "PASS" and cleanup["status"] == "PASS" else "BLOCKED_BEFORE_PASS"
    gate = {
        "status": gate_status,
        "live_call_count": 1,
        "required_live_invocations": 1,
        "max_live_invocations": 1,
        "output_contract": diagnostic_dict.get("output_contract") if diagnostic_dict else transport.last_output_contract,
        "output_schema_name": diagnostic_dict.get("output_schema_name") if diagnostic_dict else transport.last_output_schema_name,
        "failure_code": primary_failure,
        "failure_stage": diagnostic_dict.get("failure_stage") if diagnostic_dict else None,
        "schema_status": diagnostic_dict.get("schema_status") if diagnostic_dict else "NOT_CHECKED",
        "cleanup": cleanup,
        "evidence_created_by_codex": 0,
        "evidence_levels_mutated_by_codex": 0,
    }
    digest = {"status": gate_status, "gate_digest": _digest(gate), "live_consistency_digest": _digest(live_consistency)}
    _write(root, "v5-final-gate.json", gate)
    _write(root, "v5-live-acceptance-digest.json", digest)
    print(json.dumps({"status": gate_status, "root": str(root), "live_call_count": 1, "output_contract": gate["output_contract"], "output_schema_name": gate["output_schema_name"], "failure_code": primary_failure}, ensure_ascii=False))
    return 0 if gate_status == "PASS" else 5


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run exactly one bounded Live consistency-schema smoke.")
    parser.add_argument("--expected-head", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    return run_smoke(expected_head=args.expected_head, timeout_seconds=args.timeout_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
