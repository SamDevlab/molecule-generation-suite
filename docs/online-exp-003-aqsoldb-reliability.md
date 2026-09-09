# ONLINE-EXP-003 — AqSolDB reliability-stratified external error

Status: **closed; first predeclared result preserved**

## Scientific question

Does the frozen `ONLINE-EXP-001` v2 combined Random Forest show materially different external error across the reliability strata already assigned by the AqSolDB curation process, after applying the exact `ONLINE-EXP-002` structural decontamination policy?

This experiment is a post-validation diagnostic of a frozen model and frozen external dataset view. It is **not** model selection, retraining, calibration, or hyperparameter tuning.

## Parent experiments

- model parent: `research-os.online-exp-001.v2`
- external-validation parent: `research-os.online-exp-002.aqsoldb-external-v1`
- parent model training partition: seed-42 hybrid structural ESOL training partition only
- parent training count: `902`
- parent training hash: `300ddc4981e1a9c2fb3735e598bcca89fb98a1cd4722cd58454e5d923781f00b`
- external retained count from EXP-002: `8,863`
- external retained hash: `0c3179ccdeb47b96b0afb3c38f61f6e9b95ab09c3071b18a433e3fb147d9c002`
- inherited applicability-domain threshold: `0.26684684684684684`

The model specification, training partition, decontamination policy, applicability-domain threshold, and AqSolDB source commit remained unchanged.

## Frozen model

- estimator: `RandomForestRegressor`
- representation: eight Research OS RDKit 2D descriptors + Morgan fingerprint
- Morgan radius: `2`
- Morgan bits: `2048`
- `n_estimators = 300`
- `min_samples_leaf = 2`
- `random_state = 42`
- `n_jobs = 1`

No AqSolDB target was used for fitting or tuning.

## Frozen external source

Dataset: AqSolDB

DOI: `10.1038/s41597-019-0151-1`

Source commit: `98cdd10a372058743e4f3fb950a1c9974ec9603a`

Source blob SHA: `67016e030cf0a741e250ba0267bd84461041db5f`

The same immutable `results/data_curated.csv` used by EXP-002 was used here.

## AqSolDB reliability semantics

The AqSolDB curation code assigns `Group`, `Occurrences`, and `SD` before writing the curated dataset. The original implementation defines:

- `G1`: one occurrence; `SD = 0` by construction;
- `G2`: two differing occurrences with absolute difference greater than `1`; selected value chosen by the AqSolDB curation procedure;
- `G3`: two differing occurrences with absolute difference at most `1`;
- `G4`: more than two occurrences with standard deviation greater than `0.5`;
- `G5`: more than two occurrences with standard deviation at most `0.5`.

These labels are treated as **curation strata**, not as a universal ordinal truth about measurement quality. In particular, `G1` has only one occurrence and therefore cannot provide empirical agreement information.

## Frozen decontamination

Before stratified metrics the implementation:

1. parsed the same AqSolDB source used by EXP-002;
2. preserved `Group`, `Occurrences`, and `SD` metadata for audit only;
3. ran the exact EXP-002 structural decontamination against all ESOL canonical structures/InChIKeys;
4. excluded invalid structures fail-closed;
5. excluded all ESOL overlaps before prediction metrics;
6. preserved the EXP-002 deterministic handling of duplicate/conflicting canonical groups;
7. asserted the EXP-002 retained count and retained-dataset hash before stratification;
8. asserted the parent v2 training count/hash and inherited AD threshold before inference.

Reliability metadata did not influence which structures were retained or how the model was trained.

## Predeclared analyses

### 1. Per-group analysis

For each of `G1`, `G2`, `G3`, `G4`, `G5`, the protocol predeclared:

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

This aggregation was frozen before metrics were inspected.

### 3. Descriptive deltas

The protocol predeclared only descriptive differences:

- RMSE difference between `repeated_higher_dispersion` and `repeated_lower_dispersion`;
- MAE difference between those strata;
- OOD-fraction difference;
- median-similarity difference.

No p-value, significance test, causal claim, or threshold was selected from observed results.

# First execution — GitHub Actions run 200

Run `34391324826` on head `82ada496c589d57eca6b1034f8fa01d30cb7e5dc` completed successfully.

Validation before EXP-003:

- focused solubility suite: `34 passed`;
- core Python 3.11: PASS;
- core Python 3.12: PASS;
- Cantera reference capability: PASS;
- ONLINE-EXP-001 v1: PASS;
- ONLINE-EXP-001 multi-seed replication: PASS;
- ONLINE-EXP-001 frozen v2: PASS;
- ONLINE-EXP-001 v2 closure: PASS;
- ONLINE-EXP-002 external validation: PASS with the same retained external hash and scientific result hash;
- ONLINE-EXP-003 reliability stratification: PASS.

## Input invariants observed

- AqSolDB source rows: `9,982`
- retained external records: `8,863`
- retained external hash: `0c3179ccdeb47b96b0afb3c38f61f6e9b95ab09c3071b18a433e3fb147d9c002`
- parent training count: `902`
- parent training hash: `300ddc4981e1a9c2fb3735e598bcca89fb98a1cd4722cd58454e5d923781f00b`
- inherited AD threshold: `0.26684684684684684`
- reliability metadata hash: `6cfeceee8f06b8e388fb86b172e0d2bb9c2e701002a530761502c543ad87c0a5`

All fail-closed parent assertions passed before stratified metrics were produced.

## Per-group results

| Group | n | MAE | RMSE | R2 | Median train similarity | Median curated SD | Median occurrences | OOD n | OOD fraction |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| G1 | 7,295 | 1.0348 | 1.4371 | 0.6415 | 0.3571 | 0.0000 | 1 | 1,812 | 24.84% |
| G2 | 201 | 0.9124 | 1.1963 | 0.7360 | 0.3462 | 0.8314 | 2 | 55 | 27.36% |
| G3 | 858 | 0.7740 | 1.0886 | 0.7823 | 0.3960 | 0.0879 | 2 | 177 | 20.63% |
| G4 | 144 | 2.0619 | **2.8448** | -0.5847 | 0.3067 | 0.9323 | 4 | 60 | **41.67%** |
| G5 | 365 | 0.9537 | 1.4228 | 0.6343 | 0.3810 | 0.1285 | 3 | 82 | 22.47% |

G4 is the clearest adverse stratum, but it is also small (`n = 144`), structurally farther from the parent training set, and much more OOD. Its high error therefore cannot be attributed to measurement dispersion alone.

## Target distributions by group

| Group | Mean logS | Median logS | SD logS | Min | Max |
|---|---:|---:|---:|---:|---:|
| G1 | -2.8462 | -2.5400 | 2.4003 | -13.1719 | 2.1377 |
| G2 | -4.0442 | -4.3409 | 2.3341 | -9.2068 | 1.5580 |
| G3 | -2.7275 | -2.4457 | 2.3346 | -12.0605 | 1.3686 |
| G4 | -3.9972 | -4.0725 | 2.2677 | -8.8600 | 1.0000 |
| G5 | -2.5667 | -2.3000 | 2.3560 | -11.4795 | 1.5363 |

The high-dispersion groups also occupy a more negative target region on average, another interpretation boundary.

## Predeclared consensus-stratum results

| Stratum | Groups | n | MAE | RMSE | R2 | Median train similarity | Median curated SD | OOD fraction |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| single_observation | G1 | 7,295 | 1.0348 | 1.4371 | 0.6415 | 0.3571 | 0.0000* | 24.84% |
| repeated_higher_dispersion | G2 + G4 | 345 | **1.3922** | **2.0523** | 0.2039 | 0.3333 | 0.8873 | **33.33%** |
| repeated_lower_dispersion | G3 + G5 | 1,223 | **0.8276** | **1.1981** | 0.7379 | 0.3889 | 0.1021 | **21.18%** |

`*` G1 SD is zero by construction because it contains single observations; it is not evidence of perfect agreement.

## Predeclared descriptive deltas

Higher-dispersion minus lower-dispersion repeated observations:

- RMSE: **+0.8541**
- MAE: **+0.5646**
- OOD fraction: **+0.1216** (about +12.16 percentage points)
- median maximum train similarity: **-0.0556**

The direction is internally coherent with the hypothesis that heterogeneous/disagreeing measurements are associated with harder prediction, but the simultaneous structural-domain and target-distribution differences prevent a causal interpretation.

## Interpretation

Within the frozen EXP-003 protocol:

1. repeated lower-dispersion AqSolDB records (`G3 + G5`) were predicted substantially better than repeated higher-dispersion records (`G2 + G4`);
2. the RMSE difference was large (`2.0523` vs `1.1981`), not a marginal numerical fluctuation;
3. G4 alone was especially difficult (`RMSE 2.8448`, `R2 -0.5847`);
4. the higher-dispersion aggregate was also more structurally out-of-domain (`33.33%` vs `21.18%`) and had lower median similarity to the parent training set (`0.3333` vs `0.3889`);
5. higher-dispersion groups also had a more negative target distribution;
6. therefore EXP-003 establishes a **descriptive association** between AqSolDB curation dispersion strata and model error, but does not isolate measurement disagreement as the cause;
7. G1 must remain interpreted as `single_observation`, never as a high-reliability group simply because its stored SD equals zero.

The result strengthens the Research OS evidence model because it exposes a second external limitation beyond structural applicability domain: external label provenance/consistency is associated with materially different observed error.

It does **not** establish that:

- the AqSolDB G1–G5 labels are universally ordered reliability scores;
- measurement dispersion alone causes model error;
- removing high-dispersion records would necessarily improve generalization to a new population;
- the model estimates experimental reliability;
- these results transfer unchanged to another solubility dataset or generated molecules.

## Reproducibility

- reliability metadata hash: `6cfeceee8f06b8e388fb86b172e0d2bb9c2e701002a530761502c543ad87c0a5`
- EXP-002 retained dataset hash: `0c3179ccdeb47b96b0afb3c38f61f6e9b95ab09c3071b18a433e3fb147d9c002`
- parent training hash: `300ddc4981e1a9c2fb3735e598bcca89fb98a1cd4722cd58454e5d923781f00b`
- report hash: `d40be74de1036a1bd8a2a59319f20399314d62a83154cbac2d1cd612ba1d8140`
- scientific result hash: `eeca8e4f2c7006791913745204d7e7129e25d0f6a1a56dd67487ae4456b4347a`
- execution hash: `f9379d29470aa6d724708abc934cc2bde481609b8101aa3e534fa4d91d4a6f1f`
- scientific hash policy: `round-finite-floats-12-decimal-digits-drop-volatile-hashes-v1`

Run-200 environment:

- CPython 3.12.14
- NumPy 2.5.3
- RDKit 2026.03.6
- scikit-learn 1.9.0
- Linux x86_64 GitHub Actions runner

## Closure

ONLINE-EXP-003 is closed. No grouping definition, aggregate stratum, model parameter, training partition, external-set rule, AD threshold, or metric definition was changed after the first result was observed.

Any follow-up that attempts to separate measurement-dispersion effects from structural-domain or target-distribution effects must be declared as a new experiment/protocol version.