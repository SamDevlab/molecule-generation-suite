# Top-level Live acceptance — Research OS v5.0

Status: **READY_FOR_TOP_LEVEL_LIVE_EXECUTION**. The release gate remains **BLOCKED_BEFORE_PASS** until an external, genuinely top-level Codex owner completes the bounded Live stages and the resulting artifacts pass the final regression and audit gates.

## Why this boundary exists

The current Codex desktop task is itself a Codex-owned process tree. Direct inspection observed:

`python.exe → python.exe → pwsh.exe → codex.exe → ChatGPT.exe → explorer.exe`

and the environment exposes `CODEX_THREAD_ID`, `CODEX_SESSION_ID`, and `CODEX_INTERNAL_ORIGINATOR_OVERRIDE`. The top-level owner diagnostic therefore returns `TOP_LEVEL_OWNER_REQUIRED`. This is an execution-context fact, not scientific evidence, and no Live launcher was started from this task.

The launcher fails closed when it detects Codex markers, a Codex ancestor, an unresolved process parent, or an inspection failure. It never converts a nested timeout into a scientific result and never substitutes a test provider for Live.

## Top-level attempt 1 — preserved

The first genuine external acceptance is preserved at `.research-os-live-5.0-top-level/` and is treated as the immutable historical Attempt 1. Its owner diagnostic and Codex CLI preflight passed; all three reviewers completed; the final exam completed; follow-ups 1–12 were accepted; and the run reached 17/39 Live calls. `V5-FOLLOWUP-13` also completed as a real `CODEX_LIVE` process with schema `PASS`, exit code `0`, reentrancy `COMPLETED`, and child cleanup `EXITED`.

The post-response grounding gate then rejected that schema-valid answer. The prior launcher persisted only a boolean outcome, so it did not identify whether the rejection came from a missing field, an empty list, or an unknown ID. Attempt 1 therefore remains `BLOCKED_BEFORE_PASS` as an operational validation result, not a scientific failure. Its files are never overwritten by the next acceptance.

## Top-level Attempt 2 — preserved

The second genuine external acceptance is preserved at `.research-os-live-5.0-top-level-attempt-2/` with 33/39 calls: 3 reviewers, 1 final exam, 15/15 follow-ups, 10/10 stress answers, and the first two consistency calls (pair 1 A/B and pair 2 A). The process and schema gates passed for call 33, `TL-CONSISTENCY-02-B`, but grounding correctly failed closed with `UNKNOWN_GROUNDED_RECORD_ID`.

The response declared `GROUNDED` and returned 67 candidate known IDs plus `CH-V45-SOLUBILITY-EXTERNAL-BOUNDARY`. Deterministic searches of `.research-os-live-5.0` and `.research-os-live-4.5` found no official artifact containing that literal ID. It is therefore classified as `MODEL_REFERENCE_HALLUCINATION`, not as a missing registered record. The ID is not allowlisted, aliased, fuzzy-matched, autocorrected, or converted into another record. Attempt 2 remains an immutable operational finding and no scientific state was changed by it.

## Official external command

Run from a separately owned terminal or Codex CLI process, after checking out `research-os-v1.3` at the expected commit:

```powershell
.\.venv\Scripts\python.exe tools\benchmark\run_v50_live_top_level.py --run-all --expected-head (git rev-parse HEAD)
```

The command performs preflight checks for branch, expected HEAD, clean worktree, package identity, Ledger, required artifacts, fixed provider/schema contracts, and Codex CLI availability. It then runs only the blocked Live stages sequentially. The next run selects a fresh namespace such as `.research-os-live-5.0-top-level-attempt-3/`; prior attempts are never overwritten and reruns select the next unused attempt number.

| Stage | Calls |
|---|---:|
| Methodology, evidence, reproducibility reviewers | 3 |
| Final scientific exam | 1 |
| Grounded follow-ups | 15 |
| Adversarial stress questions | 10 |
| Consistency pairs | 10 |
| **Required total** | **39** |

The hard ceiling is 45 Live invocations. Retries are disabled for this acceptance run. Stable deterministic science is not rerun.

## Output and promotion rules

New machine-readable results are written only under a fresh `.research-os-live-5.0-top-level-attempt-N/` namespace. The Attempt 1 artifacts under `.research-os-live-5.0-top-level/`, the recovery artifacts under `.research-os-live-5.0-recovery/`, and the earlier `.research-os-live-5.0/` attempt are preserved. The launcher records process identity, cleanup, bounded diagnostics, response hashes, structured grounding failures, and stage outcomes without persisting raw model output or hidden reasoning.

Each attempt recognizes only these generated files: `top-level-owner-diagnostic.json`, `top-level-preflight.json`, `reviewer-panel.json`, `review-synthesis.json`, `final-scientific-exam.json`, `follow-up-answers.json`, `live-stress.json`, `live-consistency.json`, `process-cleanup.json`, `v5-live-acceptance-digest.json`, and `v5-final-gate.json`. Any other changed or untracked path, including an unknown file inside an acceptance namespace, keeps preflight at `DIRTY_WORKTREE`.

## Grounding recovery contract

Follow-up, stress, consistency, and final-exam responses must declare `grounding_status`. `GROUNDED` requires at least one literal member of `ALLOWED_GROUNDED_RECORD_IDS`; `NO_GROUNDED_ANSWER` requires an empty ID list and an explicit limitation. The deterministic validator reports `NONE`, `INVALID_RESPONSE_TYPE`, `MISSING_GROUNDED_RECORD_IDS`, `INVALID_GROUNDED_RECORD_IDS_TYPE`, `EMPTY_GROUNDING_FOR_GROUNDED_ANSWER`, `UNKNOWN_GROUNDED_RECORD_ID`, `FORBIDDEN_SCIENTIFIC_FIELD`, or `INVALID_GROUNDING_STATUS` rather than returning an opaque boolean.

When a schema-valid response is rejected after execution, `follow-up-answers.json` preserves the valid prior answers, the completed call metadata, a `LiveResponseValidationFailure`, and only safe final response fields (`answer`, `grounding_status`, `grounded_record_ids`, and `limitations`). It never persists hidden reasoning or raw process output.

Consistency runs use a separate controlled contract. Run A is validated against the normal registered state, then its literal grounded IDs are frozen as `CONSISTENCY_GROUNDING_BASIS`. Independent Run B receives exactly that basis and no Run A prose. Consistency responses also require `primary_record_id` and bounded `limitation_codes`; comparison uses a canonical `ConsistencySignature` with sorted unique IDs and codes, so narrative wording and ID ordering do not create false divergence. Any new, missing, unknown, or invented ID remains a failure, including a globally known ID outside Run A's frozen basis. The separate `ConsistencyFailureCode` is stored alongside the underlying `GroundingFailureCode`.

The final gate also records per-call process diagnostics and duration statistics (minimum, median, maximum, p95 when at least two calls exist, and timeout count), while `v5-live-acceptance-digest.json` remains content-addressed and records call/failure/timeout/evidence-mutation counts.

This implementation milestone does not promote the package, alter `main`, merge branches, force-push, change Evidence or EvidenceLevel, or modify `Biolab/` or `formolecular/`. Promotion to `5.0.0` is valid only after the external Live results satisfy the scientific, security, reproducibility, Ledger, wheel, and CI gates.
