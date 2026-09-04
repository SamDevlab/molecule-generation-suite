# Project Health v4.1

Status: **PASS** on `research-os-v1.3`.

## Verification

- Python 3.11: `195 passed, 1 skipped`.
- Python 3.12: `196 passed`.
- `python -m compileall src`: PASS.
- `node --check web/app.js`: PASS.
- `git diff --check`: PASS.
- v4.1 security audit: PASS (bounded execution, no unsafe deserialization,
  no private-corpus read, no Codex scientific authority, no EvidenceLevel
  mutation).
- v4.1 PlanValidator checks: PASS.
- v4.1 fresh Ledger: PASS.
- v4.1 new bundles: PASS.
- Codex-generated program created zero Evidence and changed zero
  EvidenceLevels.

The single Python 3.11 skip remains the expected optional-engine skip from the
prior release: `tests/test_v17_engines.py::test_missing_cantera_is_indeterminate`
is skipped when Cantera is installed on the host. The v4.1 host has Cantera,
so the skip reason is unchanged and is not a scientific failure.

## Current blockers

- AutoDock Vina is not available in the current runtime. New COX-2 protocol
  variants remain a future executable path.
- The solubility model has no eligible independent external dataset.
- No condition-matched Cantera E3↔E4 experimental comparison is registered.
- NASA PCoE RW3 lacks capacity, resistance and uncertainty fields in the
  parsed step schema.
- Materials candidates require exact-file ingestion, license review and field-
  level condition matching.
- No user corpus is present: v4.2 remains `AWAITING_USER_CORPUS`.

`Biolab/` and `formolecular/` remain preserved. No retirement or deprecation
gate has been satisfied for either legacy tree.
