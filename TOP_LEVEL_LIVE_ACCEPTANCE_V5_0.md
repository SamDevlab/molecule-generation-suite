# Top-level Live acceptance — Research OS v5.0

Status: **READY_FOR_TOP_LEVEL_LIVE_EXECUTION**. The release gate remains **BLOCKED_BEFORE_PASS** until an external, genuinely top-level Codex owner completes the bounded Live stages and the resulting artifacts pass the final regression and audit gates.

## Why this boundary exists

The current Codex desktop task is itself a Codex-owned process tree. Direct inspection observed:

`python.exe → python.exe → pwsh.exe → codex.exe → ChatGPT.exe → explorer.exe`

and the environment exposes `CODEX_THREAD_ID`, `CODEX_SESSION_ID`, and `CODEX_INTERNAL_ORIGINATOR_OVERRIDE`. The top-level owner diagnostic therefore returns `TOP_LEVEL_OWNER_REQUIRED`. This is an execution-context fact, not scientific evidence, and no Live launcher was started from this task.

The launcher fails closed when it detects Codex markers, a Codex ancestor, an unresolved process parent, or an inspection failure. It never converts a nested timeout into a scientific result and never substitutes a test provider for Live.

## Official external command

Run from a separately owned terminal or Codex CLI process, after checking out `research-os-v1.3` at the expected commit:

```powershell
.\.venv\Scripts\python.exe tools\benchmark\run_v50_live_top_level.py --run-all --expected-head (git rev-parse HEAD)
```

The command performs preflight checks for branch, expected HEAD, clean worktree, package identity, Ledger, required artifacts, fixed provider/schema contracts, and Codex CLI availability. It then runs only the blocked Live stages sequentially:

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

New machine-readable results are written only under `.research-os-live-5.0-top-level/`. The recovery artifacts under `.research-os-live-5.0-recovery/` and the earlier `.research-os-live-5.0/` attempt are preserved. The launcher records process identity, cleanup, bounded diagnostics, response hashes, grounding checks, and stage outcomes without persisting raw model output in transport diagnostics.

This implementation milestone does not promote the package, alter `main`, merge branches, force-push, change Evidence or EvidenceLevel, or modify `Biolab/` or `formolecular/`. Promotion to `5.0.0` is valid only after the external Live results satisfy the scientific, security, reproducibility, Ledger, wheel, and CI gates.
