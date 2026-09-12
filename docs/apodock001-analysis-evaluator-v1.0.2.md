# APODOCK-001 v1.0.2 analysis evaluator

This evaluator is a separate analysis boundary for the frozen APODOCK-001
v1.0.2 protocol. It is intentionally not the historical REDOCK v1.1
evaluator. It may be called only after a future prospective run has produced
and sealed its raw outputs.

## Same-frame metric

For every converted pose, the evaluator removes hydrogens for the analysis
representation, verifies element-labelled heavy-atom connectivity, enumerates
graph-isomorphic atom mappings, and calculates:

```text
sqrt(mean(||predicted_xyz - reference_xyz||²))
```

Coordinates remain in the receptor frame returned by Vina. The evaluator does
not call `GetBestRMS`, `CalcRMS`, `AlignMol`, Kabsch, or any other rigid-body
fitting operation between predicted and reference ligands. The only
optimization is correspondence among symmetry-equivalent graph mappings.

The mapping enumeration cap is exactly `10000`. Reaching the cap is
`INDETERMINATE`; an arbitrary subset is never selected.

The holo-to-apo structural transform is a separate frozen receptor transform.
It is applied only to the crystallographic reference coordinates, never to a
predicted pose. The resulting transformed-reference coordinate hash must match
the protocol before RMSD evaluation proceeds.

## Pose selection and scores

Pose 1 is the first model in the raw Vina PDBQT output. It is always the
primary metric and is never replaced by a lower-RMSD pose. The secondary
metric is the minimum RMSD among the first 20 models in output order; models
after pose 20 do not enter the secondary metric. Vina scores are parsed and
recorded per pose, but never participate in RMSD calculation. Missing or
ambiguous scores are fail-closed as `SCORE_PARSE_FAILED`.

The descriptive success threshold is `2.0 Å`, inclusive. Primary and
secondary denominators are explicit. Arithmetic means and medians use only
determinate cases; indeterminate and failed-execution cases remain in the
complete APD-001…APD-010 vector and are listed as exclusions.

## Raw seal prerequisite

The analyzer requires both `run-manifest.json` and `raw-results-seal.json`.
The run manifest must have `status = RAW_RESULTS_SEALED` and
`raw_results_sealed = true`. All declared raw-output hashes are recalculated
before analysis and checked again after every pose conversion. Any mismatch
blocks analysis with `BLOCKED: raw result seal mismatch`.

Raw PDBQT bytes are never overwritten. Each pose is copied to a derived
`analysis-derived/` path and converted through the declared Open Babel
representation adapter. The derived SDF is the only representation passed to
the evaluator.

## APD-010

APD-010 remains exclusively the frozen `BEM+MAV 1.0.0` adapter contract. The
evaluator does not reconstruct chemistry or fabricate missing experimental
coordinates. If a complete correspondence between the 25-atom BEM+MAV
adapter output and the 24 mapped experimental heavy atoms is unavailable, the
case is retained and reported as `INDETERMINATE` with
`REFERENCE_COORDINATES_INCOMPLETE`.

## Aggregation and provenance

The analysis manifest records the protocol ID/hash, final run ID, raw-results
seal SHA-256, evaluator identity, analysis implementation commit, complete
per-case metrics, first-loss stages, indeterminate cases, and explicit
aggregation denominators. The evaluator identity is separate from the
protocol identity and is derived from its schema, semantics, correspondence
policy, symmetry cap, threshold, and pose-selection rules.

The evaluator is deterministic for the same sealed bytes and explicit
implementation commit. Operational metadata does not change the scientific
case metrics.

This evaluator was frozen before the first APODOCK-001 prospective docking
result was observed.
