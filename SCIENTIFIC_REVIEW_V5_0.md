# Scientific review panel — v5.0 attempt

The required panel was dispatched sequentially against the same stored evidence. Each role timed out at the Live bridge before returning a grounded review response:

| Reviewer | Concern | Evidence | Response | Final status |
|---|---|---|---|---|
| Methodology | Live response unavailable | Stored v4.1/v4.3/v4.5 records were supplied | Keep scope-limiting concerns open; do not revise from absent review text | BLOCKED |
| Evidence | Live response unavailable | Stored DLS failure, battery schema, and materials blocker were supplied | Preserve existing failed/blocked statuses; no promotion | BLOCKED |
| Reproducibility | Live response unavailable | Stored bundle paths, hashes, environment and fresh run IDs were supplied | Preserve reproduction follow-up; no PASS claim | BLOCKED |

These are `REVIEW / ANALYSIS` attempts, not Evidence. The v5.0 gate therefore remains blocked rather than being marked as a successful independent review.

The recovery pass did not fabricate replacement panel text. The three roles remain explicitly `NOT_EXECUTED_LIVE_BOUNDARY_BLOCKED` in `.research-os-live-5.0-recovery/reviewer-panel-live.json` after the corrected provider rejected recursive launch in the current Codex-owned host.

Top-level Attempt 1 is a separate real operational record at `.research-os-live-5.0-top-level/`: the three reviewers and final exam completed, while the 13th follow-up was rejected after a schema-valid response failed the previous boolean-only grounding check. This is not a scientific contradiction. The next acceptance uses explicit grounding status, literal Ledger-ID validation, and safe post-response failure diagnostics; reviewer findings remain `REVIEW / ANALYSIS`, never Evidence.
