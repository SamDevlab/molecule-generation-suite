# ONLINE-EXP-004 — Controlled reliability-stratum error on AqSolDB

Status: **protocol frozen; no EXP-004 result inspected at freeze time**

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

These boundaries are frozen before EXP-004 controlled metrics are computed and must not be changed in response to observed results.

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

EXP-004 must report, without changing the primary calculation:

- total repeated-observation count per cohort;
- count per cohort falling inside shared cells;
- fraction per cohort falling inside shared cells;
- number of shared cells;
- total matching support `sum(w_c)`;
- cell-level cohort counts and metrics;
- cell AD status, similarity bin, and measured-logS bin.

Coverage diagnostics are interpretation boundaries, not tuning inputs.

## Interpretation rule frozen before results

Three possible descriptive outcomes are predeclared:

1. **positive controlled delta** — higher-dispersion records remain harder after the stated standardization;
2. **near-zero controlled delta** — the raw EXP-003 gap is largely explained by the controlled structural/target distribution differences under this coarsened design;
3. **negative controlled delta** — after standardization, lower-dispersion records have larger error under this coarsened design.

No numerical threshold for “near zero” is declared. The exact continuous deltas must be reported rather than converted into a binary significance claim.

## Explicit limitations

This protocol does not establish causality. Residual confounding can remain because AqSolDB aggregates heterogeneous experimental sources and because coarse bins cannot balance every chemical or protocol variable.

In particular, EXP-004 does not claim that:

- AqSolDB dispersion group causes prediction error;
- the chosen cells produce exchangeable cohorts;
- measurement SD is a calibrated uncertainty target;
- the result generalizes to another dataset;
- the model becomes safe for generated or unseen chemistry outside its applicability domain.

No p-value, significance test, bootstrap-derived decision threshold, model tuning, post-hoc bin change, or record removal based on residual/error is permitted in this experiment.

## Closure condition

After the first successful execution, record exactly the observed controlled metrics, coverage, report hash, scientific-result hash, execution environment, and interpretation boundaries in this document and in the stacked draft PR.

Any alternative matching method, different binning, regression adjustment, propensity score, bootstrap, inferential test, or model modification must be a new experiment/protocol rather than an edit to EXP-004 after results are visible.
