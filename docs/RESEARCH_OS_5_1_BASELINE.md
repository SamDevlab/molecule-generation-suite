# Research OS 5.1 pre-release baseline

Status: development branch only. This document is not a 5.1.0 release claim.

## Frozen release and scope

- Branch: `research-os-5.1-external-research-ingestion`
- Base commit: `3176a48742489ccbb72caafe4af00df5b5ae2286`
- Frozen Research OS release: 5.0.0
- Package version: `5.0.0`
- Protected main reference at cycle start: `beebb9d3e4eb6954102918cecc0a337ea25163ba`
- Protected directories: `Biolab/`, `formolecular/`
- Historical real-use branch: `research-use-001-cox2-cross-structure`
- Live Acceptance: not executed in this cycle

The branch starts exactly at the released 5.0.0 commit. No scientific
conclusion is produced by this pre-release cycle. The purpose is to close the
product gaps recorded by `REAL_USE_001_BREAKAGE_LOG.md` before a future,
separately authorized re-execution.

## Gate Zero evidence

| Check | Result |
|---|---|
| Python 3.11 full suite | `373 passed, 1 skipped` |
| Python 3.12 full suite | `374 passed` |
| Python 3.12 package gate | `research-os-core==5.0.0` |
| `python -m compileall src tools tests` | PASS |
| `node --check web/app.js` | PASS |
| `git diff --check` | PASS before implementation changes |

An initial Python 3.12 baseline run reported one failure in
`test_package_gate_reports_released_v5` because the interpreter had stale local
metadata for `research-os-core==1.4.0`. The source tree was not changed for
that failure. Installing the frozen source package as 5.0.0 corrected the
environment, after which the complete suite passed with 374 tests.

The single Python 3.11 baseline skip was the intentional
`test_missing_cantera_is_indeterminate` skip: that baseline interpreter had
the optional Cantera package installed, so the test did not exercise the
missing-engine branch. In the final local environments Cantera is absent and
the full suite reports `395 passed` on both Python 3.11 and Python 3.12.

## Development contract

This cycle preserves the canonical evidence ceiling and authority model:

- external ingestion registers provenance and content identity; it does not
  create scientific Evidence;
- mmCIF parsing is deterministic and fail-closed on missing or ambiguous
  structure identity;
- RMSD is a typed computational diagnostic and remains E2;
- engine preflight can stop execution when Vina or Open Babel is unavailable;
- engine preflight distinguishes version mismatch, unsupported input, timeout,
  execution failure and invalid output;
- source HTTP failures and local artifact hash failures remain distinct states;
- no source is replaced silently and no historical record is overwritten.

The package version remains 5.0.0. A 5.1.0 tag or release is out of scope.
