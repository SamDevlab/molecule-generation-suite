# Legacy Research Engineering Hardening

This document defines how the historical `Biolab/` and `formolecular/` trees are handled after Research OS 5.1 became the canonical architecture.

## Why this exists

The repository contains technically substantive pre–Research OS experiments: molecular preparation, docking campaigns, molecular generation, descriptor pipelines, ML models and result artifacts. They are useful audit inputs, but they were created before the current evidence, provenance, lifecycle and fail-closed contracts.

The hardening goal is **not** to rewrite history or retroactively label old results as validated. The goal is to preserve the material while moving reusable ideas into reproducible Research OS workflows.

## Canonical vs legacy

### Canonical

New scientific execution belongs under `src/research_os/` and should use:

- explicit input/config schemas;
- engine manifests and capability checks;
- content hashes and provenance;
- `GateStatus` / `EvidenceLevel` boundaries;
- fail-closed behavior and `FIRST_LOSS`;
- held-out or external validation when ML claims require generalization;
- run packages that can be verified and compared.

### Legacy

`Biolab/` and `formolecular/` are preserved as exploratory/audit trees. Their outputs do not become Research OS Evidence merely because the files are versioned in the repository.

## Immediate corrections

### Legacy ML

`formolecular/g_oraculo_farma.py` historically predicted `Score_QED` from molecular fingerprints and descriptors while presenting R² with clinical language. That interpretation is invalid because:

1. QED is directly calculable from molecular structure;
2. R² is a model metric, not clinical confidence;
3. a random molecular split can inflate performance when structurally related molecules occur on both sides.

The hardened legacy path therefore:

- describes the model as a **QED surrogate benchmark**;
- uses a scaffold-group holdout with zero structural-group overlap;
- reports MAE, RMSE and R² as model metrics only;
- ranks screening output by direct RDKit QED;
- retains the ML prediction only as a diagnostic comparison;
- describes PAINS/BRENK as structural-alert filters rather than toxicity or safety tests.

This is still a legacy benchmark, not an experimental validation.

### Dependencies

The main package remains intentionally small. Historical Python dependencies are declared in an optional group:

```bash
python -m pip install -e ".[legacy]"
```

The group covers the Python libraries used by the retained analysis/ML/reporting scripts. External binaries and scientific engines remain separate capabilities.

### External executables

Machine-specific paths such as a developer-local OpenBabel installation are not part of the supported Research OS contract.

The canonical preflight is:

```bash
research-os legacy-preflight Biolab
```

Resolution order is:

1. explicit `RESEARCH_OS_VINA_EXECUTABLE` / `RESEARCH_OS_OPENBABEL_EXECUTABLE` path, matching the canonical engine adapters;
2. explicitly supported bundled Vina candidate in `Biolab/`;
3. executable found on `PATH`.

An invalid explicit override fails closed and does not silently select another binary.

Passing this preflight means only that executables were resolved. It does **not** validate a docking method.

## Migration map

Historical responsibilities should migrate into the current architecture rather than creating a second framework:

| Historical concern | Canonical Research OS target |
| --- | --- |
| molecular parsing/descriptors | `research_os.molecule` |
| fingerprint/ML representations | `research_os.ml` / experiment adapters |
| Vina execution | `research_os.engines.vina` |
| docking protocol/gates | `research_os.docking` |
| experiment orchestration | `research_os.experiments` |
| dataset provenance | dataset registry + run package |
| metrics/generalization | registered metrics + held-out protocol |
| reports | evidence/run package, not free-form claim promotion |

Do not create `src/featurization`, `src/models`, etc. as parallel top-level frameworks when the same responsibility already has a Research OS home.

## Docking validation target: redocking

The next high-value docking benchmark is **redocking against experimentally resolved protein–ligand complexes**.

### Scientific question

Can the declared docking preparation and Vina protocol reproduce the crystallographic ligand pose under a frozen redocking setup?

### Primary endpoint

Heavy-atom pose RMSD between the best declared predicted pose and the crystallographic reference pose.

### Required reporting

- per-complex PDB identifier and ligand identifier;
- source/provenance of the experimental structure;
- reference ligand hash;
- prepared receptor/ligand hashes;
- grid definition and how it was obtained;
- Vina/OpenBabel versions;
- seed, exhaustiveness, CPU and number of modes;
- RMSD for every tested complex;
- full RMSD distribution;
- descriptive fraction with RMSD <= 2 Å;
- failures and exclusions, without dropping them silently.

### Interpretation boundary

A successful redocking result supports **pose-reproduction performance for the tested protocol and complexes**. It does not establish binding affinity, biological activity, efficacy, toxicity, clinical performance or universal docking accuracy.

### Anti-leakage / anti-tuning rule

Protocol parameters and the complex list must be frozen before reading benchmark outcomes. If a complex fails because of preparation, chemistry or engine limitations, the failure remains in the audit record. Any subsequent protocol revision becomes a new benchmark version.

## Research-engineering acceptance ladder

The historical project should be considered progressively hardened only when these stages are satisfied:

1. **Boundary hardening** — legacy status and claim limits are explicit.
2. **Environment hardening** — dependencies/executables are discoverable without a developer-specific machine path.
3. **ML hardening** — molecular generalization uses structural/external splits and correct metrics.
4. **Docking validation** — redocking benchmark reports pose RMSD on frozen public complexes.
5. **Reproducibility** — a third party can clone, install, run a reference workflow and verify a known run package.
6. **Legacy migration** — reusable logic moves into `src/research_os/`; historical scripts remain only as audit inputs.

This ladder is intentionally stricter than “the script runs.” The target is a reproducible scientific software system, not a collection of impressive-looking outputs.
