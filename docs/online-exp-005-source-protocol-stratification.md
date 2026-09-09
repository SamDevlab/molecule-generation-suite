# ONLINE-EXP-005 — Source/protocol stratification of the AqSolDB reliability-error association

## Status

**Protocol frozen before any ONLINE-EXP-005 error metric is computed or inspected.**

This experiment is stacked on the closed ONLINE-EXP-004 scientific result. It does not modify EXP-001, EXP-002, EXP-003, EXP-004, their datasets, model, hyperparameters, applicability-domain threshold, reliability groups, or previous results.

## Research question

Does the residual higher-vs-lower repeated-measurement dispersion error gap observed in ONLINE-EXP-004 persist when the comparison is additionally standardized within the original AqSolDB source-dataset identity?

This is a descriptive confounder-control experiment. It does not test a causal effect of measurement dispersion.

## Frozen parents

- EXP-004 head parent: `af5aa9940798b13317bcc11f96c37f8dec4dffa5`
- EXP-004 protocol: `research-os.online-exp-004.controlled-confounders-v1`
- EXP-004 scientific result hash: `2427a72653d0adee34e30fa241c1dd416925159ad7b84bdc495f698913e95143`
- retained AqSolDB count: `8863`
- retained external hash: `0c3179ccdeb47b96b0afb3c38f61f6e9b95ab09c3071b18a433e3fb147d9c002`
- reliability metadata hash: `6cfeceee8f06b8e388fb86b172e0d2bb9c2e701002a530761502c543ad87c0a5`
- parent ESOL training count: `902`
- parent ESOL training hash: `300ddc4981e1a9c2fb3735e598bcca89fb98a1cd4722cd58454e5d923781f00b`
- inherited AD threshold: `0.26684684684684684`
- frozen model: `random_forest_combined`
- representation: 8 RDKit descriptors + Morgan radius=2 bits=2048
- hyperparameters: `n_estimators=300`, `min_samples_leaf=2`, `random_state=42`, `n_jobs=1`

## Source/protocol variable

AqSolDB was built by concatenating nine source datasets named `dataset-A.csv` through `dataset-I.csv`. The source identity is preserved in the curated record ID prefix (`A-*` through `I-*`).

EXP-005 therefore defines `source_dataset` deterministically as the single leading letter `A`…`I` before the first `-` in the immutable AqSolDB `ID` field.

Rules:

- accepted source IDs match `^[A-I]-`;
- any retained record that does not map to exactly one source A-I causes fail-closed execution;
- source identity is read only from the frozen AqSolDB record ID;
- no source is merged, dropped, renamed, or regrouped based on observed model error;
- source identity is treated as a coarse proxy for dataset/protocol origin, not as a complete description of experimental conditions.

## Frozen cohorts

Only repeated-observation reliability groups enter the primary comparison:

- higher dispersion: `G2 + G4`
- lower dispersion: `G3 + G5`
- `G1` excluded because a single observation contains no replicate-agreement information.

No reliability-group definition is changed.

## Primary standardization

EXP-005 extends the frozen EXP-004 cell definition by one predeclared dimension: `source_dataset`.

Each primary cell is:

`source_dataset × AD_status × max_train_similarity_bin × measured_logS_bin`

where the inherited frozen dimensions are:

### Applicability-domain status

- `ID`: maximum training similarity >= `0.26684684684684684`
- `OOD`: maximum training similarity < `0.26684684684684684`

### Maximum-train-similarity bins

- `[0.0,0.4)`
- `[0.4,0.6)`
- `[0.6,0.8)`
- `[0.8,1.0]`

### Measured-logS bins

- `(-inf,-6)`
- `[-6,-4)`
- `[-4,-2)`
- `[-2,0)`
- `[0,+inf)`

These boundaries are inherited unchanged from EXP-004.

## Shared-cell and weighting rule

A source-aware cell is included in the primary standardized comparison only when both dispersion cohorts contain at least one record in that exact cell.

For every shared cell `c`:

`w_c = min(n_higher,c, n_lower,c)`

The same `w_c` is used for both cohorts. No record is selected, removed, or weighted using its residual or prediction error.

Primary standardized metrics are:

`controlled_source_MAE_g = sum(w_c * MAE_g,c) / sum(w_c)`

`controlled_source_MSE_g = sum(w_c * MSE_g,c) / sum(w_c)`

`controlled_source_RMSE_g = sqrt(controlled_source_MSE_g)`

Primary descriptive deltas are:

- `controlled_source_RMSE_higher - controlled_source_RMSE_lower`
- `controlled_source_MAE_higher - controlled_source_MAE_lower`

A positive delta means the higher-dispersion cohort retains larger error after this source-aware standardization. A negative delta means the opposite. Exact continuous values are reported without an inferential significance threshold.

R2 is not standardized because pooled R2 is not a linear cell-wise error functional under this weighting scheme.

## Interpretation support boundary

The numerical analysis is always deterministic if at least one shared source-aware cell exists. However, a primary result is labelled **SUPPORTED** only when all predeclared overlap conditions hold:

- total matching support `sum(w_c) >= 50`;
- at least 50% of higher-dispersion repeated records fall in shared source-aware cells;
- at least 50% of lower-dispersion repeated records fall in shared source-aware cells;
- at least two distinct source datasets contribute shared source-aware cells.

If any condition fails, the numerical result is retained but the interpretation status is **INSUFFICIENT_OVERLAP**. Thresholds are frozen here and must not be relaxed after results are seen.

## Coverage diagnostics

Report without changing the primary calculation:

- total repeated-observation count per cohort;
- shared-cell count per cohort;
- shared-cell fraction per cohort;
- number of shared source-aware cells;
- total matching support;
- number and identity of contributing source datasets;
- per-source total repeated counts by cohort;
- per-source shared-cell counts by cohort;
- per-source matching support;
- cell-level source, AD status, similarity bin, measured-logS bin, cohort counts, MAE, MSE, RMSE, and mean signed error.

Coverage diagnostics are interpretation boundaries, not tuning inputs.

## Secondary descriptive source analysis

For each source A-I represented among retained repeated-observation records, report separately and without pooling across sources:

- higher- and lower-dispersion record counts;
- MAE and RMSE for each cohort when present;
- raw within-source higher-minus-lower MAE/RMSE deltas only when both cohorts are present;
- median maximum-train similarity by cohort;
- ID/OOD counts by cohort;
- measured-logS distribution summaries by cohort.

The secondary analysis is diagnostic only. Sources are not ranked as better/worse protocols, and no source is removed from the primary analysis because of these diagnostics.

## Frozen interpretation outcomes

Before seeing results, EXP-005 allows four descriptive outcomes:

1. **positive source-aware delta with SUPPORTED overlap** — a residual positive association remains after the stated source-aware standardization;
2. **near-zero source-aware delta with SUPPORTED overlap** — the residual EXP-004 gap is substantially attenuated under source-aware standardization;
3. **negative source-aware delta with SUPPORTED overlap** — the lower-dispersion cohort has larger standardized error under this design;
4. **INSUFFICIENT_OVERLAP** — source-aware support is too limited under the frozen thresholds for the primary delta to support interpretation.

No numerical threshold for “near zero” is declared. The exact continuous deltas are retained.

## Reproducibility and fail-closed requirements

Before EXP-005 metrics are accepted, execution must confirm unchanged:

- AqSolDB source URL/commit/blob;
- retained external count/hash;
- reliability metadata hash;
- parent ESOL training count/hash;
- applicability-domain threshold;
- frozen model specification;
- source-ID parser accepts only A-I prefixes;
- EXP-001 through EXP-004 scientific identities continue to reproduce in CI.

Any drift causes failure rather than silent adaptation.

## Prohibited post-hoc changes

After the first EXP-005 metrics become visible, do not change within this protocol:

- source extraction rule;
- cohort membership;
- source grouping;
- AD threshold;
- similarity bins;
- measured-logS bins;
- shared-cell rule;
- cell weight;
- overlap thresholds;
- model or hyperparameters;
- dataset curation;
- record inclusion based on residual/error;
- primary metric definition.

Any alternative source grouping, source-specific model, regression adjustment, propensity matching, finer binning, bootstrap, inferential test, or model change is a new experiment/protocol.

## Interpretation limits

EXP-005 remains observational and descriptive. AqSolDB source prefix is only a dataset-origin proxy and does not encode every experimental protocol, laboratory, temperature, pH, assay method, ionization state, or measurement condition.

A residual gap after source-aware standardization does not prove that measurement dispersion causes model error. A reduced gap does not prove that source/protocol differences caused the removed portion.

No p-value, causal claim, significance threshold, tuning on external targets, or post-hoc record removal is authorized by this protocol.
