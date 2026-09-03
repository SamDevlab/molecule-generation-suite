# Legacy inventory (v1.8)

Generated from the checked-out `Biolab/` and `formolecular/` trees by the
read-only scanner `research_os.legacy.scan_legacy`. At the v1.8 checkpoint it
found 966 preserved components, two recognizable flows, and 60 dataset/model/
output artifacts requiring quarantine review. Hashes and the complete path
list are available from `research-os legacy audit --repo-root .`; the scanner
does not modify either legacy directory.

## Inventory categories

The machine-readable inventory classifies scripts, datasets, serialized
models, configs, molecular structures/targets, reports and output artifacts.
Text artifacts are additionally flagged for external-engine calls, hardcoded
paths, ML pipelines, R² overclaims, heuristics, synthetic feedback, and
Alzheimer-related target references.

Known examples include:

- `formolecular/g_oraculo_farma.py`: XGBoost prediction of QED-like labels;
- `formolecular/g_oraculo_aeroespacial.py`: XGBoost path for an Isp-like target;
- `formolecular/t_aero.py` and `t_aero2.py`: energy/Isp heuristics and synthetic
  mutation feedback;
- `Biolab/fabrica_g2.py`: Vina/Open Babel calls, parallel scoring and report
  generation;
- `formolecular/novo_horizonte/a.py`: cross-docking against `4EY7` with a
  repository comment identifying a human crystal, plus `5W8K` risk columns;
- `formolecular/modelos_ia*/`: serialized models whose training provenance is
  not independently established by this repository.

## Safety classification

Historical outputs are not experimental evidence merely because they are
stored in CSV, PDBQT, PDF or image form. Heuristic, synthetic-feedback and
unknown-provenance artifacts are represented by `QuarantineManifest` with
`eligible_for_training=false`. The quarantine policy is in
`datasets/quarantine/policy.json`.

## Migration rule

The replacement is incremental: wrap or replace a legacy flow with typed
Research OS boundaries, compare only the parts for which a protocol exists,
and preserve the legacy source until all required dependencies and evidence
gates are satisfied.

