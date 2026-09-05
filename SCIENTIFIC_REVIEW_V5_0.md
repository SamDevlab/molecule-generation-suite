# Scientific review panel — v5.0 attempt

The required panel was dispatched sequentially against the same stored evidence. Each role timed out at the Live bridge before returning a grounded review response:

| Reviewer | Concern | Evidence | Response | Final status |
|---|---|---|---|---|
| Methodology | Live response unavailable | Stored v4.1/v4.3/v4.5 records were supplied | Keep scope-limiting concerns open; do not revise from absent review text | BLOCKED |
| Evidence | Live response unavailable | Stored DLS failure, battery schema, and materials blocker were supplied | Preserve existing failed/blocked statuses; no promotion | BLOCKED |
| Reproducibility | Live response unavailable | Stored bundle paths, hashes, environment and fresh run IDs were supplied | Preserve reproduction follow-up; no PASS claim | BLOCKED |

These are `REVIEW / ANALYSIS` attempts, not Evidence. The v5.0 gate therefore remains blocked rather than being marked as a successful independent review.

The recovery pass did not fabricate replacement panel text. The three roles remain explicitly `NOT_EXECUTED_LIVE_BOUNDARY_BLOCKED` in `.research-os-live-5.0-recovery/reviewer-panel-live.json` after the corrected provider rejected recursive launch in the current Codex-owned host.

Top-level Attempt 1 is a separate real operational record at `.research-os-live-5.0-top-level/`, Attempt 2 is preserved at `.research-os-live-5.0-top-level-attempt-2/`, and Attempt 3 at `.research-os-live-5.0-top-level-attempt-3/`. Attempt 2 reached `TL-CONSISTENCY-02-B` before a schema-valid response introduced the unregistered literal `CH-V45-SOLUBILITY-EXTERNAL-BOUNDARY`; its `UNKNOWN_GROUNDED_RECORD_ID` rejection is a correct fail-closed result and is classified as `MODEL_REFERENCE_HALLUCINATION`. Attempt 3 reached `TL-CONSISTENCY-01-A`; its registered IDs passed general grounding, but the response omitted `primary_record_id` and `limitation_codes`, so Run B was not run. The next acceptance enforces the strict six-field shape, freezes Run A's support basis for independent Run B, and compares structured signatures; reviewer findings remain `REVIEW / ANALYSIS`, never Evidence.
