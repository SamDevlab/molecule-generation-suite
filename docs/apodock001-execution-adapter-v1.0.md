# APODOCK-001 execution adapter v1.0.1

This document describes the infrastructure prepared for the first
prospective run. It does not authorize or perform docking.

The adapter loads the frozen manifest through `APODOCK001Runner`, verifies the
complete frozen execution manifest, checks the exact Vina and Open Babel
identities, builds a deterministic ten-case `APODOCK001ExecutionPlan`, and
creates a no-results evidence scaffold. The protocol JSON and protocol ID are
not modified.

The command builder is pure: it returns only the frozen Vina argv and never
starts a process. It emits only `--receptor`, `--ligand`, the frozen box
coordinates and sizes, `--exhaustiveness`, `--cpu`, `--seed`, `--num_modes`,
and `--out`. `energy_range` is rejected.

Preparation boundaries are explicit. Receptor preparation selects the frozen
apo author chain and writes a chain-only PDB before the existing Open Babel
adapter performs the frozen `-h --partialcharge gasteiger -xr` conversion.
Ligand preparation reuses the reviewed ETKDGv3/UFF implementation with seed
42 and 1000 iterations. APD-010 is represented in the plan by the frozen
BEM+MAV adapter identities; no alternate chemical reconstruction is allowed.

Prepared receptor and ligand PDBQT files are staged outside `run_root` under
an explicit `staging_root`. Every one of the ten receptor/ligand pairs is
checked for the frozen source hashes, preparation contract, protocol ID, and
planned run ID. Only after the complete staging set passes validation is the
run lock created; the files are then copied byte-for-byte into
`run_root/prepared/<CASE>/` and hashed again before any future Vina call.
Missing, duplicate, mutated, or contract-divergent artifacts fail closed.

`ExecutionAuthorization` defaults to false and requires the exact label
`APODOCK-001-v1.0.1`. The adapter also rejects an existing raw PDBQT, SDF,
seal, or run-manifest marker in the future run directory. The infrastructure
workflow verifies Vina with `vina --version` and its frozen SHA-256, verifies
Open Babel 3.1.1, runs tests, builds the plan, and writes a scaffold whose
status is `NOT_EXECUTED`. It never supplies a receptor or ligand to Vina.

The future execution must occur only after this infrastructure is reviewed
and merged, with a separately authorized prospective run.
