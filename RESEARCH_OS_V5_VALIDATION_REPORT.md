# Research OS v5.0 validation report

This is an execution report for the v5.0 attempt, not a release declaration.

| Measure | Observed | Gate |
|---|---:|---|
| Research programs | 15 | PASS, minimum 12 |
| Codex-dynamic programs | 4 | PASS, minimum 4 |
| Systematic questions | 150 | PASS |
| Codex-current-turn questions | 50 | PASS |
| Total questions | 200 | PASS |
| Fresh engine runs | 3 | PASS, bundles and Ledger registration |
| Sealed replays | 30 | PASS |
| FIRST_DIVERGENCE cases | 1 | PASS |
| Stress cases | 75 | PASS |
| Live reviewer roles | 0 completed | BLOCKED: nested CODEX_LIVE timeout |
| Final Live exam | 0 completed | BLOCKED: nested CODEX_LIVE timeout |
| Boundary recovery smoke | 1 real attempt + 9 bounded cases | SAFE REJECTION in Codex-owned host; Live gate remains blocked |
| Top-level owner launcher | implemented; 0 calls from this task | READY: requires genuinely external owner; configured for 39 sequential calls, ceiling 45 |

The fresh H2 run at `phi=1.05` returned `2395.300775369576 K` under the declared Cantera HP-equilibrium protocol. This is E3 physics output and is not an E4/E5 experiment. The associated material change is a narrow condition-map extension, not a universal combustion claim.

The DLS-100 validation remains a failed unrestricted-generalization test: its 56-record unique subset was OOD for the frozen model, with no retraining or post-result threshold tuning. Battery and hydrogen-materials questions remain blocked by missing condition-complete external records. No private user corpus was found; v4.2 remains `INFRASTRUCTURE_READY_AWAITING_USER_CORPUS`.

The authoritative status is in `.research-os-live-5.0/master-real-research-validation.json`; its `status_checks` field is the gate record.

The recovery pass did not overwrite that prior attempt. Its diagnostic, smoke matrix, and blocked Live-stage artifacts are under `.research-os-live-5.0-recovery/`. The corrected provider records `REJECTED_REENTRANT` at admission in this host, so no reviewer/exam answer is counted as Live.

The official external execution contract is [TOP_LEVEL_LIVE_ACCEPTANCE_V5_0.md](TOP_LEVEL_LIVE_ACCEPTANCE_V5_0.md). The top-level launcher was not invoked from this Codex-owned task.
