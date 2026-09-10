# Research OS 5.1.0

Research OS 5.1.0 promotes the Declarative Experiment Engine into the integrated Research OS line while preserving the evidence, provenance, fail-closed gates, FIRST_LOSS semantics, bundles and Ledger architecture established in 5.0.

## Highlights

### Declarative Experiment Engine

A strict `research-os.declarative-experiment.v1` YAML/JSON protocol can orchestrate a domain-neutral numeric regression experiment through registered components only:

- dataset adapter;
- split strategy;
- model adapter;
- metrics;
- evidence gates;
- provenance and run-package generation.

Protocols do not embed arbitrary Python import paths or executable hooks.

### CLI

The installed CLI now supports:

```text
research-os run experiment protocol.yaml --output runs
research-os run experiment-verify runs/EXPERIMENT-ID
research-os run experiment-inspect runs/EXPERIMENT-ID
research-os run experiment-compare runs/A runs/B
```

Existing Research OS commands remain delegated to the preserved legacy CLI implementation.

### Auditable run packages

A successful declarative run emits:

- `manifest.json`
- `protocol.yaml`
- `metrics.json`
- `provenance.json`
- `evidence.json`
- `environment.json`
- `hashes.json`
- `report.md`

Verification recalculates protected identities and fails closed on tampering or incompatible methodology.

### Reproducibility identities

Research OS 5.1 separates several meanings that were previously easy to conflate:

- full protocol/document integrity;
- scientific protocol identity;
- scientific result identity;
- implementation identity;
- execution/environment identity;
- methodological compatibility.

The reference protocol reproduced the same scientific result and implementation identities on Python 3.11 and Python 3.12 while producing distinct execution hashes for the different runtimes.

Reference identities validated before release:

```text
scientific_protocol_hash = c6e2963ce0903359eab8d24fc1d9e8aa24544b43b6afc5da8053ca5a22d32bec
scientific_result_hash   = f7baa41b7f07ed07f1225e15e7619b0d1350ea918d370f1d05ddbde500c60ef2
compatibility_hash       = 835e0afaa23103f146909eeb8d9d2f6d0b3eda2671637c4e1cfcd568aae7c33d
split_membership_hash    = aaa79d379fa3f35c2931a3884f1988822b1b22d8692f92baaae6712db56c15ee
implementation_hash      = 7a45b51a3748ba473b9ecf3dfa326e6ecbdaef0144553ff8bf9206b2ba1217ce
```

Observed execution hashes:

```text
Python 3.11 = 243fa86a4ea15d782da35b1e5dce9a9876d679e2c87fb81e885c0a7af13f9716
Python 3.12 = f5fe0da7e6be79b6f0885a42cd6018f61f526059164632ad4414d0645de0e5e1
```

### Hardening included before release

The 5.1 review fixed and tested:

- scientific identity portability across experiment labels and file locations;
- deterministic resolution of relative dataset paths against the protocol location only;
- explicit implementation-source hashing and aggregate `implementation_hash`;
- rejection of duplicate YAML and JSON keys;
- rejection of unsafe/path-traversing experiment IDs;
- rejection of non-finite or non-numeric values by the numeric CSV adapter;
- fail-closed behavior for unregistered execution components;
- preservation of the historical Research OS security audit boundary.

## Validation

The feature integration commit was merged into `research-os-v1.3` as:

```text
de0cee5deab7adb8648971ba37f5b9e3c6f63959
```

Post-merge GitHub Actions run **218** executed directly on `research-os-v1.3` and passed:

- Python 3.11: `397 passed, 1 skipped`;
- Python 3.12: `397 passed, 1 skipped`;
- Cantera reference capability: PASS;
- `pip check`: PASS;
- `compileall`: PASS;
- installed declarative reference run twice: PASS;
- `experiment-verify`: PASS;
- `experiment-inspect`: PASS;
- `experiment-compare`: PASS;
- identical rerun MAE/RMSE/R² deltas: `0.0`.

## Scope boundary

The v1 declarative protocol deliberately proves a small generic regression path. Research OS 5.1 does **not** claim that arbitrary scientific domains can already be represented declaratively.

The release does not promote computational output to experimental evidence and does not alter the evidence-level semantics established in Research OS 5.0.

The earlier ONLINE-EXP solubility studies remain separate research history and were not rewritten as part of this release.

## Next direction

The natural next milestone is multi-domain validation: demonstrate that the declarative engine can support a second genuinely different problem class without introducing domain knowledge into its core orchestration layer.
