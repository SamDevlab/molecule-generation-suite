# ONLINE-EXP-001 v2 — chemical-domain solubility benchmark

This document freezes the v2 protocol before interpreting its first real run. The accepted v1 and multi-seed reports remain historical results and are not rewritten.

## Question

How much of the apparent aqueous-solubility performance survives a stricter chemical-domain audit when we improve structural grouping, compare molecular representations, and explicitly measure applicability domain?

## Dataset

The input remains Delaney/ESOL, using the measured logS target and the same recorded DOI/source as v1. Raw data is downloaded at execution time and is not vendored.

Before fitting any learned model, v2 records:

- raw and valid record counts;
- canonical isomeric SMILES;
- InChIKey uniqueness;
- duplicate structure groups;
- duplicate structures with conflicting measured targets;
- multi-fragment records;
- formally charged records;
- deterministic audit hash.

The audit is descriptive. Duplicates, salts/fragments, or charged structures are not silently removed. Invalid structures fail the v2 benchmark closed.

## Structural split v2

The v1 Murcko-only method maps every ringless molecule to an empty scaffold. V2 does not collapse all acyclic molecules into a single `ACYCLIC` group.

- molecules with a ring system use their Bemis-Murcko scaffold;
- acyclic molecules are clustered using Morgan radius 2, 2048-bit fingerprints and Butina clustering;
- the acyclic clustering similarity threshold is frozen at `0.50` before execution and is not optimized against solubility targets;
- structural groups are allocated whole to train/validation/test;
- a post-split audit fails if a v2 structural group appears in more than one partition.

Both random and hybrid-structural protocols target 80/10/10 partitions.

## Models and representations

V2 evaluates a fixed matrix. Test results must not be used to change these specifications inside v2.

1. training-target mean baseline;
2. original Delaney ESOL formula with fixed published coefficients (not refitted);
3. Ridge (`alpha=1.0`) on the same eight 2D descriptors used by v1;
4. Random Forest (`300` trees, `min_samples_leaf=2`) on eight 2D descriptors;
5. the same Random Forest specification on Morgan radius 2 / 2048-bit fingerprints;
6. the same Random Forest specification on descriptors + Morgan bits.

No hyperparameter search is performed.

## Target-distribution audit

For train, validation, and test, the report records:

- n;
- mean;
- median;
- sample standard deviation;
- minimum;
- Q1;
- Q3;
- maximum.

This is required because R² changes with the variance/distribution of the held-out targets and must not be interpreted as a reliability percentage.

## Applicability domain

Applicability domain is derived from structure only.

1. Compute Morgan radius 2 / 2048-bit fingerprints for the hybrid-structural training partition.
2. For every training molecule, calculate its maximum Tanimoto similarity to another training molecule (leave-one-out nearest neighbor).
3. Define the domain threshold as the 5th percentile of that training-only distribution.
4. For each test molecule, calculate maximum Tanimoto similarity to the training set.
5. Mark the test structure in-domain when its maximum similarity is at least the training-derived threshold.

The threshold therefore uses no test target and is not chosen to improve test metrics.

For each model, v2 reports in-domain and out-of-domain metrics separately when records exist. For the combined Random Forest it also reports descriptive error summaries in fixed Tanimoto bands: `[0,0.4)`, `[0.4,0.6)`, `[0.6,0.8)`, `[0.8,1.0]`.

## Error associations

For the combined Random Forest on the hybrid-structural test set, v2 reports Pearson association between absolute prediction error and:

- maximum training similarity;
- molecular weight;
- MolLogP;
- TPSA.

These are descriptive associations only and do not establish causality.

## Descriptor ablation

Leave-one-descriptor-out Random Forest ablation is performed only on the hybrid-structural validation partition. It does not alter the model subsequently reported on the test set.

This avoids selecting descriptor subsets from test performance.

## Interpretation boundary

V2 remains a benchmark on one public measured dataset. It does not establish universal solubility prediction, experimental validation, safety, synthesizability, efficacy, or performance of generated molecules.

A future external dataset remains a separate experiment and must be structurally decontaminated against ESOL before being called external validation.
