# External Validation Campaigns v4.3

## Locked solubility campaign

Source: DLS-100 unique public subset, downloaded from the public data file
derived from the University of St Andrews DLS-100 dataset. The exact file was
hashed before use (`7f6ba392c6208c716adb5083b095d431890eb8b805d95ed88ec0f7b0b9a67fb9`).
The source portal identifies the dataset as measured intrinsic aqueous
solubility with `log10(mol/L)` values and a CC BY-NC license context.

The V39 Morgan radius-2, 2048-bit / NumPy Ridge model was frozen. No retraining,
threshold tuning or source reuse occurred. Molecule identity overlap with the
training sample was zero. The 56-record result was:

- MAE: `1.167993` log10(mol/L)
- RMSE: `1.423244`
- bias: `-0.031516`
- R²: `0.264241`
- OOD fraction: `1.0` (`0/56` in domain)
- residual interval coverage: `0.892857`

This is a negative external-validation result for unrestricted generalization.
It does not authorize ranking the OOD compounds and does not promote the model.

## Blocked and ineligible campaigns

The RCSB 4Z0L alternate murine COX-2 structure is a legitimate structural
comparison candidate, but another docking structure remains E2 and the Vina
engine was unavailable for execution. The Cantera search did not produce an
exact E3↔E4 matched experimental record. NASA battery metadata exposed a
promising alternative artifact, but it was not downloaded and parsed here.
Public hydrogen-material sources (316L, De-Hy WP3 and an aluminum-alloy
dataset) require exact-file ingestion, license review and field-level condition
matching before any claim.

These paths remain preserved as `NO_ELIGIBLE_EXTERNAL_DATA` or
`BLOCKED_EXTERNAL`, never silently converted to success.
