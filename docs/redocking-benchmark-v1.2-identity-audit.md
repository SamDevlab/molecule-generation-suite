# REDOCK-001 v1.2 — scientific identity portability audit

## Trigger

The post-merge Research OS CI run 252 reproduced the REDOCK-001 v1.2 scientific observables from run 251 exactly: all five pose-1 RMSDs, Vina scores, pose counts and PASS statuses were unchanged. However, `scientific_result_hash` changed between the two executions.

## Root cause

The v1.2 scientific payload still included SHA-256 values of representation-level SDF files. Those files are not byte-stable across otherwise identical runs:

- RCSB ModelServer SDF responses embed request-specific `job_id`, UTC timestamp and timing metadata;
- Open Babel SDF output embeds a writer timestamp in the molfile header;
- the starting conformer inherited volatile ModelServer properties from the source molecule.

Therefore the byte hashes changed even when molecular coordinates, graph, docking inputs after preparation, Vina output and evaluated RMSDs were unchanged.

## Correction

Representation-only SDF hashes are retained in the full audit report but excluded from `scientific_result_hash`. The scientific identity continues to include stable experimental determinants and outcomes, including:

- frozen protocol and case definitions;
- raw PDB and extracted receptor/native-ligand PDB identities;
- prepared receptor/ligand PDBQT output hashes;
- Vina output and per-pose PDBQT hashes;
- engine versions, grid and frozen parameters;
- statuses, scores, pose counts and same-frame symmetry-aware RMSDs.

No case, receptor chain, ligand, docking parameter, starting-conformer method, search box, RMSD evaluator, symmetry policy, threshold or scientific interpretation was changed.

## Regression protection

Tests now require the scientific hash to remain unchanged when only volatile reference/starting/predicted SDF hashes change, while still changing when stable pose PDBQT content or a material RMSD changes.

This is an identity/provenance correction, not a new docking protocol version.
