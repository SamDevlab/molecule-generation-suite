# Project Health — Research OS 3.1

## Summary

| Area | Implemented | Operational | Tested | Blocker | Status |
|---|---:|---:|---:|---|---|
| Software core | yes | yes | yes | none known | PASS |
| Oracle | yes | yes | yes | external production LLM intentionally not configured | PASS |
| Web chat | yes | yes locally | yes | no deployment target requested | PASS |
| Sessions/jobs | yes | yes locally | yes | background execution is synchronous in this milestone | PASS |
| Knowledge OS | yes | yes locally | yes | user corpus awaiting review when absent | PASS |
| Ledger/bundles | existing and connected | yes | yes | none known | PASS |
| Autonomous loop | existing bounded loop | library-ready | yes | not exposed as an unbounded chat action | PASS |
| Legacy | preserved | audited | yes | Biolab/formolecular retirement gates unmet | PRESERVED |

## Engine readiness

| Engine | Boundary | Available | Configured | Executed | Reference Validated |
|---|---|---|---|---|---|
| RDKit | IMPLEMENTED | runtime probe | runtime probe | per MoleculeLab run | no global reference case |
| Cantera | IMPLEMENTED | runtime probe | runtime probe | safe reference attempt | only after successful reference |
| Open Babel | IMPLEMENTED | argv probe | executable config | no default run | no |
| AutoDock Vina | IMPLEMENTED | argv probe | executable config | no default run | no |
| pymatgen | IMPLEMENTED | import probe | runtime probe | no default run | no |
| matminer | IMPLEMENTED | import probe | runtime probe | no default run | no |
| pycalphad | IMPLEMENTED | import probe | runtime probe | no default run | no |

The UI derives these values from actual manifests; an adapter alone is never
shown as executed or reference-validated.

## Scientific audit

- LLM/narrator output cannot create Evidence.
- Knowledge retrieval produces citations only.
- Evidence ceilings and required levels are fail-closed.
- Simulation is not represented as experiment; docking is capped at E2.
- OOD candidates are excluded from normal ranking.
- Missing engines produce `INDETERMINATE` and downstream `SKIPPED`.
- Verified knowledge requires a source locator.

## Remaining blockers

There is no production LLM or external deployment requirement in this
milestone. Cantera, Open Babel, Vina and materials engines depend on optional
local installations and therefore truthfully remain unavailable or
not-configured when absent. The existing `Biolab/` and `formolecular/` trees
remain preserved until their independent retirement gates are met.
