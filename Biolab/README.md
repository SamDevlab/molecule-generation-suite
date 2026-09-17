# Biolab — legacy exploratory workflows

`Biolab/` is preserved as historical research material from the pre–Research OS codebase. It is **not** the canonical execution layer of Research OS 5.1 and its raw script outputs must not be interpreted as validated scientific evidence.

## Status

- historical docking/screening logic: preserved for audit and migration;
- machine-local executable assumptions: legacy behavior, not the supported Research OS runtime contract;
- docking scores: computational screening values only;
- heuristic selectivity/toxicity labels: exploratory labels only, not measured safety or pharmacology;
- legacy ML helpers: exploratory surrogates unless a held-out protocol is explicitly recorded.

The supported docking architecture lives under `src/research_os/docking/` and `src/research_os/engines/`, where engine availability, hashes, protocol metadata, gates and evidence boundaries are explicit and fail closed.

## Do not infer

A Vina score, docking-derived `Ki`, heuristic off-target label, or legacy ranking does **not** establish measured affinity, inhibition, efficacy, toxicity, clinical relevance or regulatory suitability.

## Migration direction

The next validation target for the docking line is a reproducible **redocking benchmark** against experimentally resolved complexes. The primary metric will be heavy-atom pose RMSD against the crystallographic ligand, with the protocol frozen before execution. A conventional `RMSD <= 2 Å` success summary may be reported descriptively, but the full distribution and per-complex provenance must also be retained.

Until a legacy workflow is migrated behind Research OS gates, treat it as exploratory/audit-only code.
