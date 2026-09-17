# Research OS v1.7 — Real Scientific Engines

v1.7 adds fail-closed boundaries for Cantera, Open Babel, AutoDock Vina,
pymatgen, matminer and pycalphad. The implementation records engine identity,
version, configuration hash, protocol, input/output hashes, environment and
scientific artifact provenance in `EngineManifest` records. Research bundles
store these in `engines/manifests.json` and verify their hashes.

## Execution semantics

An engine can be `AVAILABLE`, `NOT_CONFIGURED`, `UNAVAILABLE` or have an
`EXECUTION_FAILED` outcome. Run-level status distinguishes
`SUPPORTED_AND_EXECUTED`, `AVAILABLE_BUT_NOT_EXECUTED`, `NOT_CONFIGURED`,
`UNAVAILABLE`, `INDETERMINATE` and `EXECUTION_FAILED`. A probe is not a
reference validation. A deterministic calculation, physics simulation, ML
prediction and experiment remain separate evidence levels.

Cantera requires a resolvable mechanism and records its SHA-256, phase, species
count and reaction count. Propulsion consumes the resulting thermodynamic
evidence and has no SMILES-to-Isp path. Open Babel preparation records separate
ligand and receptor manifests. Vina records per-target grids, seed and artifact
hashes; replicated campaigns remain E2 computational evidence. Docking claims
are blocked from clinical, safety, efficacy and experimental-affinity language.

Materials features require a `MaterialFeatureSchema` and preserve atomic versus
mass fractions. CALPHAD requires an explicit TDB path and provenance; a missing
database is `INDETERMINATE`.

## Current host boundary

The validation host has RDKit installed. Cantera, AutoDock Vina, Open Babel,
pymatgen, matminer and pycalphad are not installed/configured, so their real
reference cases are deliberately not reported as executed or validated. The
tests exercise these missing-engine boundaries and tamper detection. No legacy
file under `Biolab/` or `formolecular/` is changed.

## Traceability and comparison

`RunRegistry` indexes engine manifests and supports queries by engine, version,
mechanism hash, database hash, receptor hash and grid hash. Comparison reports
use `ENGINE_CHANGED`, `ENGINE_VERSION_CHANGED`, `MECHANISM_CHANGED`,
`DATABASE_CHANGED`, `RECEPTOR_CHANGED`, `GRID_CHANGED` and `PROTOCOL_CHANGED`,
with the first divergence retained.
