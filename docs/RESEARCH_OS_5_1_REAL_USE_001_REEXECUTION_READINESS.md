# REAL-USE-001 re-execution readiness

Status at the beginning of the 5.1 cycle: `BLOCKED_BY_PRODUCT_GAP`.

This document records readiness criteria only. It is not a new scientific
result and does not authorize Live Acceptance.

## Required product gates

| Gap | Product gate | 5.1 implementation status |
|---|---|---|
| BRK-001 | canonical campaign/source registration, provenance, fingerprint and idempotence | Implemented and unit/integration-tested |
| BRK-002 | deterministic Gemmi mmCIF parser, canonical normalization, fail-closed ligand identity | Implemented and unit-tested with 5KIR/5IKR plus altloc/model/duplicate/missing/truncated/inconsistent fixtures |
| BRK-003 | deterministic atom mapping, declared symmetry handling, RMSD diagnostics | Implemented and unit-tested for reorder, heavy/all-atom, identity, connectivity and missing-atom cases |
| BRK-004 | formal Vina/Open Babel adapter registration and preflight | Implemented with typed availability/version/input/execution/output states; current development host reports both external executables unavailable |
| BRK-005 | typed remote failure codes, local hash integrity and comparability state | Implemented and unit-tested |

## Runtime gate still required

The future re-execution must run the normal top-level preflight on a clean,
owned environment and record actual manifests for the two external engines.
`EnginePreflight` must return `ENGINE_AVAILABLE` for both `autodock-vina` and `openbabel`
before preparation or docking can start. Their current absence in this
development host is reported as unavailable; it is not converted into a fake
successful run.

The re-execution must then independently verify:

1. 5KIR and 5IKR source IDs and hashes;
2. selected chains and ligand component IDs;
3. receptor and ligand preparation manifests;
4. explicit grid, seed, exhaustiveness, CPU and timeout;
5. output hashes and immutable run/bundle records;
6. docking score and pose-recovery diagnostics as E2 only;
7. no unsupported cross-structure claim.

Until the full preflight, external-engine availability, bundle sealing, and
post-run audit are completed by the authorized external runner, the correct
status remains `BLOCKED_BY_PRODUCT_GAP` for real-use execution. This branch
does not run that execution.
