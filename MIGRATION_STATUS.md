# Migration status

| Area | Status | Evidence | Remaining gate |
|---|---|---|---|
| Legacy inventory | MIGRATING | 966 components, 2 flows, hashes and flags from read-only scanner | review every quarantined artifact |
| Deterministic molecular descriptors | REPLACED for declared descriptor scope | RDKit side-by-side parity contract and tests | keep version/protocol pinned |
| Pharma ML predictions | MIGRATING | model boundary exists | provenance, split and independent validation |
| Aerospace Isp-like target | MIGRATING | `HEURISTIC_REVIEW` classification | real physics protocol or independent experiment |
| Legacy docking | MIGRATING | target/species/grid/preparation contracts | configure and execute real Vina/Open Babel reference campaign |
| Historical datasets/models | ACTIVE + QUARANTINED | manifests default to `eligible_for_training=false` | provenance/license/conditions/split review |

Retirement is intentionally not claimed. `Biolab/` and `formolecular/` remain
untouched and available for audit.

