# Molecular Discovery Program v0.1

## Purpose

This is the first flagship vertical that **uses Research OS 5.1 instead of extending it**.

The workflow composes existing components:

```text
candidate SMILES
      |
      v
  MoleculeLab
      |
      +--> deterministic molecular characterization (E2)
      |
      v
frozen ESOL solubility capability
      |
      +--> predicted aqueous logS (E1)
      +--> applicability-domain status
      |
      v
optional DockingLab
      |
      +--> docking evidence (E2)
      |
      v
evidence-completeness triage
      |
      v
auditable report
```

It deliberately introduces no Program v2, Registry v2, Evidence v2 or new generic orchestrator.

## Solubility capability

The product-facing predictor is extracted from the closed ONLINE-EXP-001 through ONLINE-EXP-005 sequence rather than merging that old stacked PR chain into the active core.

Frozen parent model:

- Delaney/ESOL;
- seed-42 hybrid structural training partition only;
- training count: 902;
- training hash: `300ddc4981e1a9c2fb3735e598bcca89fb98a1cd4722cd58454e5d923781f00b`;
- eight RDKit descriptors + Morgan radius 2 / 2048 bits;
- RandomForestRegressor with 300 trees, min_samples_leaf 2, random_state 42, n_jobs 1.

The implementation reconstructs the model from the recorded ESOL source and refuses to call a different dataset/partition the frozen model.

### Validation retained

Internal five-seed hybrid holdout:

- RMSE: 0.803 ± 0.113;
- R2: 0.859 ± 0.031.

Decontaminated AqSolDB external validation:

- n = 8,863;
- MAE = 1.0202;
- RMSE = 1.4359;
- R2 = 0.6421;
- in-domain RMSE = 1.2349;
- out-of-domain RMSE = 1.9239.

Later diagnostics are retained as interpretation boundaries, not as new model tuning:

- raw repeated-dispersion RMSE gap: +0.8541;
- after AD/similarity/target control: +0.4664;
- after additional source-aware control: +0.3743.

The residual association is heterogeneous across source datasets and remains observational. It is not evidence that measurement dispersion causes model error.

## Triage semantics

No universal composite drug score is produced.

Candidate groups are:

- `ELIGIBLE_FOR_REVIEW`: chemistry passed, solubility is in-domain, and requested docking did not fail;
- `OUT_OF_DOMAIN`: solubility prediction lies outside the inherited AD threshold;
- `INCOMPLETE_EVIDENCE`: a requested/expected capability is unavailable or failed;
- `EXCLUDED`: molecular validation failed.

Within `ELIGIBLE_FOR_REVIEW`, review order is deterministic and uses higher predicted aqueous logS first. This is **triage order only**, not efficacy ranking.

Docking scores are not folded into a cross-target composite score.

## Running

Install the vertical dependencies:

```bash
python -m pip install -e ".[dev,discovery]"
```

Prepare a CSV:

```csv
id,name,smiles
MOL-001,Ethanol,CCO
MOL-002,Propanol,CCCO
```

Run with the recorded public ESOL source:

```bash
python scripts/run_molecular_discovery.py candidates.csv --output runs/molecular-discovery-001
```

Or provide a local copy of the exact ESOL CSV:

```bash
python scripts/run_molecular_discovery.py candidates.csv --esol-csv data/delaney-processed.csv --output runs/molecular-discovery-001
```

The output directory contains:

```text
manifest.json
candidates.csv
evidence.json
limitations.json
report.md
```

## Optional docking

The Python API accepts a `docking` mapping per candidate and delegates it directly to the existing DockingLab.

The workflow does **not** fabricate a 3D ligand or receptor from SMILES. A docking request must already satisfy DockingLab preparation, receptor, grid, target and protocol requirements.

## Scientific boundaries

- solubility prediction is E1 ML evidence;
- deterministic molecular characterization is E2 computational evidence;
- docking is E2 computational evidence;
- no stage establishes clinical efficacy or safety;
- OUT_OF_DOMAIN is preserved explicitly;
- missing capabilities do not receive silent heuristic substitutes;
- review order is not an experimental conclusion.
