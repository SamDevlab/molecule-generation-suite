# APODOCK-001 v1.1 preregistration

This document records the prospective APODOCK-001 v1.1 hypothesis and
protocol before any v1.1 docking result was observed.  It is derived from the
historical v1.0.2 protocol and does not modify that protocol, its input bundle,
or its evidence.

## Background and hypothesis

The v1.0.2 prospective run recovered no determinate primary pose at the
frozen 2.0 Å threshold (`0/7`) and no determinate secondary best-of-20 pose at
that threshold (`0/7`).  The observed result is not proof of a particular
failure mechanism.  The preregistered hypothesis is narrower:

> A single higher-exhaustiveness search may improve sampling for this
> difficult apo/holo benchmark when all other scientific controls remain
> unchanged.

This is a hypothesis, not a conclusion from the future run.  Ranking-only
changes are not preregistered because the v1.0.2 outputs did not provide a
near-threshold pose to re-rank.  Receptor remodeling is not included because
it would introduce a larger structural and leakage-sensitive change.

## Frozen identity

The generated manifest is
`configs/apodock001-protocol-freeze-v1.1.json`.

- Protocol ID: `research-os.apodock001.protocol.v1.1+b1a3c7b16db63ea4`
- Protocol hash: `b1a3c7b16db63ea426202a82db2551cc07301e34ea5584bfab75706681481a9e`
- Planned run ID: `research-os.apodock001.planned-run.v2+96c21ae483c16db7`
- Parent protocol: `research-os.apodock001.protocol.v1.0.2+aa40517362e14795`
- Input bundle: `research-os.apodock001.input-bundle.v1+4be4265fa5917645`
- Analysis engine: `research-os.apodock001.analysis.v1+25ebfa66ecace1dd`

The v1.0.2 manifest and `inputs/apodock001/v1.0.2` are byte-identical to the
parent branch.  A final v1.1 `run_id` does not exist at preregistration time.

## v1.1 change surface

| Category | v1.0.2 | v1.1 | Status |
| --- | ---: | ---: | --- |
| Vina version and binary SHA-256 | 1.2.7 / `f31f774f...570644` | unchanged | frozen |
| Cohort, input bundle, chemistry, preparation | frozen | unchanged | frozen |
| Boxes, scoring, seed, CPU, num_modes | frozen / 42 / 1 / 20 | unchanged | frozen |
| Exhaustiveness | 16 | 32 | preregistered scientific change |
| Case timeout | 900 s historical adapter policy | 1800 s | preregistered operational policy |
| Retries | 0 | 0 | frozen |
| Analysis, threshold, APD-010 policy | same-frame, 2.0 Å, explicit indeterminate | unchanged | frozen |

No `energy_range` is passed.  One case receives one attempt in frozen case
order.  A failed case is recorded and the run continues without retry,
parameter adjustment, conformer regeneration, or post-result tuning.

APD-007 remains subject to the frozen evaluator's representation contract;
APD-010 remains `INDETERMINATE` when complete experimental correspondence is
unavailable.  Neither limitation is silently repaired by this preregistration.

## Execution boundary and evidence

The v1.1 freeze branch contains only identity generation, invariant
validation, command construction, and offline preflight.  The adapter's
`execute_prospective` method is intentionally unavailable here.  Preflight
must report `READY_FOR_EXPLICIT_AUTHORIZATION`, `execution_authorized: false`,
`run_id: null`, empty results/scores/poses, and
`evidence_scaffold_status: NOT_EXECUTED`.

A future execution branch must preserve the protocol, planned run identity,
tool identity, prepared artifact manifests, exact commands, stdout/stderr,
raw outputs and hashes, raw-results seal, run manifest, and post-seal analysis
manifest.  Analysis is permitted only after the raw-results seal is verified.

This evaluator/protocol was frozen before the first APODOCK-001 v1.1
prospective docking result was observed.
