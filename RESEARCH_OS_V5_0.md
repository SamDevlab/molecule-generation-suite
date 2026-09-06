# Research OS v5.0 — operational validation status

Status: **RESEARCH OS 5.0.0 — PASS**. Attempt 8 completed the independent top-level Live acceptance with 39/39 calls, all required review/exam/follow-up/stress stages, five consistency pairs, ten controlled consistency calls, cleanup PASS, and zero Codex Evidence or EvidenceLevel mutations. Attempts 1–7 remain immutable historical records; Attempt 7 correctly remains `37/39`, `PRIMARY_RECORD_DRIFT`, `BLOCKED_BEFORE_PASS`. Attempt 7's failure demonstrated that an ID-only frozen basis was incomplete; the completed launcher freezes the full status/IDs/primary/codes signature and attributes cross-run failures to Run B. No additional Live acceptance is required for this release.

The attempted cycle selected a high-information, locally executable question from the registered state: whether a predeclared H2 equilibrium condition at `phi=1.05`, `T0=300 K`, `P=101325 Pa`, `gri30.yaml`, and mole basis added information to the existing combustion boundary. The run produced a sealed E3 physics bundle. It did not produce experimental evidence or change an EvidenceLevel.

The recovery pass first reproduced the minimal Live timeout, then added an explicit `CODEX_LIVE_REENTRANCY` admission guard, `LiveInvocationDiagnostic`, `LiveExecutionBudget`, fixed-process environment/argv controls, timeout classifications, and bounded retry policy. In the current Codex-owned host the corrected boundary now rejects recursive launch before process creation. This is a safe boundary result, not a completed Live response.

The runner also preserved the two paths that should stop: solubility work after the locked DLS external failure and battery/materials work without the missing condition-complete external records. Identical 1PXX docking was recorded as low information gain.

The machine-readable attempt is [master-real-research-validation.json](.research-os-live-5.0/master-real-research-validation.json). The companion files are [final-scientific-exam.json](.research-os-live-5.0/final-scientific-exam.json), [reviewer-panel.json](.research-os-live-5.0/reviewer-panel.json), and [reproduction-matrix.json](.research-os-live-5.0/reproduction-matrix.json).

The recovery diagnostics are [live-boundary-diagnostics.json](.research-os-live-5.0-recovery/live-boundary-diagnostics.json), [live-smoke-matrix.json](.research-os-live-5.0-recovery/live-smoke-matrix.json), and the [provider boundary audit](CODEX_LIVE_PROVIDER_V5_AUDIT.md). Live reviewer, exam, and consistency artifacts remain explicitly blocked.

The top-level acceptance contract, Attempts 1–7 records, grounding diagnostics, worktree policy, and official external command are documented in [TOP_LEVEL_LIVE_ACCEPTANCE_V5_0.md](TOP_LEVEL_LIVE_ACCEPTANCE_V5_0.md). Attempt 1 remains at `.research-os-live-5.0-top-level/`; Attempts 2–7 remain in their numbered namespaces; the next external run must write `.research-os-live-5.0-top-level-attempt-8/` without overwriting prior attempts or recovery artifacts.

## Gate result

The following completed before the Live bridge blocker:

- 15 real/sealed research-program records, including 4 current-turn dynamic selections;
- 150 systematic questions and 50 Codex-current-turn question proposals;
- 3 fresh local runs, all sealed and Ledger-registered;
- 30 sealed-bundle reproductions plus a tamper case with `FIRST_DIVERGENCE`;
- 75 scientific/security/stability stress cases;
- impact traces for knowledge/decision change, no-material-change, and external blockers;
- scientific and security audits with no failed check in the final attempt.

## Release closure

Attempt 8 is the sole release acceptance record: reviewer panel `PASS`, final scientific exam `PASS`, follow-ups `15/15 PASS`, stress `10/10 PASS`, consistency `5/5 pairs PASS` and `10/10` controlled calls with `CONSISTENCY` / `live_consistency.schema.json`, cleanup `PASS`, zero owned child processes remaining, and zero Codex-created Evidence or EvidenceLevel mutations. The package is now `5.0.0`; this release does not claim experimental, clinical, universal-generalization, or scientific-truth status.
