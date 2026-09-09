# ONLINE-EXP-001 — aqueous solubility generalization benchmark

## Scientific question

How well do simple 2D molecular descriptors predict measured aqueous solubility when the test molecules are structurally separated from the training set by Murcko scaffold?

This experiment is intentionally a generalization benchmark, not a molecule-generation task.

## Dataset

The first reference dataset is Delaney/ESOL. Research OS records the original paper DOI (`10.1021/ci034243x`) and retrieves the public Delaney CSV from the DeepChem-hosted source when no local file is supplied. The raw dataset is **not vendored** in this repository.

The benchmark uses only the measured aqueous log-solubility target. Any precomputed ESOL prediction column present in the CSV is ignored.

A content-derived dataset hash is recorded in every report.

## Features

Eight deterministic RDKit 2D descriptors are used:

- molecular weight;
- MolLogP;
- TPSA;
- hydrogen-bond donors;
- hydrogen-bond acceptors;
- rotatable bonds;
- fraction Csp3;
- aromatic-heavy-atom fraction.

No target-derived feature is permitted.

## Models

The protocol fixes three models before evaluation:

1. training-target mean baseline;
2. standardized Ridge regression (`alpha=1.0`);
3. Random Forest (`300` trees, `min_samples_leaf=2`, fixed seed, single worker for reproducibility).

Validation metrics are reported but are not used to tune these hyperparameters in v1.

## Splits

Both comparisons target the same 80/10/10 train/validation/test fractions:

- deterministic seeded random split;
- Murcko scaffold-group split.

For the scaffold split, groups are ordered from largest to smallest before greedy allocation; the seeded shuffle only breaks equal-size ties. This prevents a large scaffold group such as the acyclic bucket from accidentally consuming the held-out partition merely because it was encountered first.

Research OS then audits the scaffold split and fails closed if a scaffold occurs in more than one partition.

The main diagnostic is the test-RMSE generalization gap:

`scaffold RMSE - random RMSE`

A positive gap means performance worsened under scaffold-held-out evaluation. It does not by itself establish why performance changed.

## Metrics

- MAE
- RMSE
- R2

R2 is a regression score and must never be described as a reliability, confidence, clinical, or thermodynamic-accuracy percentage.

## Running

Install the optional ML capability:

```bash
python -m pip install -e ".[dev,molecule,ml]"
```

Then run:

```bash
python scripts/run_solubility_benchmark.py --output online-exp-001.json
```

To use a previously obtained CSV instead of network retrieval:

```bash
python scripts/run_solubility_benchmark.py --csv path/to/delaney-processed.csv --output online-exp-001.json
```

## Interpretation boundary

This benchmark evaluates predictive generalization on an existing measured dataset. It does not demonstrate experimental efficacy, safety, synthesizability, or performance of newly generated molecules. Results should be interpreted together with split strategy, dataset provenance, chemical-domain coverage, measurement limitations, and the exact partitioning protocol.
