# Research OS 5.1

**Reproducible scientific execution with explicit evidence, provenance, fail-closed gates, and auditable research workflows.**

Research OS is a Python research infrastructure for running computational studies without silently turning heuristics, ML predictions, simulations, or model-generated text into stronger scientific evidence than they actually are.

This repository started as `molecule-generation-suite`, combining molecular docking and ML experiments. Those legacy trees are still preserved for audit and migration, but the primary project is now **Research OS 5.1**.

> Research OS does not claim clinical validation, experimental validation, universal generalization, or scientific truth. Computational outputs remain computational; physics simulations remain distinct from experiments; ML and language-model output do not automatically become Evidence.

## Why Research OS exists

Scientific software often fails in a subtle way: a pipeline continues after a missing dependency, an ML score is presented as confidence, a docking score is described as efficacy, or an unavailable physical model is replaced by a convenient heuristic.

Research OS is designed around the opposite behavior:

- **fail closed** when the required evidence or engine is unavailable;
- record the **first loss** (`FIRST_LOSS`) instead of hiding downstream uncertainty;
- distinguish deterministic calculations, ML, simulations, curated observations, and validated experiments;
- preserve provenance, conditions, hashes, versions, lineage, limitations, and decision history;
- allow an Oracle/LLM to plan or explain work without letting it fabricate scientific Evidence;
- keep runs reproducible and auditable through manifests, bundles, registries, and an immutable Ledger.

## Architecture

Research OS is split into four major layers:

```text
┌──────────────────────────────────────────────────────────────┐
│  Oracle / Knowledge / Campaigns / Research Programs         │
│  planning, retrieval, prioritization, explanation           │
└───────────────────────────────┬──────────────────────────────┘
                                │ typed requests
┌───────────────────────────────▼──────────────────────────────┐
│  Scientific Labs                                             │
│  Molecule · Pharma · Docking · Fuel · Combustion            │
│  Propulsion · Metal · Thermal · Degradation                 │
└───────────────────────────────┬──────────────────────────────┘
                                │ engine contracts
┌───────────────────────────────▼──────────────────────────────┐
│  Scientific / computational engines                         │
│  RDKit · AutoDock Vina · Open Babel · Cantera              │
│  pycalphad · pymatgen · matminer · reference engines        │
└───────────────────────────────┬──────────────────────────────┘
                                │ evidence + provenance
┌───────────────────────────────▼──────────────────────────────┐
│  Proof / Evidence / Bundles / Ledger                         │
│  gates · FIRST_LOSS · hashes · lineage · sealed runs        │
└──────────────────────────────────────────────────────────────┘
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the detailed boundary model.

## Evidence model

Research OS uses explicit evidence levels:

| Level | Meaning |
|---|---|
| `E0_HEURISTIC` | heuristic, assumption, or unvalidated estimate |
| `E1_ML` | machine-learning output under a declared model/data protocol |
| `E2_COMPUTATIONAL` | deterministic or computational result |
| `E3_PHYSICS` | result from an attributable physical/scientific simulation protocol |
| `E4_CURATED_EXPERIMENTAL` | curated experimental observation with provenance |
| `E5_VALIDATED_EXPERIMENTAL` | independently validated experimental evidence |

The levels are **not additive**. Multiple E2 results do not become E3, and repeated simulations do not become experimental evidence.

Gate outcomes are also explicit:

```text
PASS
FAIL
INDETERMINATE
OUT_OF_DOMAIN
INSUFFICIENT_EVIDENCE
SKIPPED
```

A run stops or becomes non-passing at the first non-`PASS` result instead of continuing with a fabricated fallback.

## Run lifecycle

Evidence-producing Labs follow a staged lifecycle:

```text
CREATED
   ↓
RUNNING
   ↓
preflight gates
   ↓
scientific calculation / engine execution
   ↓
Evidence + provenance + result gates
   ↓
COMPLETED
   ↓
SEALED (when persisted as immutable research state)
```

A successful preflight is therefore not enough to mark a scientific run complete. If the engine or calculation fails after validation, the run records `FAIL` or `INDETERMINATE` instead of preserving a false PASS.

## Scientific Labs

### MoleculeLab

- deterministic RDKit molecular characterization;
- canonical molecular representation;
- molecular descriptors and QED;
- Morgan fingerprints kept separate as ML representation rather than physical evidence.

### DockingLab

- AutoDock Vina execution through an explicit engine contract;
- receptor/ligand hashes;
- grid, seed, exhaustiveness, target and protocol metadata;
- docking remains `E2_COMPUTATIONAL` and is never treated as measured binding affinity or clinical efficacy.

### PharmaLab

- molecular characterization through `MoleculeLab`;
- optional docking through `DockingLab`;
- explicit claim boundaries for efficacy, safety, ADMET, and clinical interpretation.

### FuelLab

- explicit composition, fraction basis, conditions, and provenance;
- molecular delegation without treating fuel performance as an intrinsic molecular property.

### CombustionLab

- Cantera-backed equilibrium protocol;
- physics evidence only when the configured physical engine actually executes;
- missing mechanism or engine produces an explicit non-pass state rather than a substitute estimate.

### PropulsionLab

- consumes combustion Evidence;
- bounded ideal isentropic nozzle model;
- no fallback to historical `sqrt(energy / mass)` heuristics;
- preserves model limitations such as geometry, pressure thrust, heat loss, boundary layers, and hardware effects.

### MetalLab

- explicit alloy composition and fraction basis;
- deterministic composition descriptors;
- optional material feature engines;
- CALPHAD remains fail-closed when a thermodynamic engine/database is unavailable.

### ThermalLab

- bounded steady 1-D Fourier conduction model;
- assumptions and omitted heat-transfer modes are preserved with the result.

### DegradationLab

- evidence-first degradation/corrosion records;
- does not invent corrosion rate, embrittlement, oxidation life, creep, or fatigue from material names alone;
- experimental levels require attributable experimental/publication/dataset/database provenance.

### KnowledgeLab

- source-located Zettelkasten records;
- review status remains separate from EvidenceLevel;
- verified training/RAG records require traceable source locators.

See [`LAB_REGISTRY.md`](LAB_REGISTRY.md) and [`ENGINE_REGISTRY.md`](ENGINE_REGISTRY.md) for the current capability registries.

## ML validation

Research OS separates model validation from scientific evidence promotion.

Supported split strategies include:

- random;
- Murcko scaffold;
- cluster;
- source;
- group;
- temporal;
- explicit external test sets.

Model artifacts can retain dataset, schema, metric, split, environment, and training-run lineage. A high R² is a model metric; it is not described as clinical confidence or experimental validation.

See [`MODEL_REGISTRY.md`](MODEL_REGISTRY.md) and [`DATASET_REGISTRY.md`](DATASET_REGISTRY.md).

## Declarative Experiment Engine

Research OS 5.1 adds the first domain-neutral declarative experiment path. A strict YAML/JSON protocol can select registered dataset, split, model and metric adapters without embedding arbitrary executable hooks in the protocol.

The reference CLI surface is:

```bash
research-os run experiment protocol.yaml --output runs
research-os run experiment-verify runs/EXPERIMENT-ID
research-os run experiment-inspect runs/EXPERIMENT-ID
research-os run experiment-compare runs/A runs/B
```

Successful runs emit an auditable package with the protocol, metrics, provenance, evidence, environment, hashes and report. Scientific identity is kept separate from document labels/locations and from execution identity, while implementation provenance is explicitly hashed and verified.

The v1 declarative protocol intentionally exposes a small generic regression route rather than pretending to support arbitrary scientific domains. See [`docs/research-os-5.1-declarative-experiment-engine.md`](docs/research-os-5.1-declarative-experiment-engine.md).

## Installation

Python **3.10+** is required. CI currently exercises Python 3.11 and 3.12.

Install the core development + molecular/data environment:

```bash
python -m pip install -e ".[dev,molecule,data]"
```

Optional scientific capabilities are separated by extras:

```bash
python -m pip install -e ".[combustion]"
python -m pip install -e ".[docking]"
python -m pip install -e ".[metals]"
python -m pip install -e ".[materials]"
python -m pip install -e ".[science]"
```

Some workflows also require external engines, databases, mechanisms, or binaries. Research OS treats those dependencies as explicit capabilities; absence should produce an attributable non-pass result instead of a silent approximation.

## Run the tests

```bash
python -m pip check
python -m compileall -q src tests
pytest -q
```

GitHub Actions runs the test suite on Python 3.11 and 3.12.

## Minimal example

```python
from research_os.molecule.lab import MoleculeLab

run = MoleculeLab().run({"smiles": "CCO"})

print(run.status)
print(run.first_loss)

if run.passed:
    print(run.evidence[0].payload)
```

The important output is not only the property value. The run also carries the protocol state, gates, EvidenceLevel, engine identity/version, provenance, and reproducibility metadata required by the workflow.

## Oracle boundary

Research OS can use a structured Oracle/Codex layer for discovery, planning, ranking registered information, and explaining results.

The Oracle cannot silently:

- create scientific Evidence;
- raise an EvidenceLevel;
- invent a source, dataset, engine execution, run, condition, or claim;
- bypass fail-closed scientific gates.

Scientific truth remains owned by registered data, Labs, engines, Evidence, bundles, and the Ledger.

## Reproducibility and research state

The project includes infrastructure for:

- run manifests;
- input/output hashes;
- environment capture;
- dataset/model/engine registries;
- immutable/sealed runs;
- lineage and rerun relationships;
- research bundles;
- longitudinal scientific memory;
- external evidence updates;
- reproduction/stress tests;
- bounded research campaigns and programs.

Generated local state is intentionally separated from source code. Only selected canonical validation artifacts are versioned when they are part of the reproducibility or acceptance record.

## Legacy migration

The historical directories remain available as audit inputs:

```text
Biolab/
formolecular/
```

Their original scripts are not the architectural source of truth for new Research OS flows.

Examples of corrected legacy assumptions include:

- QED, TPSA, molecular weight, LogP, and directly calculable descriptors belong on deterministic computational paths rather than being presented as discovered biological truth;
- docking score does not establish efficacy or measured affinity;
- R² is not "clinical confidence";
- specific impulse is not treated as an intrinsic molecular property;
- missing engines or experimental observations do not become PASS through heuristic replacement.

## Current release

The package version is **5.1.0**.

Research OS 5.1 promotes the Declarative Experiment Engine into the integrated release while preserving the Research OS 5.0 evidence/proof architecture and fail-closed scientific boundaries.

Release acceptance and the preserved validation record are documented in:

- [`RELEASE_NOTES_V5_1.md`](RELEASE_NOTES_V5_1.md)
- [`docs/research-os-5.1-declarative-experiment-engine.md`](docs/research-os-5.1-declarative-experiment-engine.md)
- [`RESEARCH_OS_V5_VALIDATION_REPORT.md`](RESEARCH_OS_V5_VALIDATION_REPORT.md)
- [`SCIENTIFIC_EVIDENCE_MODEL.md`](SCIENTIFIC_EVIDENCE_MODEL.md)
- [`SECURITY_AUDIT_V5_0.md`](SECURITY_AUDIT_V5_0.md)

The 5.0 release notes and milestone documents remain in the repository for auditability; they are no longer the current release narrative.

## Scientific limits

Research OS is research infrastructure, not a substitute for domain validation.

In particular:

- docking is protocol-dependent computational evidence;
- ML inherits the coverage, bias, leakage risk, and uncertainty of its datasets and validation design;
- physical simulation depends on its equations, mechanism/database, conditions, boundary assumptions, and engine implementation;
- generated molecules require chemical and experimental validation;
- computational prioritization does not establish safety, efficacy, manufacturability, stability, or regulatory suitability;
- language-model output is not promoted to scientific Evidence by narration alone.

The desired behavior when the system cannot support a claim is a traceable **`INDETERMINATE`**, **`OUT_OF_DOMAIN`**, or **`INSUFFICIENT_EVIDENCE`** result—not an impressive-looking guess.
