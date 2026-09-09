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

## First execution — GitHub Actions run 206

The first valid EXP-005 execution was GitHub Actions run `34400289332` on implementation commit `c4d7fd8cf5604386d38dceea78bebf7e5f98d49c`.

Validation before the new result:

- focused solubility suite: `46 passed`
- core Python 3.11: PASS
- core Python 3.12: PASS
- Cantera reference: PASS
- ONLINE-EXP-001 v1: PASS with unchanged scientific identity
- ONLINE-EXP-001 multi-seed: PASS with unchanged scientific identity
- ONLINE-EXP-001 v2: PASS with unchanged scientific identity
- ONLINE-EXP-001 v2 closure: PASS with unchanged scientific identity
- ONLINE-EXP-002: PASS with unchanged scientific identity
- ONLINE-EXP-003: PASS with unchanged scientific identity
- ONLINE-EXP-004: PASS with unchanged scientific identity
- ONLINE-EXP-005: PASS

No EXP-005 error metric was inspected before the protocol-freeze commit `e7ba6cb09cd10f717d6221485d10bc533082841b`.

## Observed source-aware coverage

| Coverage item | Higher dispersion | Lower dispersion |
|---|---:|---:|
| Total repeated-observation records | 345 | 1,223 |
| Records in shared source-aware cells | 338 | 1,075 |
| Shared-cell fraction | 97.97% | 87.90% |

Additional frozen-support diagnostics:

- shared source-aware cells: `68`
- total matching support `sum(w_c)`: `312`
- contributing sources: `A, B, C, D, E, F, I` (`7` sources)
- interpretation status: **SUPPORTED**

All predeclared support conditions passed: matching support is above `50`, both cohort coverage fractions are above `0.50`, and more than two source datasets contribute.

### Source contribution to shared support

| Source | High total | Low total | High shared | Low shared | Matching support | Shared cells |
|---|---:|---:|---:|---:|---:|---:|
| A | 234 | 649 | 231 | 642 | 207 | 21 |
| B | 55 | 284 | 55 | 282 | 55 | 19 |
| C | 26 | 133 | 26 | 86 | 25 | 11 |
| D | 7 | 42 | 5 | 10 | 5 | 5 |
| E | 3 | 45 | 3 | 19 | 3 | 3 |
| F | 16 | 41 | 15 | 29 | 14 | 6 |
| H | 1 | 17 | 0 | 0 | 0 | 0 |
| I | 3 | 12 | 3 | 7 | 3 | 3 |

Source `G` has no repeated-observation record in the EXP-005 cohorts. Source `H` has repeated records but no shared source-aware cell and therefore contributes no primary matching support.

Source `A` contributes `207/312` of total matching support. This concentration is an interpretation limitation even though the predeclared overlap criteria are satisfied; the primary result must not be described as uniform across source datasets.

## Primary source-aware controlled result

| Metric | Higher dispersion | Lower dispersion | Higher - lower |
|---|---:|---:|---:|
| MAE | 1.3030 | 1.0435 | **+0.2595** |
| RMSE | 1.9102 | 1.5359 | **+0.3743** |

Exact values:

- source-aware higher-dispersion MAE: `1.3030498429933037`
- source-aware lower-dispersion MAE: `1.043528950541642`
- source-aware MAE delta: `+0.25952089245166166`
- source-aware higher-dispersion RMSE: `1.9102130199057479`
- source-aware lower-dispersion RMSE: `1.535935484444603`
- source-aware RMSE delta: `+0.37427753546114495`

For context, the sequence of descriptive RMSE gaps is:

| Experiment | Control level | Higher - lower RMSE gap |
|---|---|---:|
| EXP-003 | repeated reliability strata, uncontrolled | `+0.8541281588526171` |
| EXP-004 | + AD status, similarity bin, measured-logS bin | `+0.4663940071863022` |
| EXP-005 | + immutable AqSolDB source identity | `+0.37427753546114495` |

Adding source identity reduces the EXP-004 residual RMSE gap by `0.09211647172515725`, approximately `19.75%` relative to the EXP-004 residual. The EXP-005 gap is approximately `43.82%` of the original EXP-003 raw gap.

These ratios are descriptive only. They are not causal variance decomposition, percentages of error explained, or estimates of a source effect.

## Secondary per-source pattern

Raw within-source RMSE deltas are heterogeneous:

| Source | Raw RMSE high - low |
|---|---:|
| A | `+0.9828779131221446` |
| B | `+0.05939493117834316` |
| C | `+0.17466829058723` |
| D | `+0.24984912808134874` |
| E | `-0.0037597029645295432` |
| F | `+0.06320914620539342` |
| H | `-0.30621773158535204` |
| I | `-0.17517265152202088` |

These are secondary raw diagnostics, not the primary standardized result. Their mixed signs reinforce that the association is not uniform across source datasets. In particular, source `A` has both the largest matching-support contribution and a large positive raw within-source gap, while several smaller sources are near zero or negative.

No source was removed, regrouped, reweighted by error, or promoted to a separate model after these values became visible.

## Interpretation

The first EXP-005 result matches the predeclared **positive source-aware delta with SUPPORTED overlap** outcome: the higher-dispersion repeated-observation cohort retains larger error after the frozen EXP-004 control is additionally stratified by immutable AqSolDB source identity.

The reduction from `+0.4664` in EXP-004 to `+0.3743` in EXP-005 indicates that source-dataset imbalance contributes additional descriptive confounding beyond the structural/domain and target-range imbalance already addressed by EXP-004.

However, the residual positive gap does **not** establish that measurement dispersion causes prediction error. The source prefix is only a coarse dataset-origin proxy. It does not recover laboratory, assay method, pH, temperature, ionization state, solvent conditions, measurement technique, publication-specific protocol, or chemistry differences that remain within each coarse cell.

The strong concentration of matching support in source `A` and the mixed signs of secondary source-specific deltas are especially important boundaries. The result is supported under the frozen overlap rules, but it is not a claim that every AqSolDB source exhibits the same relationship.

## Reproducibility

First execution identities:

- protocol-freeze commit: `e7ba6cb09cd10f717d6221485d10bc533082841b`
- implementation commit: `c4d7fd8cf5604386d38dceea78bebf7e5f98d49c`
- GitHub Actions run: `34400289332` (`run 206`)
- parent EXP-004 report hash: `f5f0bc3267dfe207e04cea6709c47dc90ac9794b51abe4aaddc0aabeb73cc709`
- parent EXP-004 scientific result hash: `2427a72653d0adee34e30fa241c1dd416925159ad7b84bdc495f698913e95143`
- reliability metadata hash: `6cfeceee8f06b8e388fb86b172e0d2bb9c2e701002a530761502c543ad87c0a5`
- retained external hash: `0c3179ccdeb47b96b0afb3c38f61f6e9b95ab09c3071b18a433e3fb147d9c002`
- parent training hash: `300ddc4981e1a9c2fb3735e598bcca89fb98a1cd4722cd58454e5d923781f00b`
- EXP-005 report hash: `12ed0f59ac929a3eaed1be0faa55fceb09273fdf1f3f46088ebe7f3475eb4007`
- EXP-005 scientific result hash: `3516c82f572e119c11b0033738d408dda5c11fdda6717656de83c76f222a003e`
- EXP-005 execution hash: `ad238d8af6651830e700e2880037e72d7d3bb5b99b0fc4a4d71444a03725c82b`

Run-206 environment:

- CPython `3.12.14`
- NumPy `2.5.3`
- RDKit `2026.03.6`
- scikit-learn `1.9.0`
- Linux x86_64 GitHub Actions runner

Parent scientific-result hashes repeated unchanged before EXP-005:

- EXP-001 v1: `962ede85e64c0f84c9bb3788d2d561124eec74805e2d5ca66ad5f1e5d9aee8d9`
- EXP-001 multi-seed: `736da31970423b47a6eef00a60c682d3db1d03004182df214dfb2fca64c85c30`
- EXP-001 v2: `790dd3bc820bd5a7756abec3049e037ab55e3a47068acf91d71cb59d4cdbe815`
- EXP-001 v2 closure: `16a5d5813b696e463e8d3c412f0625ed492da01002cd03805ba53f6762b90e9a`
- EXP-002: `2bcd795284143f73c1207f9c0a20fdd2272b5fb05cccbb3ac5da7d25e5e44057`
- EXP-003: `eeca8e4f2c7006791913745204d7e7129e25d0f6a1a56dd67487ae4456b4347a`
- EXP-004: `2427a72653d0adee34e30fa241c1dd416925159ad7b84bdc495f698913e95143`

## Closure

ONLINE-EXP-005 is closed. The first source-aware result is retained without post-hoc changes to the model, cohorts, source extraction rule, source grouping, applicability-domain threshold, similarity bins, measured-logS bins, shared-cell rule, weighting rule, or overlap thresholds.

Any alternative source grouping, source-specific fitting, publication-level stratification, protocol-condition extraction, finer matching, regression adjustment, bootstrap, inferential test, or model modification is a new experiment/protocol rather than an edit to EXP-005 after results became visible.
