# ONLINE-EXP-004 — Controlled reliability-stratum error on AqSolDB

Status: **closed; first controlled result retained without post-hoc tuning**

## Scientific question

After the frozen `ONLINE-EXP-003` observation that repeated higher-dispersion AqSolDB records (`G2 + G4`) have larger external prediction error than repeated lower-dispersion records (`G3 + G5`), does that error difference remain when the two aggregates are standardized over the same structural-domain, similarity, and measured-logS strata?

This experiment is a descriptive confounder-control analysis of a frozen model and frozen external dataset. It is **not** retraining, calibration, model selection, feature selection, threshold tuning, causal inference, or a new external validation.

## Parent experiments and immutable inputs

- model parent: `research-os.online-exp-001.v2`
- external-validation parent: `research-os.online-exp-002.aqsoldb-external-v1`
- reliability parent: `research-os.online-exp-003.aqsoldb-reliability-v1`
- parent model: `random_forest_combined`
- parent seed: `42`
- parent training count: `902`
- parent training hash: `300ddc4981e1a9c2fb3735e598bcca89fb98a1cd4722cd58454e5d923781f00b`
- retained AqSolDB count: `8,863`
- retained AqSolDB hash: `0c3179ccdeb47b96b0afb3c38f61f6e9b95ab09c3071b18a433e3fb147d9c002`
- reliability metadata hash: `6cfeceee8f06b8e388fb86b172e0d2bb9c2e701002a530761502c543ad87c0a5`
- inherited applicability-domain threshold: `0.26684684684684684`
- AqSolDB source commit: `98cdd10a372058743e4f3fb950a1c9974ec9603a`
- AqSolDB source blob SHA: `67016e030cf0a741e250ba0267bd84461041db5f`

All parent hashes and counts are fail-closed assertions. If any parent identity drifts, EXP-004 must stop before producing controlled metrics.

## Frozen model

The model specification is inherited unchanged from EXP-001 v2 / EXP-002 / EXP-003:

- `RandomForestRegressor`
- eight Research OS RDKit 2D descriptors + Morgan fingerprint
- Morgan radius `2`
- Morgan bits `2048`
- `n_estimators = 300`
- `min_samples_leaf = 2`
- `random_state = 42`
- `n_jobs = 1`

No AqSolDB target participates in fitting or model tuning.

## Cohorts

Only records with repeated observations are eligible for the primary controlled comparison:

- `higher_dispersion = G2 + G4`
- `lower_dispersion = G3 + G5`

`G1` is excluded from the controlled comparison because it has only a single observation and therefore no replicate-agreement information.

No record is removed because of its prediction error.

## Predeclared confounder strata

Each eligible retained AqSolDB record is assigned deterministically to one cell defined by all three dimensions below.

### 1. Applicability-domain status

Using the inherited frozen threshold `0.26684684684684684`:

- `OOD`: maximum train similarity `< threshold`
- `ID`: maximum train similarity `>= threshold`

### 2. Maximum-train-similarity bin

Fixed bins inherited from the prior solubility diagnostics:

- `[0.0, 0.4)`
- `[0.4, 0.6)`
- `[0.6, 0.8)`
- `[0.8, 1.0]`

The final bin includes `1.0`.

### 3. Measured-logS bin

Fixed two-log-unit target strata:

- `(-inf, -6)`
- `[-6, -4)`
- `[-4, -2)`
- `[-2, 0)`
- `[0, +inf)`

These boundaries were frozen before EXP-004 controlled metrics were computed and were not changed after the first result.

## Shared-cell rule

A cell is eligible for standardization only when it contains at least one `higher_dispersion` record and at least one `lower_dispersion` record.

No minimum cell size beyond one record per cohort is imposed. Small cells therefore remain auditable instead of being removed by a result-dependent support threshold.

For each shared cell `c`:

- `n_high,c` = higher-dispersion count
- `n_low,c` = lower-dispersion count
- matching support weight `w_c = min(n_high,c, n_low,c)`

The weight is based only on cohort support, not on prediction error.

## Predeclared controlled metrics

For each cohort and each shared cell, compute:

- MAE
- MSE
- RMSE
- mean signed error as a diagnostic only
- record count

The primary standardized metrics use the same shared-cell weights for both cohorts:

`controlled_MAE_g = sum(w_c * MAE_g,c) / sum(w_c)`

`controlled_MSE_g = sum(w_c * MSE_g,c) / sum(w_c)`

`controlled_RMSE_g = sqrt(controlled_MSE_g)`

Primary descriptive deltas are:

- `controlled_RMSE_higher - controlled_RMSE_lower`
- `controlled_MAE_higher - controlled_MAE_lower`

A positive delta means the higher-dispersion cohort retains larger error after standardization over the predeclared shared cells.

R2 is not standardized because pooled R2 is not a linear cell-wise error functional and would be easy to misinterpret under this weighting scheme.

## Coverage diagnostics

EXP-004 reports, without changing the primary calculation:

- total repeated-observation count per cohort;
- count per cohort falling inside shared cells;
- fraction per cohort falling inside shared cells;
- number of shared cells;
- total matching support `sum(w_c)`;
- cell-level cohort counts and metrics;
- cell AD status, similarity bin, and measured-logS bin.

Coverage diagnostics are interpretation boundaries, not tuning inputs.

## Interpretation rule frozen before results

Three possible descriptive outcomes were predeclared:

1. **positive controlled delta** — higher-dispersion records remain harder after the stated standardization;
2. **near-zero controlled delta** — the raw EXP-003 gap is largely explained by the controlled structural/target distribution differences under this coarsened design;
3. **negative controlled delta** — after standardization, lower-dispersion records have larger error under this coarsened design.

No numerical threshold for “near zero” was declared. The exact continuous deltas are reported rather than converted into a binary significance claim.

## First execution — GitHub Actions run 203

The first valid EXP-004 execution was GitHub Actions run `34396580121` on implementation commit `e99cff081b0832781e203df4c060d76dfec6011a`.

Validation before the new result:

- focused solubility suite: `39 passed`
- core Python 3.11: PASS
- core Python 3.12: PASS
- Cantera reference: PASS
- ONLINE-EXP-001 v1: PASS
- ONLINE-EXP-001 multi-seed: PASS
- ONLINE-EXP-001 v2: PASS
- ONLINE-EXP-001 v2 closure: PASS
- ONLINE-EXP-002: PASS with unchanged scientific identity
- ONLINE-EXP-003: PASS with unchanged scientific identity
- ONLINE-EXP-004: PASS

No EXP-004 metric was inspected before the protocol-freeze commit `aa95438566a382280cbbaeba3118d261fe11347e`.

## Observed coverage

| Coverage item | Higher dispersion | Lower dispersion |
|---|---:|---:|
| Total repeated-observation records | 345 | 1,223 |
| Records in shared cells | 345 | 1,214 |
| Shared-cell fraction | 100.00% | 99.26% |

Additional support diagnostics:

- shared cells: `22`
- total matching support `sum(w_c)`: `330`

The high coverage means the controlled result is not driven by discarding most of either repeated-observation cohort. Nine lower-dispersion records fall outside shared support; all 345 higher-dispersion records fall inside shared cells.

## Primary controlled result

| Metric | Higher dispersion | Lower dispersion | Higher - lower |
|---|---:|---:|---:|
| MAE | 1.3282 | 1.0115 | **+0.3167** |
| RMSE | 1.9476 | 1.4812 | **+0.4664** |

Exact values:

- controlled higher-dispersion MAE: `1.3281807318031669`
- controlled lower-dispersion MAE: `1.0114855696331642`
- controlled MAE delta: `+0.3166951621700027`
- controlled higher-dispersion RMSE: `1.9476321808548787`
- controlled lower-dispersion RMSE: `1.4812381736685765`
- controlled RMSE delta: `+0.4663940071863022`

For context, EXP-003's uncontrolled repeated-stratum RMSE delta was `+0.8541281588526171`. The predeclared control therefore reduces the observed gap substantially, but does not reverse it or reduce it to zero.

The controlled RMSE delta is about 54.6% of the raw EXP-003 RMSE delta. This ratio is descriptive only; it is not a causal decomposition or a percentage of error “explained.”

## Cell-level pattern

The sign of the difference is not uniform across all 22 shared cells. Several in-domain cells are near zero or favor the higher-dispersion cohort, while some low-similarity OOD cells retain large positive differences.

Examples retained exactly as observed:

| AD | Similarity | measured logS | High n | Low n | RMSE high | RMSE low | Delta |
|---|---|---|---:|---:|---:|---:|---:|
| OOD | `[0.0,0.4)` | `[-6,-4)` | 49 | 42 | 3.4204 | 2.0704 | **+1.3499** |
| OOD | `[0.0,0.4)` | `[-4,-2)` | 21 | 63 | 1.9766 | 1.2048 | **+0.7717** |
| OOD | `[0.0,0.4)` | `(-inf,-6)` | 18 | 11 | 4.0915 | 3.3569 | **+0.7346** |
| ID | `[0.4,0.6)` | `[-6,-4)` | 32 | 62 | 0.8982 | 1.0157 | **-0.1175** |
| ID | `[0.4,0.6)` | `[-4,-2)` | 25 | 140 | 0.7369 | 0.9071 | **-0.1702** |

These cell-level differences are descriptive diagnostics. They do not authorize a post-hoc redefinition of the primary comparison.

## Interpretation

The first EXP-004 result matches the predeclared **positive controlled delta** outcome: repeated higher-dispersion AqSolDB records remain harder for the frozen model after deterministic standardization over applicability-domain status, maximum-train-similarity bins, and measured-logS bins.

However, the reduction from the raw RMSE gap of `+0.8541` to a controlled gap of `+0.4664` indicates that structural/domain and target-distribution imbalance materially contributed to the EXP-003 association.

The remaining positive gap is evidence of a residual association under this specific coarsened control design. It is **not** evidence that measurement dispersion alone causes model error. Source-specific protocols, chemistry within bins, measurement conditions, assay methodology, and other unobserved variables can still confound the comparison.

The especially large differences in several low-similarity OOD cells also reinforce the existing applicability-domain boundary: this experiment does not make predictions outside the learned chemical domain more trustworthy.

## Explicit limitations

This protocol does not establish causality. Residual confounding can remain because AqSolDB aggregates heterogeneous experimental sources and because coarse bins cannot balance every chemical or protocol variable.

In particular, EXP-004 does not claim that:

- AqSolDB dispersion group causes prediction error;
- the chosen cells produce exchangeable cohorts;
- measurement SD is a calibrated uncertainty target;
- the observed gap is statistically significant;
- the ratio between controlled and raw gaps is a causal fraction explained;
- the result generalizes to another dataset;
- the model becomes safe for generated or unseen chemistry outside its applicability domain.

No p-value, significance test, bootstrap-derived decision threshold, model tuning, post-hoc bin change, or record removal based on residual/error was performed.

## Reproducibility

First execution identities:

- protocol-freeze commit: `aa95438566a382280cbbaeba3118d261fe11347e`
- implementation commit: `e99cff081b0832781e203df4c060d76dfec6011a`
- GitHub Actions run: `34396580121` (`run 203`)
- reliability metadata hash: `6cfeceee8f06b8e388fb86b172e0d2bb9c2e701002a530761502c543ad87c0a5`
- retained external hash: `0c3179ccdeb47b96b0afb3c38f61f6e9b95ab09c3071b18a433e3fb147d9c002`
- parent training hash: `300ddc4981e1a9c2fb3735e598bcca89fb98a1cd4722cd58454e5d923781f00b`
- report hash: `f5f0bc3267dfe207e04cea6709c47dc90ac9794b51abe4aaddc0aabeb73cc709`
- scientific result hash: `2427a72653d0adee34e30fa241c1dd416925159ad7b84bdc495f698913e95143`
- execution hash: `8a5ab7f7841de0f38eb22316fd106b2e8f64f31aa72c0954a0a4c02865ed3a52`

Run-203 environment:

- CPython `3.12.14`
- NumPy `2.5.3`
- RDKit `2026.03.6`
- scikit-learn `1.9.0`
- Linux x86_64 GitHub Actions runner

Parent scientific-result hashes repeated unchanged before EXP-004:

- EXP-001 v1: `962ede85e64c0f84c9bb3788d2d561124eec74805e2d5ca66ad5f1e5d9aee8d9`
- EXP-001 multi-seed: `736da31970423b47a6eef00a60c682d3db1d03004182df214dfb2fca64c85c30`
- EXP-001 v2: `790dd3bc820bd5a7756abec3049e037ab55e3a47068acf91d71cb59d4cdbe815`
- EXP-001 v2 closure: `16a5d5813b696e463e8d3c412f0625ed492da01002cd03805ba53f6762b90e9a`
- EXP-002: `2bcd795284143f73c1207f9c0a20fdd2272b5fb05cccbb3ac5da7d25e5e44057`
- EXP-003: `eeca8e4f2c7006791913745204d7e7129e25d0f6a1a56dd67487ae4456b4347a`

## Closure

ONLINE-EXP-004 is closed. The first controlled result is retained without post-hoc changes to the model, cohorts, applicability-domain threshold, similarity bins, measured-logS bins, shared-cell rule, or weighting rule.

Any alternative matching method, finer binning, regression adjustment, propensity score, bootstrap, inferential test, source-specific analysis, or model modification is a new experiment/protocol rather than an edit to EXP-004 after results became visible.
