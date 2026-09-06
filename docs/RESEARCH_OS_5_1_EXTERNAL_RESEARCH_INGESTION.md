# Research OS 5.1 external research ingestion

This is a pre-release implementation record for the product gaps exposed by
`REAL-USE-001-COX2-CROSS-STRUCTURE`. It does not replace the historical
blocked run and does not assert a new cross-structure scientific result.

## Canonical source intake

`research_os.external_research.ExternalResearchIntake` is the single intake
boundary for externally supplied research artifacts. It records:

- path-safe stable source ID and explicit URI;
- canonical `SourceType` and provenance metadata;
- local content SHA-256 when an artifact is available;
- deterministic source fingerprint;
- append-only integration with the existing `SourceRegistry`;
- idempotent re-registration of the same source identity;
- `SOURCE_CHANGED` when an existing identity conflicts, without overwriting
  the canonical registry record.

Remote retrieval is intentionally separate from registration. The typed
availability codes preserve `HTTP_403`, `HTTP_404`, `HTTP_429`, `HTTP_5XX`,
`TIMEOUT`, `DNS_FAILURE`, local hash mismatch, missing artifact, and
not-comparable conditions.

## Structure parser and ligand identity

The parser uses the Gemmi scientific mmCIF implementation, constrained to
`gemmi>=0.7.5,<0.8`, and emits a normalized representation containing:

- entry ID and parser version;
- source path and source SHA-256;
- model and chain identity;
- canonical atom names, elements, coordinates, residue and entity identity;
- revision dates and reported resolution when present.

Ligand extraction requires an explicit component and rejects an ambiguous
chain/instance selection. The 5KIR and 5IKR official mmCIF artifacts are
stored as deterministic test fixtures with their original SHA-256 values:

| Entry | SHA-256 |
|---|---|
| 5KIR | `927fb3eb69423db63849eb15842dc475172964f1bbdb63ac97eacf4867c54243` |
| 5IKR | `a4a20672b28f87d32a4cdff8ae7dbdbe4c94af40bc86d4b7caf0122d860cf472` |

No network access is performed by the parser. A registered source can be
required at the call boundary, and a changed local artifact fails with an
explicit hash mismatch.

## Pose recovery and RMSD

`research_os.docking.pose_recovery` requires ligand identity, element
identity, and a deterministic atom map. Unique atom names map directly.
Symmetry alternatives are enumerated only when a chemical caller declares the
symmetry group; no favorable RMSD is allowed to invent a map. Search limits,
mapping method, raw RMSD, aligned RMSD, and diagnostics are returned together.
Ambiguous mappings are `INDETERMINATE`, not silently selected.

The result is a computational diagnostic. It cannot create Evidence and its
declared evidence ceiling is `E2_COMPUTATIONAL`.

## Engines and docking contract

The existing argv-based `VinaEngine` and `OpenBabelEngine` remain the only
external adapters. The new registry records adapter names and capabilities;
`EnginePreflight` verifies the signed manifest, adapter registration, declared
capability, and runtime availability before execution. A missing executable
returns a typed non-ready result and cannot be treated as an executed run.

`DockingExecutionContract` now binds protocol ID, engine ID, paths, grid,
seed, exhaustiveness, CPU, modes, timeout, target identity, source/hash
metadata when available, and a fixed `E2_COMPUTATIONAL` ceiling. It rejects
invalid limits, malformed hashes, and any attempted evidence ceiling above E2.

## Safety boundary

No new evidence level, additive evidence promotion, clinical interpretation,
silent receptor substitution, silent source substitution, or Live Acceptance
is introduced by this branch.
