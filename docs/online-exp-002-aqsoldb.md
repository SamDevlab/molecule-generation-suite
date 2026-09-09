# ONLINE-EXP-002 — AqSolDB external validation

Status: **predeclared protocol; results not yet inspected**

## Scientific question

Does the frozen `ONLINE-EXP-001` v2 combined Random Forest retain useful aqueous-solubility predictive performance on an external public dataset after removing every structure that overlaps Delaney/ESOL?

This experiment is an external validation of a fixed model specification. It is not a new model-selection exercise.

## External source

Dataset: AqSolDB

Primary paper: Sorkun, Khetan & Er (2019), *AqSolDB, a curated reference set of aqueous solubility and 2D descriptors for a diverse set of compounds*, Scientific Data 6, 143.

DOI: `10.1038/s41597-019-0151-1`

Recorded source file:

`https://raw.githubusercontent.com/mcsorkun/AqSolDB/master/results/data_curated.csv`

Recorded GitHub blob SHA for the source file at protocol declaration:

`67016e030cf0a741e250ba0267bd84461041db5f`

Raw AqSolDB data will not be vendored into Research OS.

## Why decontamination is mandatory

AqSolDB was curated from nine public solubility datasets and includes Delaney/ESOL among its source datasets. Calling an unfiltered AqSolDB score “external validation” would therefore be invalid.

The external set must be decontaminated before any prediction metric is computed.

## Frozen parent model

Parent protocol: `research-os.online-exp-001.v2`

Training source: Delaney/ESOL public dataset already recorded by `ONLINE-EXP-001`.

Training partition: the **seed-42 hybrid structural training partition only**, produced by the already frozen v2 grouping protocol.

Expected parent training count from the accepted v2 run: `902`.

Frozen model specification:

- estimator: `RandomForestRegressor`
- representation: eight Research OS RDKit 2D descriptors + Morgan fingerprint
- Morgan radius: `2`
- Morgan bits: `2048`
- `n_estimators = 300`
- `min_samples_leaf = 2`
- `random_state = 42`
- `n_jobs = 1`

The parent validation or test targets are not added to training for EXP-002.

## AqSolDB parsing

Required source columns:

- `ID`
- `SMILES`
- `Solubility`

`InChIKey` is read when present but Research OS independently canonicalizes structures with the active RDKit runtime.

Rows with missing/non-numeric/non-finite solubility or invalid molecular structure are excluded with counts recorded. Missing values are never imputed.

## Decontamination policy

Before inference:

1. canonicalize every ESOL and AqSolDB structure with RDKit;
2. derive canonical isomeric SMILES and InChIKey;
3. if any AqSolDB canonical structure or InChIKey matches any ESOL record, exclude the entire AqSolDB canonical-structure group;
4. among the remaining AqSolDB records, group by canonical structure;
5. if a group contains conflicting numeric targets, exclude the entire group;
6. if a group contains repeated identical targets, retain one deterministic source row;
7. do not average targets;
8. do not impute targets;
9. compute a lineage hash over every keep/exclude decision;
10. compute a separate curated external-dataset hash over the retained records.

This policy is frozen before external metrics are observed.

## Metrics

Primary metrics over the complete retained external set:

- MAE
- RMSE
- R2

R2 is a regression score, never a confidence or reliability percentage.

No pass/fail threshold is chosen from the observed AqSolDB result.

## Applicability-domain analysis

The domain rule remains inherited from v2:

- Morgan radius 2 / 2048-bit Tanimoto similarity;
- threshold derived only from the ESOL training partition;
- threshold = 5th percentile of leave-one-out nearest-neighbor similarity in the parent training set.

Report:

- in-domain count and metrics;
- out-of-domain count and metrics when non-empty;
- external similarity-bin counts and RMSE for `[0,0.4)`, `[0.4,0.6)`, `[0.6,0.8)`, `[0.8,1.0]`;
- no strong OOD-error claim when subsets are too small.

AqSolDB targets are not used to construct the domain threshold.

## Reproducibility

The report must include:

- AqSolDB source URL and DOI;
- recorded source blob SHA;
- parsed source hash;
- parent ESOL dataset hash;
- parent training-partition hash;
- overlap/decontamination counts;
- lineage hash;
- retained external-set hash;
- model specification;
- scientific result hash;
- execution hash and execution environment.

Raw legacy hashes may be preserved for compatibility but are not treated as environment-independent scientific identities.

## Interpretation boundaries

A successful execution can support only statements about this fixed ESOL-trained model on the retained, decontaminated AqSolDB view.

It does **not** establish:

- universal solubility prediction;
- safety or efficacy;
- synthesizability;
- clinical validity;
- causal relationships;
- performance on generated molecules;
- independence from all possible historical data relationships beyond the explicitly audited structural overlap.

## Freeze rule

After the first external metrics are produced, changes to model hyperparameters, representation, decontamination rules, metric definitions, or applicability-domain threshold require a new protocol version. The first result must not be tuned post hoc.