# Project Health — Research OS 3.2

## Summary

| Area | Implemented | Operational | Tested | Status |
|---|---:|---:|---:|---|
| Research OS core and version | yes | yes | yes | PASS |
| Codex deterministic CI provider | yes | yes | yes | PASS |
| Codex live Oracle bridge | yes | yes in the Codex host | live acceptance | PASS |
| Plan validation and bounded repair | yes | yes | yes | PASS |
| Narration grounding and audit trace | yes | yes | yes | PASS |
| Web chat and audit inspector | yes | yes locally | yes | PASS |
| Ledger, bundles and lineage | existing and connected | yes | yes | PASS |
| Knowledge retrieval | yes | yes locally | yes | PASS |
| Preserved legacy trees | preserved | audited | yes | PRESERVED |

## Required status surface

```text
CODEX DETERMINISTIC TEST PROVIDER: PASS
CODEX LIVE ORACLE: PASS
LIVE REASONING: VALIDATED
SCIENTIFIC EVIDENCE PROVIDER: FALSE
EXTERNAL LLM API: NOT_REQUIRED_FOR_THIS_MILESTONE
STANDALONE WEB LLM: NOT_AVAILABLE / STANDALONE_LLM_BRIDGE_NOT_IMPLEMENTED
PLAN VALIDATION: ENFORCED
GROUNDING: ENFORCED
```

## Engine readiness

| Engine | Local validated state | Evidence boundary |
|---|---|---|
| RDKit | available; real molecular acceptance path executed | E2 computational |
| Cantera | available; version 3.2.0; real `gri30.yaml` reference path executed | E3 physics simulation |
| Open Babel | not configured | preparation only; no default execution |
| AutoDock Vina | not configured | docking E2 only; missing engine is indeterminate |
| pymatgen | unavailable in the validated runtime | materials path unavailable |
| matminer | unavailable in the validated runtime | materials path unavailable |
| pycalphad | unavailable in the validated runtime | thermodynamic path unavailable |

Engine availability, configuration, execution and reference validation remain
separate facts. A discovered adapter is never represented as executed.

## Live acceptance

The operational report is generated locally and intentionally ignored by Git:

```powershell
.\.venv\Scripts\python.exe tools\oracle\codex_live.py `
  --data-root .research-os-live-3.2 `
  --output .research-os-live-3.2\live-acceptance.json
```

The suite covers the bridge, real RDKit and Cantera execution, Vina absence,
claim containment, prompt-injection resistance, E4 insufficiency, Knowledge
citation, continuation lineage, ranking grounding, first divergence and the
bounded experimental gap. Deterministic CI remains independent of this live
report.

## Known limits and blockers

- A local Codex session is required for the live operational harness; no
  standalone web LLM service is claimed.
- Live model output remains a proposal/narration boundary and cannot create
  scientific evidence.
- Cantera `gri30.yaml` is mechanism-scoped and does not support arbitrary fuel
  names; unsupported mechanisms/fuels remain explicit losses.
- Vina/Open Babel and materials engines require separate local configuration.
- Knowledge user imports remain `REVIEW_REQUIRED` until human review.
- The preserved legacy `Biolab/` and `formolecular/` trees retain their own
  historical scope and retirement gates; they were not modified.
