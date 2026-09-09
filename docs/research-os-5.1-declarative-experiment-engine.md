# Research OS 5.1 — Declarative Experiment Engine

Status: **frozen implementation contract**

This document defines the implementation target for Research OS 5.1 before the engine code is added. It is intentionally domain-agnostic: no chemistry, solubility, combustion, materials, docking, or other scientific-domain rule belongs in the declarative core.

## Goal

Turn reproducible experiments into a protocol-driven Research OS capability. A user should be able to describe a supported experiment in a declarative file, run it through the Research OS CLI, receive a sealed/auditable run package, verify that package later, and compare compatible runs without writing experiment-specific orchestration code.

## Protocol v1

Protocol identifier: `research-os.declarative-experiment.v1`

The v1 protocol is strict and fail-closed. Unknown top-level keys, missing required fields, unsupported adapter/model/split/metric identifiers, malformed values, and integrity mismatches must fail rather than be ignored.

Minimum contract:

```yaml
protocol: research-os.declarative-experiment.v1
experiment:
  id: REFERENCE-REGRESSION-001
  task: regression
  seed: 42

dataset:
  adapter: csv
  path: examples/data/reference-regression.csv
  target: y
  features: [x1, x2]

split:
  strategy: random
  train_fraction: 0.8

models:
  - id: ordinary_least_squares
    adapter: linear_regression

metrics: [mae, rmse, r2]

evidence:
  require_dataset_hash: true
  require_protocol_hash: true
  fail_closed: true
```

YAML is the human-facing representation. JSON with the same schema is also accepted. YAML support is an explicit core dependency in 5.1 rather than an optional scientific capability.

## Generic interfaces

The declarative core must expose generic, registered interfaces for:

- `DatasetAdapter`
- `SplitStrategy`
- `ModelAdapter`
- `Metric`
- experiment gates / integrity requirements
- run-package generation and verification

The registry is explicit. Protocols may refer only to registered identifiers; arbitrary Python import paths or executable hooks are forbidden in protocol v1.

## V1 built-ins

To prove the architecture without coupling it to chemistry, v1 includes a minimal dependency-light regression path:

- dataset adapter: numeric CSV
- split strategy: deterministic seeded random holdout
- model adapter: ordinary least squares implemented in the core without scikit-learn
- metrics: MAE, RMSE, R²

This built-in path is a reference capability, not a claim that all scientific domains should use linear regression.

## CLI surface

5.1 extends the existing `research-os run` namespace instead of creating a second CLI:

```text
research-os run experiment protocol.yaml --output runs
research-os run experiment-verify runs/REFERENCE-REGRESSION-001
research-os run experiment-inspect runs/REFERENCE-REGRESSION-001
research-os run experiment-compare runs/A runs/B
```

`experiment-compare` must fail closed when the two run packages are not methodologically compatible. At minimum, protocol version, task, dataset schema identity, feature names, target name, split strategy, model identifiers/configuration, and metric set participate in the compatibility identity. Dataset content hashes may differ so the command can compare reruns on separately materialized but schema-compatible data; the difference must be reported, never hidden.

## Run package

A successful declarative run writes one directory per run containing at least:

```text
manifest.json
protocol.yaml
metrics.json
provenance.json
evidence.json
environment.json
hashes.json
report.md
```

The package records:

- experiment/run identity
- normalized protocol and protocol SHA-256
- input dataset SHA-256
- dataset schema identity
- deterministic split membership hash
- model configuration and fitted-model identity
- metrics
- environment details sufficient for execution auditing
- per-artifact hashes
- a scientific-result hash distinct from the execution/environment hash

`hashes.json` itself is excluded from its per-artifact hash map to avoid recursive hashing.

## Reproducibility semantics

- Scientific identity is based on normalized scientific inputs/results, not wall-clock time or platform metadata.
- Execution identity includes environment/runtime metadata.
- The same protocol + dataset + seed + implementation must reproduce the same split membership and scientific-result hash.
- Any modification to a hashed run artifact must make verification fail.
- Time stamps may exist for auditability but must not participate in scientific identity.

## Safety / fail-closed rules

Protocol v1 must not execute shell commands, evaluate expressions, resolve arbitrary modules, download URLs, or invoke unregistered code. CSV paths are local files. Dataset values used by the built-in numeric adapter must be finite numbers. Empty datasets, duplicate headers, missing targets/features, invalid fractions, too-small splits, and non-finite model/metric outputs fail.

## Compatibility with Research OS 5.0

5.1 is additive. Existing `ResearchBundle`, ledger, golden workflows, labs, engines, dataset registry, and frozen ONLINE-EXP results are not rewritten by this milestone. The declarative run package may reuse Research OS hashing/environment primitives, but the v1 engine remains independently verifiable and does not require a domain-specific lab.

The project version remains `5.0.0` on this feature branch until the milestone is accepted for integration. This document names the target milestone; it does not perform the release bump.

## Acceptance criteria

Research OS 5.1 is implementation-complete when all of the following are true:

1. Strict YAML/JSON protocol parsing and validation are covered by tests.
2. A registry resolves only known dataset/split/model/metric identifiers.
3. A deterministic end-to-end reference regression runs from a protocol file.
4. The run emits all eight required package artifacts.
5. A second identical run reproduces split and scientific-result hashes.
6. Verification passes for an untouched package and fails after artifact tampering.
7. Compatible-run comparison succeeds and reports metric deltas.
8. Incompatible-run comparison fails closed.
9. CLI smoke tests cover run, verify, inspect, and compare.
10. Core test suite passes on supported Python versions.
11. Existing core functionality remains green.
12. No solubility- or chemistry-specific identifier is imported by the declarative engine package.

## Out of scope for 5.1

- hyperparameter search
- arbitrary plugins from protocol files
- remote dataset fetching
- classification/survival/time-series built-ins
- scheduler/distributed execution
- notebook execution
- LLM-generated executable code
- rewriting the frozen ONLINE-EXP-001 through ONLINE-EXP-005 results

Those can be evaluated after the declarative engine has demonstrated a stable, auditable core.