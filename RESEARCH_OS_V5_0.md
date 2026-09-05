# Research OS v5.0 — operational validation status

Status: **READY_FOR_TOP_LEVEL_LIVE_EXECUTION**; release gate remains **BLOCKED_BEFORE_PASS**. The v5.0 runner completed the bounded scientific work, and the repository now has a fail-closed top-level owner boundary for the still-blocked Live stages. No Live launcher was executed from the current Codex-owned task and no test provider was substituted.

The attempted cycle selected a high-information, locally executable question from the registered state: whether a predeclared H2 equilibrium condition at `phi=1.05`, `T0=300 K`, `P=101325 Pa`, `gri30.yaml`, and mole basis added information to the existing combustion boundary. The run produced a sealed E3 physics bundle. It did not produce experimental evidence or change an EvidenceLevel.

The recovery pass first reproduced the minimal Live timeout, then added an explicit `CODEX_LIVE_REENTRANCY` admission guard, `LiveInvocationDiagnostic`, `LiveExecutionBudget`, fixed-process environment/argv controls, timeout classifications, and bounded retry policy. In the current Codex-owned host the corrected boundary now rejects recursive launch before process creation. This is a safe boundary result, not a completed Live response.

The runner also preserved the two paths that should stop: solubility work after the locked DLS external failure and battery/materials work without the missing condition-complete external records. Identical 1PXX docking was recorded as low information gain.

The machine-readable attempt is [master-real-research-validation.json](.research-os-live-5.0/master-real-research-validation.json). The companion files are [final-scientific-exam.json](.research-os-live-5.0/final-scientific-exam.json), [reviewer-panel.json](.research-os-live-5.0/reviewer-panel.json), and [reproduction-matrix.json](.research-os-live-5.0/reproduction-matrix.json).

The recovery diagnostics are [live-boundary-diagnostics.json](.research-os-live-5.0-recovery/live-boundary-diagnostics.json), [live-smoke-matrix.json](.research-os-live-5.0-recovery/live-smoke-matrix.json), and the [provider boundary audit](CODEX_LIVE_PROVIDER_V5_AUDIT.md). Live reviewer, exam, and consistency artifacts remain explicitly blocked.

The top-level acceptance contract and official external command are documented in [TOP_LEVEL_LIVE_ACCEPTANCE_V5_0.md](TOP_LEVEL_LIVE_ACCEPTANCE_V5_0.md). Its output namespace is `.research-os-live-5.0-top-level/`; it does not overwrite prior attempts or recovery artifacts.

## Gate result

The following completed before the Live bridge blocker:

- 15 real/sealed research-program records, including 4 current-turn dynamic selections;
- 150 systematic questions and 50 Codex-current-turn question proposals;
- 3 fresh local runs, all sealed and Ledger-registered;
- 30 sealed-bundle reproductions plus a tamper case with `FIRST_DIVERGENCE`;
- 75 scientific/security/stability stress cases;
- impact traces for knowledge/decision change, no-material-change, and external blockers;
- scientific and security audits with no failed check in the final attempt.

The release remains 4.5.0 until the three sequential Live review roles, Live problem discovery, and Live final examination return grounded analysis from the same stored evidence.
