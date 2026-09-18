# MOLDISC-002 — AqSolDB structural coverage of the frozen ID5 neighborhood

Status: **executed and closed; first coverage result preserved without post-hoc threshold or model changes**

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


## First successful execution — GitHub Actions run 9

The first MOLDISC-002 result was produced in Actions run `35294959772`.

A preceding CI run failed while reproducing the MOLDISC-001 generation identity,
before AqSolDB coverage executed. The implementation was corrected to reuse the
same canonical-seed atom ordering as MOLDISC-001. No coverage result had been
observed and no scientific rule changed.

Source audit:

- AqSolDB rows: `9,982`
- invalid structures under active RDKit: `2`
- unique valid canonical structures: `9,980`
- parsed-source hash: `2c6e56f56389f0fd99fa2a3c843446f98b6b068a3f93aaab71a08822caa085f4`

Scientific identities:

- parent generation: `d2881a9906a6a60d54e90a303601d9509983e6f1a0b9ce01a0792bf088890abe`
- coverage: `f951cfe78c43d430f7077532a67fdcbf84b49157ca68214b4880066cd8158a56`
- program: `3e7060ecd6fe307afef520a4b4506a961aa0e5a56aca4b2948dce13d0abcb4d6`

### Coverage result

All nine frozen candidates fall in the predeclared `[0.0,0.4)` nearest-neighbor
bin.

There are:

- `0 / 9` candidates with any AqSolDB neighbor at Tanimoto >= 0.4;
- `0 / 9` at >= 0.6;
- `0 / 9` at >= 0.8.

The highest nearest-neighbor similarity is `0.39655172413793105`, observed for
`MOLDISC-001-ID5-GEN-20C30B98F0`. Its closest recorded structure is
`O=C(O)COc1cc(Cl)ccc1Cl` (AqSolDB source `C-1803`), with recorded logS
`-2.62`.

The crystallographic ID5 seed itself has nearest AqSolDB similarity
`0.2857142857142857`.

### Scientific conclusion

The MOLDISC-001 chemical neighborhood is not merely outside the ESOL training
domain. Under the same Morgan representation, it also lacks close measured
neighbors in the much larger immutable AqSolDB source at the historical 0.4
similarity boundary.

Therefore MOLDISC-002 **does not justify fitting a local AqSolDB model** for this
candidate set.

This is preserved as another boundary result rather than lowering the
similarity boundary after seeing the data.

A next program should change the scientific question rather than tune this
result. Reasonable next directions are to select a different source-backed
target/seed whose chemistry is actually covered by measured solubility data, or
to investigate an orthogonal property/evidence layer without claiming that it
repairs the missing solubility support.
