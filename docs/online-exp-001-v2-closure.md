# ONLINE-EXP-001 v2 closure

Status: accepted closure analysis for the draft ONLINE-EXP-001 branch.

## Protocols

- Parent: `research-os.online-exp-001.v2`
- Robustness: `research-os.online-exp-001.v2.robustness-v1`
- Dataset sensitivity: `research-os.online-exp-001.v2.unique-nonconflicting-v1`
- Seeds: `7, 21, 42, 84, 101`

The accepted v2 model specification is unchanged. No seed-specific tuning is performed. Descriptor ablation is not repeated in the closure because the closure targets split/domain robustness rather than feature selection.

## Multi-seed robustness

Combined RF (`descriptors + Morgan`) under hybrid structural holdout:

| Metric | Mean | SD | Min | Max |
|---|---:|---:|---:|---:|
| Test MAE | 0.586 | 0.073 | 0.481 | 0.662 |
| Test RMSE | 0.803 | 0.113 | 0.672 | 0.964 |
| Test R2 | 0.859 | 0.031 | 0.822 | 0.893 |
| AD threshold | 0.2648 | 0.0085 | 0.2500 | 0.2703 |
| OOD count | 6.0 | 2.74 | 2 | 9 |
| In-domain RMSE | 0.790 | 0.090 | 0.678 | 0.900 |
| OOD RMSE | 0.890 | 0.503 | 0.524 | 1.745 |

Robustness report hash:

`773095ddb1aa011a8d17f4231727fb5e26a879d2d9f6a1ef4d17f5c5611d03a3`

### Interpretation

The combined RF test performance and the applicability-domain threshold are reasonably stable across the five fixed seeds. The threshold-defined OOD subset is not stable enough to support a strong claim that OOD error is always higher: only 2–9 test molecules are classified OOD per seed, and OOD RMSE has high dispersion.

Accordingly, the seed-42 observation (`OOD RMSE 1.745` versus `ID RMSE 0.900`) is retained as a real run result but is no longer treated as a robust general statement.

A pooled descriptive view across the five runs gives the following similarity-band behavior:

| Max train Tanimoto | Pooled n | Pooled MAE | Pooled RMSE |
|---|---:|---:|---:|
| [0.0, 0.4) | 128 | 0.595 | 0.837 |
| [0.4, 0.6) | 348 | 0.610 | 0.842 |
| [0.6, 0.8) | 61 | 0.465 | 0.583 |
| [0.8, 1.0] | 28 | 0.505 | 0.679 |

This supports a weaker and more defensible statement: molecules with maximum training similarity at or above roughly `0.6` show lower pooled error in this benchmark than the less-similar groups. The highest-similarity bin remains small and is not strictly monotonic.

## Dataset sensitivity

The ESOL audit found 11 duplicate structure groups, including 6 groups with conflicting measured targets.

The sensitivity view applies the following deterministic policy:

- conflicting target groups: exclude the entire canonical-structure group;
- same-target duplicates: retain one deterministic source row;
- no averaging;
- no target imputation.

Resulting view:

- source records: 1128
- source unique structures: 1117
- conflicting structure groups excluded: 6
- conflicting records excluded: 12
- same-target duplicate groups collapsed: 5
- redundant same-target rows collapsed: 5
- kept records: 1111
- lineage hash: `8ac09ca1628aa3829224da3196c35d53b9026628e218866d8d163460af6d2b4b`
- curated dataset hash: `184d5ecbe80bc6c7ddbd8dfcaaf321ffe93ceeec420a0392c376d22d212f6e38`

Seed-42 combined RF comparison:

| Metric | Original ESOL | Unique non-conflicting | Delta |
|---|---:|---:|---:|
| Test MAE | 0.662 | 0.557 | -0.106 |
| Test RMSE | 0.964 | 0.784 | -0.180 |
| Test R2 | 0.822 | 0.838 | +0.017 |
| AD threshold | 0.26685 | 0.26667 | -0.00018 |
| OOD count | 6 | 10 | +4 |
| ID RMSE | 0.900 | 0.773 | -0.126 |
| OOD RMSE | 1.745 | 0.884 | -0.861 |

Sensitivity report hash:

`411424384fee2fb057824f3d9f89fee5dc834d3bc2ac409d07c8be948b5d00ab`

The sensitivity analysis improves seed-42 error materially, which means duplicate/conflicting measurements and the changed partition composition are not negligible. This curated view is a sensitivity analysis only; it does not retroactively replace the accepted source-dataset v2 result.

## Closure conclusion

ONLINE-EXP-001 supports the following claims within its stated boundary:

1. Simple 2D physicochemical descriptors carry substantial predictive signal for ESOL.
2. Morgan fingerprints alone are weaker than descriptor-based RF under the frozen protocol.
3. Descriptors + Morgan provide a modest improvement over descriptors alone in the accepted seed-42 v2 run.
4. Hybrid structural holdout is materially harder and more informative than an easy random split.
5. The combined RF remains reasonably stable across five hybrid-split seeds (`RMSE 0.803 ± 0.113`).
6. The training-derived AD threshold is stable (`0.2648 ± 0.0085`), but the binary OOD subset is too small to support a stable OOD-error estimate.
7. A broader similarity analysis suggests lower error above approximately 0.6 maximum Tanimoto similarity, but the relationship is not strictly monotonic.
8. Duplicate/conflicting measured targets materially affect the benchmark and must be handled explicitly in future external validation.

The next experiment should therefore be external validation on a decontaminated dataset, with overlap removal and lineage recorded before inference.
