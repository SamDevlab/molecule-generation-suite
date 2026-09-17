# Research OS v1.4 — Reproducible Scientific Run

This milestone makes a complete run auditable as a relationship between code, dataset, environment, configuration, labs, evidence and claims. It keeps the migration incremental: the legacy `Biolab/` and `formolecular/` directories remain untouched and are not treated as scientific ground truth merely because their scripts execute.

## Reproducible run

```text
Question / Input
      ↓
DatasetManifest
      ↓
EnvironmentManifest
      ↓
Materialized ResearchPlan
      ↓
Labs + ProofEngine
      ↓
Evidence + FIRST_LOSS
      ↓
ScientificClaim
      ↓
ResearchBundle
      ↓
SEALED run
      ↓
Rerun / Compare
```

Evidence is an attributable observation or calculation output. Proof is the result of explicit gates over the recorded inputs and evidence. A PASS means only that the declared gate passed; it does not upgrade a computational result to experimental truth. `FIRST_LOSS` is the first non-PASS gate and is preserved when a downstream step is skipped.

## Core artifacts

`EnvironmentManifest` records Python, platform, git commit/branch/dirty state, package versions and optional engines. Its logical hash excludes volatile identity and timestamp fields and is stable under dictionary reordering. Missing optional dependencies are represented as `available: false`.

`DatasetManifest` records identity, version, schema, content hash, row/column counts, source classification, evidence levels, transformations and artifact locations. The v1.4 path validates CSV input, streams it into curated Parquet with PyArrow, and stores the source hash, output hash and conversion run ID. DuckDB is an optional query backend; it is not a dependency of any Lab.

`RunManifest` has explicit lifecycle transitions: `CREATED → RUNNING → COMPLETED|FAILED|INDETERMINATE → SEALED`. Sealing freezes mutable collections and nested payload mappings. A rerun receives a new ID and a `RunLineage` record; the original run is never overwritten.

`ResearchBundle` is a filesystem audit package containing the run manifest, environment, inputs, config, dataset manifests, provenance, steps, evidence, claims, artifact index, `FIRST_LOSS`, summary and integrity/seal metadata. `verify_bundle()` returns `PASS`, `FAIL` or `INDETERMINATE` with Rule IDs for missing files, hash mismatches, broken references, invalid dataset/environment state and seal failures.

## Golden workflow

Install the development and data extras, then run the safe fixture:

```powershell
python -m pip install -e ".[dev,molecule,data]"
python examples/golden_workflow/run.py --mode stub
python examples/golden_workflow/run.py --mode real
```

Stub mode is deterministic and labels every fixture result `TEST_SYNTHETIC` with `test_fixture` provenance. It is an infrastructure test, not a physics calculation. Real mode uses the configured Labs. If Cantera is absent, the combustion step is `INDETERMINATE`, its `FIRST_LOSS` is retained, and downstream steps are `SKIPPED`; the resulting bundle is still a valid record of an indeterminate run.

The small `examples/golden_workflow/data/golden_fuels.csv` input contains only benign fixture records. Its manifest is explicitly synthetic and cannot pass the experimental-ground-truth gate.

## ML golden path

`research_os.ml.golden.run_ml_golden_path()` exercises a non-molecular fixture target through `DatasetManifest`, `FeatureSchema`, a seeded split, `TrainingRunManifest`, candidate/champion manifests, validation and `ModelPromotionEngine`. A candidate with higher MAE is rejected with `ML-PROMO-MAE-001`. R² remains a metric; it is never rendered as a reliability percentage. Missing external-test acceptability remains insufficient evidence when the promotion policy requires it.

## Knowledge MOCs

MOCs are typed navigation structures, not evidence. `MOCRegistry` and `moc_integrity_gate()` detect unresolved Zettel or child-MOC references. The knowledge directory helper creates `inbox/`, `sources/`, `zettels/`, `mocs/`, `claims/`, `equations/`, `review/` and `training/` without ingesting books or copying a corpus. Training/RAG records still require eligible reviewed Zettels with source locators.

## CLI and verification

Useful commands are intentionally small:

```text
research-os env capture --output environment.json
research-os dataset inspect path/to/data.csv
research-os dataset register path/to/data.csv --dataset-id demo --version 1 --schema-id demo-v1
research-os dataset verify demo --root datasets
research-os run golden --mode stub --output runs/golden
research-os bundle verify runs/golden/<PLAN-ID>
research-os labs
```

External engines remain bounded by their models and validity domains. Cantera is physics/model evidence, not experiment; RDKit is deterministic chemical-structure characterization; docking is computational evidence; CALPHAD is computational thermodynamics; ML predictions are not E4/E5 evidence. The legacy scripts remain necessary until their behavior and outputs are migrated behind these typed contracts and independently verified.
