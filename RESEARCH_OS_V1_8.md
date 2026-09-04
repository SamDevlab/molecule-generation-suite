# Research OS v1.8 — Legacy Migration & Parity

v1.8 inventories the preserved legacy trees without editing them. The scanner
records component kind, path, size, hash, migration status, risk flags and
uncertain provenance for scripts, datasets, models, configs, structures,
outputs and reports. It detects hardcoded paths, external-engine calls,
heuristics, synthetic feedback, R² overclaims and Alzheimer-related text.

Legacy flows remain `MIGRATING`; deterministic descriptor calculations are
`REPLACED` only for the explicitly declared RDKit descriptor scope. The
aerospace Isp-like target stays `HEURISTIC_REVIEW`, and historical datasets/
models default to `eligible_for_training=false` in quarantine. `Biolab/` and
`formolecular/` are preserved for audit and no destructive retirement is
claimed.

