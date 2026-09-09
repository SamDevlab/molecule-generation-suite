# ONLINE-EXP-002 — AqSolDB external validation

Status: **executed and closed; protocol frozen before first external metrics**

## Scientific question

Does the frozen `ONLINE-EXP-001` v2 combined Random Forest retain useful aqueous-solubility predictive performance on an external public dataset after removing every structure that overlaps Delaney/ESOL?

This experiment is an external validation of a fixed model specification. It is not a new model-selection exercise.

## External source

Dataset: AqSolDB

Primary paper: Sorkun, Khetan & Er (2019), *AqSolDB, a curated reference set of aqueous solubility and 2D descriptors for a diverse set of compounds*, Scientific Data 6, 143.

DOI: `10.1038/s41597-019-0151-1`

Recorded immutable source file:

`https://raw.githubusercontent.com/mcsorkun/AqSolDB/98cdd10a372058743e4f3fb950a1c9974ec9603a/results/data_curated.csv`

Source commit: `98cdd10a372058743e4f3fb950a1c9974ec9603a`

Recorded GitHub blob SHA for the source file at protocol declaration:

`67016e030cf0a741e250ba0267bd84461041db5f`

Raw AqSolDB data is not vendored into Research OS.

## Why decontamination is mandatory

AqSolDB was curated from nine public solubility datasets and includes Delaney/ESOL among its source datasets. Calling an unfiltered AqSolDB score “external validation” would therefore be invalid.

The external set was decontaminated before any prediction metric was computed.

## Frozen parent model

Parent protocol: `research-os.online-exp-001.v2`

Training source: Delaney/ESOL public dataset already recorded by `ONLINE-EXP-001`.

Training partition: the **seed-42 hybrid structural training partition only**, produced by the already frozen v2 grouping protocol.

Parent training count: `902`.

Parent training-partition hash:

`300ddc4981e1a9c2fb3735e598bcca89fb98a1cd4722cd58454e5d923781f00b`

Frozen model specification:

- estimator: `RandomForestRegressor`
- representation: eight Research OS RDKit 2D descriptors + Morgan fingerprint
- Morgan radius: `2`
- Morgan bits: `2048`
- `n_estimators = 300`
- `min_samples_leaf = 2`
- `random_state = 42`
- `n_jobs = 1`

The parent validation and test targets were not added to training for EXP-002.

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

This policy was frozen before external metrics were observed.

## Metrics

Primary metrics over the complete retained external set:

- MAE
- RMSE
- R2

R2 is a regression score, never a confidence or reliability percentage.

No pass/fail threshold was selected from the observed AqSolDB result.

## Applicability-domain analysis

The domain rule remains inherited from v2:

- Morgan radius 2 / 2048-bit Tanimoto similarity;
- threshold derived only from the ESOL training partition;
- threshold = 5th percentile of leave-one-out nearest-neighbor similarity in the parent training set.

AqSolDB targets do not participate in construction of the domain threshold.

## First external execution — GitHub Actions run 198

The first result was produced only after the protocol and source were frozen.

Validation status: **PASS**

- focused solubility suite: `29 passed`
- core Python 3.11: PASS
- core Python 3.12: PASS
- Cantera reference capability: PASS
- ONLINE-EXP-001 v1: PASS
- ONLINE-EXP-001 multi-seed replication: PASS
- ONLINE-EXP-001 frozen v2: PASS
- ONLINE-EXP-001 v2 closure: PASS
- ONLINE-EXP-002 external validation: PASS

### Source and curation audit

| Item | Count |
|---|---:|
| AqSolDB source rows | 9,982 |
| Parsed rows | 9,982 |
| Missing-structure rows | 0 |
| Invalid-target rows | 0 |
| Invalid structures detected by RDKit | 2 |
| ESOL-overlap canonical groups excluded | 1,117 |
| ESOL-overlap records excluded | 1,117 |
| Remaining conflicting-target groups | 0 |
| Remaining same-target duplicate groups | 0 |
| Retained external records | **8,863** |

The overlap audit identified `1,117` AqSolDB structures matching ESOL, equal to the number of unique canonical structures found in the parent ESOL chemical audit. Those records were removed before prediction metrics were computed.

Parsed AqSolDB source hash:

`2c6e56f56389f0fd99fa2a3c843446f98b6b068a3f93aaab71a08822caa085f4`

Decontamination lineage hash:

`6c5c1beaf69e29b087a7224b7fccaa65eeb0b3e2b8d286fe357e93215184f4cc`

Retained external-dataset hash:

`0c3179ccdeb47b96b0afb3c38f61f6e9b95ab09c3071b18a433e3fb147d9c002`

### External predictive performance

On the `8,863` retained AqSolDB records:

| Metric | External result |
|---|---:|
| MAE | **1.0202** |
| RMSE | **1.4359** |
| R2 | **0.6421** |

The external score is materially weaker than the internal ESOL structural-holdout result. This is evidence that the ESOL result should not be treated as universal performance. At the same time, the positive external R2 and error levels show that the frozen model retains meaningful predictive signal on the much larger decontaminated AqSolDB view.

The external result reflects both model generalization limits and the heterogeneity of measurements aggregated by AqSolDB; it must not be interpreted as a pure estimate of model error under one controlled experimental protocol.

### External applicability domain

Inherited threshold:

`0.26684684684684684`

| Domain | n | MAE | RMSE | R2 |
|---|---:|---:|---:|---:|
| In-domain | 6,677 | 0.8924 | **1.2349** | 0.7271 |
| Out-of-domain | 2,186 | 1.4104 | **1.9239** | 0.3895 |

Unlike the tiny OOD subsets in ONLINE-EXP-001, the external OOD set contains `2,186` compounds. The substantially larger OOD error is therefore a much stronger descriptive result for this dataset, while still not establishing causality.

### Similarity-stratified external error

| Maximum parent-train Tanimoto | n | MAE | RMSE |
|---|---:|---:|---:|
| [0.0, 0.4) | 5,284 | 1.1749 | **1.6169** |
| [0.4, 0.6) | 2,815 | 0.8178 | **1.1493** |
| [0.6, 0.8) | 599 | 0.7150 | **0.9914** |
| [0.8, 1.0] | 165 | 0.6252 | **0.9612** |

Error decreases substantially as maximum structural similarity to the parent training set rises. Across these fixed bins, RMSE falls from `1.6169` below 0.4 similarity to `0.9612` in the highest-similarity bin.

This supports a strong **descriptive applicability-domain relationship** in the external benchmark. It does not prove that structural similarity alone causes prediction error, nor that this exact relationship transfers unchanged to another dataset.

## Reproducibility identities

Parent ESOL dataset hash:

`6de39771743dc4f15b191cffc27e1e02eb474457cc841afda565f31aff198e85`

Parent training-partition hash:

`300ddc4981e1a9c2fb3735e598bcca89fb98a1cd4722cd58454e5d923781f00b`

Legacy/raw report hash:

`1117c124378b49f98551eac59758dcee900987975eca81f496a9086f2a6ea1f1`

Scientific result hash:

`2bcd795284143f73c1207f9c0a20fdd2272b5fb05cccbb3ac5da7d25e5e44057`

Scientific hash policy:

`round-finite-floats-12-decimal-digits-drop-volatile-hashes-v1`

Execution hash:

`0dfafd1df3a0a88428b66f05148c5fee533fc510868322696357ee96092b2a60`

Run-198 execution environment:

- CPython `3.12.14`
- NumPy `2.5.3`
- RDKit `2026.03.6`
- scikit-learn `1.9.0`
- Linux x86_64 GitHub Actions runner

## Final interpretation

Within this frozen protocol:

1. the ESOL-trained descriptor+Morgan Random Forest retains useful predictive signal on a structurally decontaminated AqSolDB view;
2. external performance is materially weaker than internal ESOL holdout performance, demonstrating a real generalization gap;
3. all `1,117` unique canonical ESOL structures present in AqSolDB were excluded before metrics;
4. two structures rejected by the active RDKit runtime were excluded fail-closed and recorded;
5. the inherited applicability-domain threshold separates substantially different external error regimes;
6. the large external OOD subset provides stronger evidence than the small OOD subsets observed in ONLINE-EXP-001;
7. prediction error decreases across the predeclared structural-similarity bins as similarity to the parent training set rises;
8. AqSolDB source and measurement heterogeneity remains a major interpretation boundary.

The result does **not** establish:

- universal solubility prediction;
- safety or efficacy;
- synthesizability;
- clinical validity;
- causal relationships;
- performance on generated molecules;
- independence from all possible historical data relationships beyond the explicitly audited structural overlap.

## Freeze rule

ONLINE-EXP-002 is now closed. The first external result is retained as observed.

Any change to model hyperparameters, representation, decontamination rules, metric definitions, parent training partition, or applicability-domain threshold requires a new experiment/protocol version rather than modifying this result post hoc.

A scientifically useful next experiment is to explain the remaining external error without tuning this frozen result, for example by stratifying AqSolDB by measurement/source reliability or source provenance.