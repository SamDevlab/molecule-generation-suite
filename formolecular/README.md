# formolecular — legacy exploratory workflows

`formolecular/` contains historical molecular-generation and ML experiments from before Research OS became the canonical architecture. The directory is retained for auditability and migration, not as the current scientific source of truth.

## Scientific boundary

Legacy model scores are model outputs, not clinical confidence. Molecular ranking, QED, structural alerts, docking scores and surrogate predictions do not establish efficacy, safety, ADMET performance or experimental validation.

`g_oraculo_farma.py` has been hardened to make this distinction explicit:

- QED is treated as a directly computable RDKit descriptor;
- the XGBoost model is retained only as a **QED surrogate benchmark**;
- evaluation uses a structural-group holdout rather than a purely random train/test split;
- MAE, RMSE and R² are reported as model metrics only;
- screening ranks by direct RDKit QED and keeps the surrogate prediction as a diagnostic field;
- PAINS/BRENK are described as structural-alert filters, not proof of toxicity or safety.

## Installation

The legacy Python stack is explicitly declared as an optional dependency group:

```bash
python -m pip install -e ".[legacy]"
```

External scientific engines remain separate capabilities and must be validated independently.

## Canonical path

New work should use modules under `src/research_os/`, especially the declarative experiment engine, molecule adapters, docking lab, evidence model, provenance and fail-closed gates. Legacy scripts should migrate incrementally rather than being treated as equivalent to Research OS runs.
