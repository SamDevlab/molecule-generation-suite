# Top-level Live acceptance — Research OS v5.0

Status: **READY_FOR_TOP_LEVEL_SCHEMA_SMOKE**. The release gate remains **BLOCKED_BEFORE_PASS** until the provider-compatible schema smoke and then an external, genuinely top-level Codex owner completes the bounded Live stages and the resulting artifacts pass the final regression and audit gates.

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

## Top-level Attempt 3 — preserved

The third genuine external acceptance is preserved at `.research-os-live-5.0-top-level-attempt-3/`. It completed 30/39 calls: the three reviewers, the final exam, 15 follow-ups, 10 stress answers, and Run A of consistency pair 1. Calls 1–30 completed with process, schema, and child-cleanup success; the general grounding validator also passed Run A because all six returned IDs were registered.

The run stopped at call 30, `TL-CONSISTENCY-01-A`. Its structured response omitted the required `primary_record_id` and `limitation_codes` fields. The limitation text contained prose prefixes, but prose is not parsed into canonical limitation codes. Run B was therefore not executed, and the consistency assessment correctly recorded `RUN_A_GROUNDING_FAILURE`. The original artifact predates the structured contract diagnostics and consequently has no top-level failure fields; it remains unchanged. Cleanup passed, Codex created zero Evidence, no EvidenceLevel changed, and no scientific state changed. This is a provider-shape contract failure, not a scientific failure.

## Top-level Attempt 4 — preserved

The fourth genuine external acceptance is preserved at `.research-os-live-5.0-top-level-attempt-4/`. It again completed 30/39 calls: 3 reviewers, the final exam, 15/15 follow-ups, 10/10 stress answers, and Run A of consistency pair 1. The final gate correctly propagated `failure_code=RUN_A_GROUNDING_FAILURE`, `consistency_failure_code=RUN_A_GROUNDING_FAILURE`, `failed_call_id=30`, and `failed_label=TL-CONSISTENCY-01-A`; cleanup passed with zero owned child processes remaining.

Attempt 4 made the architectural gap explicit. Its outer `live_output.schema.json` envelope passed, but the inner consistency object still omitted `primary_record_id` and `limitation_codes`. The existing `live_consistency.schema.json` was not selected for `codex exec`, so the launcher discovered the omission only after transport acceptance. Attempt 4 is preserved without modification and remains an operational contract failure, not a scientific result.

## Top-level Attempt 5 — preserved

The fifth genuine external acceptance is preserved at `.research-os-live-5.0-top-level-attempt-5/`. It completed 30/39 calls with reviewers, final exam, 15/15 follow-ups, 10/10 stress answers, and Run A of consistency pair 1. Call 30 (`TL-CONSISTENCY-01-A`) completed process execution, but its diagnostic reported `output_contract=ENVELOPE` and `output_schema_name=live_output.schema.json`; Run B was therefore not executed. Cleanup passed with no owned child processes remaining.

Attempt 5 isolated the remaining integration defect as `PER_CALL_CONTEXT_PROPAGATION_BUG`: `consistency_run` and `consistency_contract` were present in `payload.followup_context`, but `CodexLiveProvider` forwarded only its persistent global request context to the transport. The strict transport routing was correct for the context it received. This implementation milestone fixes the provider boundary; Attempt 5 remains immutable and is not a scientific result.

## Top-level Attempt 6 — preserved

The sixth genuine external acceptance is preserved at `.research-os-live-5.0-top-level-attempt-6/`. It completed 30/39 calls with all three reviewers, the final exam, 15/15 follow-ups, 10/10 stress answers, and Run A of consistency pair 1. The corrected per-call propagation reached the intended route: call 30 (`TL-CONSISTENCY-01-A`) reported `output_contract=CONSISTENCY` and `output_schema_name=live_consistency.schema.json`.

Attempt 6 then stopped before a response was accepted because the provider process returned `PROCESS_ERROR` during completion; `schema_status=NOT_CHECKED`, `failure_code=PROCESS_ERROR`, and the final gate preserved the secondary `consistency_failure_code=RUN_A_GROUNDING_FAILURE`. Cleanup passed with no owned child processes remaining and no child acceptance stages were started. This is an operational provider-admission finding, not scientific evidence. The provider-facing schema was subsequently reduced to the six required structural fields and deterministic validators retain the cross-field semantics. A bounded typed `OUTPUT_SCHEMA_ADMISSION_ERROR` diagnostic is now available for recognized provider schema rejection messages without persisting raw stderr.

The next external action is a one-call fresh-namespace schema smoke. It must pass before the 39-call Attempt 7 launcher is permitted. This current Codex-owned task does not execute either Live action.

## Consistency-schema Smoke 1 — preserved

The first real external consistency-schema smoke is preserved immutably at `.research-os-live-5.0-consistency-schema-smoke/`. The Live invocation, provider route, `CONSISTENCY` contract, `live_consistency.schema.json`, schema validation, grounding validation, consistency validation, and forbidden-field check all passed. It returned one completed call with `failure_code=null`, `failure_stage=NONE`, and `schema_status=PASS`.

The overall smoke gate was `BLOCKED_BEFORE_PASS` only because `process-cleanup.json` aggregated both historical observer events for one PID instead of the final state: `RUNNING` followed by `EXITED` was incorrectly reported as `owned_child_processes_remaining=true`. This is classified as `PROCESS_EVENT_FINAL_STATE_AGGREGATION_BUG`, not a provider, schema, grounding, consistency, or scientific failure. Smoke 1 remains unchanged; no artifact is rewritten to make it pass.

The cleanup implementation now aggregates the final observed event for each owned PID, and the next smoke automatically selects `.research-os-live-5.0-consistency-schema-smoke-attempt-2/`.

## Official external command

Run from a separately owned terminal or Codex CLI process, after checking out `research-os-v1.3` at the expected commit:

```powershell
.\.venv\Scripts\python.exe tools\benchmark\run_v50_live_top_level.py --run-all --expected-head (git rev-parse HEAD)
```

The command performs preflight checks for branch, expected HEAD, clean worktree, package identity, Ledger, required artifacts, fixed provider/schema contracts, and Codex CLI availability. The Attempt 7 wrapper first runs the one-call consistency-schema smoke in a fresh namespace; only a smoke `PASS` permits the 39 blocked Live stages. The next run selects `.research-os-live-5.0-consistency-schema-smoke-attempt-2/` and, after smoke `PASS`, `.research-os-live-5.0-top-level-attempt-7/`; prior attempts are never overwritten and reruns select the next unused namespace.

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

New machine-readable results are written only under a fresh `.research-os-live-5.0-top-level-attempt-N/` namespace or the fresh `.research-os-live-5.0-consistency-schema-smoke[-attempt-N]/` namespace. The Attempt 1 artifacts under `.research-os-live-5.0-top-level/`, Attempts 2–6 under their numbered namespaces, the recovery artifacts under `.research-os-live-5.0-recovery/`, and the earlier `.research-os-live-5.0/` attempt are preserved. The launcher records process identity, cleanup, bounded diagnostics, response hashes, structured grounding failures, output contract/schema metadata, and stage outcomes without persisting raw model output or hidden reasoning.

Each attempt recognizes only these generated files: `top-level-owner-diagnostic.json`, `top-level-preflight.json`, `reviewer-panel.json`, `review-synthesis.json`, `final-scientific-exam.json`, `follow-up-answers.json`, `live-stress.json`, `live-consistency.json`, `process-cleanup.json`, `v5-live-acceptance-digest.json`, and `v5-final-gate.json`. Any other changed or untracked path, including an unknown file inside an acceptance namespace, keeps preflight at `DIRTY_WORKTREE`.

## Grounding recovery contract

Follow-up, stress, consistency, and final-exam responses must declare `grounding_status`. `GROUNDED` requires at least one literal member of `ALLOWED_GROUNDED_RECORD_IDS`; `NO_GROUNDED_ANSWER` requires an empty ID list and an explicit limitation. The deterministic validator reports `NONE`, `INVALID_RESPONSE_TYPE`, `MISSING_GROUNDED_RECORD_IDS`, `INVALID_GROUNDED_RECORD_IDS_TYPE`, `EMPTY_GROUNDING_FOR_GROUNDED_ANSWER`, `UNKNOWN_GROUNDED_RECORD_ID`, `FORBIDDEN_SCIENTIFIC_FIELD`, or `INVALID_GROUNDING_STATUS` rather than returning an opaque boolean.

When a schema-valid response is rejected after execution, `follow-up-answers.json` preserves the valid prior answers, the completed call metadata, a `LiveResponseValidationFailure`, and only safe final response fields (`answer`, `grounding_status`, `grounded_record_ids`, and `limitations`). It never persists hidden reasoning or raw process output.

Consistency runs use a separate controlled contract. Run A is validated against the normal registered state, then its literal grounded IDs are frozen as `CONSISTENCY_GROUNDING_BASIS`. Independent Run B receives exactly that basis and no Run A prose. Both A and B must return the strict six-field response from `live_consistency.schema.json`: `answer`, `grounding_status`, `grounded_record_ids`, `primary_record_id`, `limitation_codes`, and `limitations`. `primary_record_id` must be one literal member of the frozen basis for a grounded answer; `limitation_codes` must be drawn from `CONSISTENCY_LIMITATION_CODES`, and limitation prose is never parsed. Comparison uses a canonical `ConsistencySignature` with sorted unique IDs and codes, so narrative wording and ID ordering do not create false divergence. Any new, missing, unknown, or invented ID remains a failure, including a globally known ID outside Run A's frozen basis. Contract diagnostics distinguish `MISSING_PRIMARY_RECORD_ID`, `INVALID_PRIMARY_RECORD_ID`, `MISSING_LIMITATION_CODES`, `INVALID_LIMITATION_CODES`, `INVALID_LIMITATIONS`, and `INVALID_CONSISTENCY_RESPONSE`. The separate `ConsistencyFailureCode` is stored alongside the underlying `GroundingFailureCode`.

The transport now selects one internal `LiveOutputContract` before `codex exec`: ordinary operations use the fixed `ENVELOPE` contract and `live_output.schema.json`; a `final_exam_followup`/`final_exam_followups` request with `context.consistency_contract` uses the fixed `CONSISTENCY` contract and `live_consistency.schema.json`. The schema registry is closed, the model cannot select it, arbitrary constructor paths are rejected, consistency JSON is direct rather than wrapped in `result`, and the provider parses according to the already-selected contract. `CodexLiveProvider` now merges only an explicit per-call allowlist into the transport context; security-sensitive global owner/state fields cannot be overwritten, and per-call consistency metadata cannot contaminate later calls. The envelope and consistency forms are each rejected when supplied to the other mode.

The provider-facing consistency schema intentionally contains only portable structural keywords: the six required fields, primitive/object/array types, enums, array item types, and `additionalProperties=false`. Cross-field rules, uniqueness, and minimum/maximum cardinality remain deterministic Research OS validators in the transport and top-level launcher. This avoids depending on provider-specific support for `allOf`, `if/then`, `uniqueItems`, or `minItems`/`maxItems`. Recognized provider schema-admission failures are surfaced as the bounded typed code `OUTPUT_SCHEMA_ADMISSION_ERROR`; raw stderr, hidden reasoning, and secrets are never persisted.

The final gate exposes failure precedence explicitly: provider/process failures first, the underlying `GroundingFailureCode` second, and the `ConsistencyFailureCode` third. When a consistency response is structurally invalid but the general grounding contract passed, the top-level fields are `failure_code=RUN_A_GROUNDING_FAILURE`, `consistency_failure_code=RUN_A_GROUNDING_FAILURE`, and the failed call identity. If a lower-level grounding failure also exists, its code remains the primary `failure_code` and the consistency code is preserved separately.

The final gate also records per-call process diagnostics and duration statistics (minimum, median, maximum, p95 when at least two calls exist, and timeout count), while `v5-live-acceptance-digest.json` remains content-addressed and records call/failure/timeout/evidence-mutation counts.

This implementation milestone does not promote the package, alter `main`, merge branches, force-push, change Evidence or EvidenceLevel, or modify `Biolab/` or `formolecular/`. Promotion to `5.0.0` is valid only after the external Live results satisfy the scientific, security, reproducibility, Ledger, wheel, and CI gates.
