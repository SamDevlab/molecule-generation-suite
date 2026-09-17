# Legacy parity matrix (v1.8)

| Legacy flow | Research OS replacement | Parity | Status | Decision |
|---|---|---|---|---|
| `formolecular/g_oraculo_farma.py` | `MoleculeLab` + RDKit deterministic properties + `PharmaLab` | NUMERICAL only for direct descriptors | MIGRATING | QED/MW/LogP/TPSA/FractionCSP3/RotatableBonds/AromaticRings/HDonors/HAcceptors are compared under one RDKit protocol; ML ADMET is not deterministic parity |
| `formolecular/g_oraculo_aeroespacial.py` | `FuelLab -> CombustionLab -> PropulsionLab` | NONE | MIGRATING | `AERO_Impulso_Espec_Teorico` remains `HEURISTIC_REVIEW`; no numerical parity target |
| `formolecular/t_aero.py` | explicit fuel/physics protocols | NONE | MIGRATING | arbitrary efficiency/energy ranking is not revalidated |
| `formolecular/t_aero2.py` | physics engine boundary | NONE | MIGRATING | synthetic energy feedback is quarantined |
| `Biolab/fabrica_g2.py` | preparation -> `DockingLab` -> campaign -> `PharmaLab` -> Evidence -> Bundle -> Ledger | BEHAVIORAL | MIGRATING | requires real Vina/Open Babel execution, target-specific grids, species and validated protocol |

## Deterministic parity contract

`research_os.legacy.deterministic_property_parity` provides side-by-side
checks for the nine directly calculable fields. A passing comparison means
the deterministic replacement agrees under the declared RDKit version and
tolerance. It does not promote a model prediction, docking score, synthetic
candidate or clinical statement.

## Permanent regression rules

- no `SMILES -> XGBoost -> Isp` path can claim physics evidence;
- R² is retained as a model metric, never converted to confidence;
- `synthetic != experimental`, and mock outputs cannot become E3;
- resubstitution scoring is not validation;
- missing species is `UNKNOWN`, never implicitly human;
- `INDETERMINATE` and `OUT_OF_DOMAIN` are excluded from normal ranking, not
  sorted as poor numeric scores.

