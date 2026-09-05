# CODEX_LIVE provider v5 boundary audit

Status: `BLOCKED_BEFORE_PASS`.

## Finding

The pre-fix `CodexCliTransport` used a direct `subprocess.run(..., shell=False)` call with a fixed `codex exec` argument shape, but it had no admission guard, no invocation lifecycle record, no bounded retry policy, and no explicit stage classification. In the Codex-owned host used for this validation, the minimal real call reproduced:

`LiveCodexUnavailable: Codex CLI invocation failed: TimeoutExpired`

The process environment contained `CODEX_THREAD_ID`, `CODEX_SESSION_ID`, and `CODEX_INTERNAL_ORIGINATOR_OVERRIDE`. This makes a child `codex exec` a recursive session boundary. The previous v5 attempt reached the same timeout during problem discovery, reviewer calls, and the final exam.

## Boundary contract after the fix

- The executable is restricted to the fixed `codex`/`codex.exe` identity and the argv shape is assembled by Research OS.
- `shell=False` is mandatory; prompts are validated structured data, never commands.
- A Codex-owned host is rejected before child-process creation unless a trusted external runner explicitly owns the boundary.
- A context-local active invocation rejects recursive provider entry without waiting or deadlocking.
- Every admitted attempt emits `LiveInvocationDiagnostic` with invocation/parent identity, depth, command contract, timestamps, elapsed time, timeout, exit status, bounded output byte counts, schema status, failure code, and failure stage.
- Subprocess environment forwarding removes Codex session markers and `CODEX_HOME`; no raw output is persisted in the diagnostic artifact.
- `LiveExecutionBudget` bounds total/stage time, live turns, and retries.
- Only provider-start, process-start, and pipe-I/O transients are retryable. Reentrancy, timeout, schema, scientific, evidence, and PlanValidator failures are not retried.

## Diagnosis

The failure was not a scientific result and cannot be repaired by changing Evidence, Claims, Decisions, protocol thresholds, or deterministic engine output. The safe result in the current host is `CODEX_LIVE_REENTRANCY=REJECTED_REENTRANT`. Review roles and the final exam therefore remain unexecuted rather than being replaced by `CodexTestProvider` or fabricated text.

The full call graph is intentionally short:

`CodexLiveProvider operation → CodexCliTransport → fixed subprocess boundary → fixed output schema → Research OS parser/validator`

There is no provider-to-provider recursion in the repository. The unsafe recursion is host-level: the current Codex task launches another Codex session. The guard records that parent context and stops at admission. A standalone process without Codex session markers remains the supported top-level owner.

## Smoke result

The minimal real smoke and the ten-case boundary matrix are recorded in [live-boundary-diagnostics.json](.research-os-live-5.0-recovery/live-boundary-diagnostics.json) and [live-smoke-matrix.json](.research-os-live-5.0-recovery/live-smoke-matrix.json). Case 01 was safely rejected in the current host; cases 06–10 passed as deterministic boundary-policy fixtures; cases 02–05 were not represented as Live output.

The recovery artifacts [reviewer-panel-live.json](.research-os-live-5.0-recovery/reviewer-panel-live.json), [final-scientific-exam-live.json](.research-os-live-5.0-recovery/final-scientific-exam-live.json), and [live-consistency.json](.research-os-live-5.0-recovery/live-consistency.json) preserve the honest blocked state. The earlier `.research-os-live-5.0/` attempt remains unchanged.

The repository now also provides a separate [top-level Live acceptance contract](TOP_LEVEL_LIVE_ACCEPTANCE_V5_0.md). It inspects process ancestry and environment before admission, fails closed in a Codex-owned task, and writes each bounded acceptance under a fresh `.research-os-live-5.0-top-level-attempt-N/` namespace. Attempts 1 and 2 are preserved; this task did not execute the next Live launcher.

The first genuine top-level attempt is preserved at `.research-os-live-5.0-top-level/`: calls 1–16 completed under the Live boundary, and call 17 (`V5-FOLLOWUP-13`) completed with process/schema/cleanup `PASS` but was rejected by the previous boolean-only grounding gate. Attempt 2 is preserved separately at `.research-os-live-5.0-top-level-attempt-2/` and stopped at call 33 (`TL-CONSISTENCY-02-B`) when the real model returned the unregistered `CH-V45-SOLUBILITY-EXTERNAL-BOUNDARY`; the exact grounding and consistency failure remains visible. The hardened acceptance now reports `GroundingValidationResult`, `LiveResponseValidationFailure`, frozen consistency bases and canonical signatures, requires explicit `grounding_status`, and persists only safe final structured fields from a rejected response.

## Release decision

The boundary hardening is testable and regression-safe, but v5.0 is not released: a real top-level Live response, three Live review roles, the final Live exam, follow-ups, and consistency checks were not completed. The package remains `4.5.0`. The next valid action is to run the same bounded recovery script from a genuinely top-level Codex CLI owner, then rerun only the blocked Live gates.
