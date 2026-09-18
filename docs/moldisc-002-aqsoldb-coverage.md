# MOLDISC-002 — AqSolDB structural coverage of the frozen ID5 neighborhood

Status: **protocol frozen before first coverage result is inspected**

## Scientific question

MOLDISC-001 established that the crystallographic ID5 seed and all eight frozen
single-halogen analogs are outside the applicability domain of the frozen ESOL
predictor.

MOLDISC-002 does not change that result and does not train another model.

It asks one narrower question:

> Does the immutable AqSolDB source contain experimentally measured structural
> neighbors for the exact nine-molecule MOLDISC-001 candidate set?

If AqSolDB also has poor structural coverage, there is no scientific basis for
simply retraining on AqSolDB and claiming that the problem is solved. If it has
materially closer measured neighbors, that observation can justify a separate
future local-model experiment with its own predeclared validation protocol.

## Frozen parent candidate set

Parent program: `MOLDISC-001 v1.0`

Frozen generation scientific hash:

`d2881a9906a6a60d54e90a303601d9509983e6f1a0b9ce01a0792bf088890abe`

Candidate count:

- 1 crystallographic ID5 seed;
- 8 deterministic E0 halogen analogs;
- 9 total structures.

MOLDISC-002 recomputes the parent generation and refuses to execute if the
generation hash changes.

## Immutable AqSolDB source

Dataset: AqSolDB

DOI: `10.1038/s41597-019-0151-1`

Source commit:

`98cdd10a372058743e4f3fb950a1c9974ec9603a`

Recorded source blob SHA:

`67016e030cf0a741e250ba0267bd84461041db5f`

Immutable source URL:

`https://raw.githubusercontent.com/mcsorkun/AqSolDB/98cdd10a372058743e4f3fb950a1c9974ec9603a/results/data_curated.csv`

Expected source rows:

`9982`

Expected parsed-source scientific hash:

`2c6e56f56389f0fd99fa2a3c843446f98b6b068a3f93aaab71a08822caa085f4`

These identities were already observed and frozen during ONLINE-EXP-002. The raw
dataset is not vendored into Research OS.

## Coverage representation

Each valid AqSolDB structure is:

1. parsed with the active RDKit runtime;
2. canonicalized;
3. assigned an active-runtime InChIKey;
4. grouped by canonical structure;
5. fingerprinted with Morgan radius 2 / 2048 bits.

Repeated measurements of the same canonical structure are **preserved** inside
that structure group. MOLDISC-002 records count, median, minimum, maximum and
source IDs but does not create a new averaged training target.

For each of the nine frozen candidates, the program records:

- nearest AqSolDB Tanimoto similarity;
- the five nearest unique canonical structures;
- number of unique AqSolDB structures at similarity >= 0.4;
- number at >= 0.6;
- number at >= 0.8.

## Predeclared similarity bins

No new coverage threshold is selected after seeing the candidate results.

MOLDISC-002 reuses the exact descriptive bins from ONLINE-EXP-002:

- `[0.0, 0.4)`
- `[0.4, 0.6)`
- `[0.6, 0.8)`
- `[0.8, 1.0]`

In ONLINE-EXP-002 these bins were associated with different external ESOL-model
error regimes. In MOLDISC-002 they are used **only as structural coverage
descriptors**.

## No training in v1

MOLDISC-002 performs:

```text
frozen MOLDISC-001 candidates
              |
              v
immutable AqSolDB source
              |
              v
canonical unique structures
              |
              v
Morgan/Tanimoto neighborhood search
              |
              v
coverage report
```

It does not perform:

- model fitting;
- model selection;
- hyperparameter tuning;
- target averaging for training;
- docking;
- candidate regeneration;
- post-result threshold selection.

## First-run acceptance gates

Before the first result can be accepted, CI must confirm:

- the MOLDISC-001 generation hash still matches;
- exactly nine parent candidates are evaluated;
- AqSolDB source row count is 9,982;
- parsed-source hash matches the frozen ONLINE-EXP-002 identity;
- all valid AqSolDB structures are canonicalized fail-closed;
- candidate nearest-neighbor metrics are deterministic;
- no model is trained;
- coverage/program scientific hashes are emitted.

## Interpretation boundaries

A close AqSolDB structural neighbor is useful evidence that the chemical region
has measured solubility coverage. It does not prove that the candidate has the
same solubility as that neighbor.

Structural similarity does not establish:

- common mechanism;
- binding affinity;
- inhibition or potency;
- efficacy;
- safety;
- synthetic accessibility;
- clinical value.

AqSolDB also aggregates measurements from heterogeneous source protocols. Any
future model trained from this source requires a new experiment that deals
explicitly with source heterogeneity, data splitting, leakage, validation and
applicability domain before model performance is inspected.
