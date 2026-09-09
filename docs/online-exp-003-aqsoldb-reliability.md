# ONLINE-EXP-003 — AqSolDB reliability-stratified external error

Status: **predeclared protocol; results not yet inspected**

## Scientific question

Does the frozen `ONLINE-EXP-001` v2 combined Random Forest show materially different external error across the reliability strata already assigned by the AqSolDB curation process, after applying the exact `ONLINE-EXP-002` structural decontamination policy?

This experiment is a post-validation diagnostic of a frozen model and frozen external dataset view. It is **not** model selection, retraining, calibration, or hyperparameter tuning.

## Parent experiments

- model parent: `research-os.online-exp-001.v2`
- external-validation parent: `research-os.online-exp-002.aqsoldb-external-v1`
- parent model training partition: seed-42 hybrid structural ESOL training partition only
- expected parent training count: `902`
- parent external retained count from EXP-002: `8,863`

The model specification, training partition, decontamination policy, applicability-domain threshold, and AqSolDB source commit remain unchanged.

## Frozen model

- estimator: `RandomForestRegressor`
- representation: eight Research OS RDKit 2D descriptors + Morgan fingerprint
- Morgan radius: `2`
- Morgan bits: `2048`
- `n_estimators = 300`
- `min_samples_leaf = 2`
- `random_state = 42`
- `n_jobs = 1`

No AqSolDB target is used for fitting or tuning.

## Frozen external source

Dataset: AqSolDB

DOI: `10.1038/s41597-019-0151-1`

Source commit: `98cdd10a372058743e4f3fb950a1c9974ec9603a`

Source blob SHA: `67016e030cf0a741e250ba0267bd84461041db5f`

The same immutable `results/data_curated.csv` used by EXP-002 is used here.

## AqSolDB reliability semantics

The AqSolDB curation code assigns `Group`, `Occurrences`, and `SD` before writing the curated dataset. The original implementation defines:

- `G1`: one occurrence; `SD = 0` by construction;
- `G2`: two differing occurrences with absolute difference greater than `1`; selected value chosen by the AqSolDB curation procedure;
- `G3`: two differing occurrences with absolute difference at most `1`;
- `G4`: more than two occurrences with standard deviation greater than `0.5`;
- `G5`: more than two occurrences with standard deviation at most `0.5`.

These labels are treated as **curation strata**, not as a universal ordinal truth about measurement quality. In particular, `G1` has only one occurrence and therefore cannot provide empirical agreement information.

## Frozen decontamination

Before stratified metrics:

1. parse the same AqSolDB source used by EXP-002;
2. preserve `Group`, `Occurrences`, and `SD` metadata for audit only;
3. run the exact EXP-002 structural decontamination against all ESOL canonical structures/InChIKeys;
4. exclude invalid structures fail-closed;
5. exclude all ESOL overlaps before prediction metrics;
6. preserve the EXP-002 deterministic handling of duplicate/conflicting canonical groups;
7. assert that retained record count and retained-dataset hash match EXP-002 expectations before stratification.

Reliability metadata must not influence which structures are retained.

## Predeclared analyses

### 1. Per-group analysis

For each of `G1`, `G2`, `G3`, `G4`, `G5`, report:

- retained `n`;
- MAE;
- RMSE;
- R2;
- target mean / median / standard deviation / range;
- median maximum Tanimoto similarity to the frozen parent training partition;
- in-domain and out-of-domain counts using the inherited EXP-002 threshold.

### 2. Consensus-stratum analysis

Predeclared aggregate strata:

- `single_observation = G1`;
- `repeated_higher_dispersion = G2 + G4`;
- `repeated_lower_dispersion = G3 + G5`.

For each, report the same error and domain diagnostics.

This aggregation is frozen before metrics are inspected.

### 3. Descriptive deltas

Report only descriptive differences:

- RMSE difference between `repeated_higher_dispersion` and `repeated_lower_dispersion`;
- MAE difference between those strata;
- OOD-fraction difference;
- median-similarity difference.

No p-value, significance test, causal claim, or threshold is selected from observed results.

## Interpretation controls

A difference in error between reliability groups can reflect multiple factors, including:

- measurement disagreement represented by AqSolDB curation metadata;
- differing chemical-space coverage;
- target-distribution differences;
- applicability-domain differences;
- source/protocol heterogeneity inherited from the underlying public datasets.

Therefore this experiment may identify **association**, not causation.

No claim will be made that AqSolDB reliability groups are perfectly ordered, that one group is intrinsically trustworthy for every use, or that the model directly measures experimental reliability.

## Reproducibility

The final report must include:

- EXP-002 retained-dataset hash assertion;
- parent training hash;
- source commit/blob SHA;
- reliability-metadata parse hash;
- group counts;
- per-group metrics;
- consensus-stratum metrics;
- inherited AD threshold;
- scientific-result hash;
- execution-environment hash.

## Freeze rule

After the first EXP-003 metrics are produced, changes to grouping definitions, aggregate strata, model specification, parent training data, decontamination policy, or reported metrics require a new protocol version. The first result must not be tuned post hoc.