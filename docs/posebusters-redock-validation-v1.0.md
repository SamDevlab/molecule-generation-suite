# PoseBusters redock validation v1.0

Status: **protocol frozen before PoseBusters outcome interpretation**.

## Purpose

This benchmark adds an orthogonal validation axis to REDOCK-001 and REDOCK-002. The existing redocking benchmarks answer primarily whether the Vina rank-1 pose is localized near the crystallographic ligand. PoseBusters is used here to assess whether those already-generated rank-1 poses are also physically and chemically plausible.

No docking is repeated for this benchmark. No pose is repaired, minimized, reranked or otherwise modified before validation.

## Frozen input cohort

Exactly ten rank-1 poses are evaluated:

- five `RDK-*` poses from REDOCK-001 v1.2;
- five `HLD-*` poses from REDOCK-002 Astex holdout v1.0.

Source scientific identities:

```text
REDOCK-001 = 4c24876d0a744f28b3ff4d2792102b708d9447bfd7dd35bdfa5aaf11be1bf16b
REDOCK-002 = 8540d1acf507047af402013f9d9d5d6ad93c5ac63123b95ab2876a46ecabb00c
```

The CI source artifacts are frozen to GitHub Actions run 261:

```text
run_id = 34540186017
REDOCK-001 artifact_id = 10177251400
REDOCK-002 artifact_id = 10177125237
```

Each case uses only files already present in the frozen redocking evidence bundle:

- predicted pose: `pose_01.sdf`;
- crystallographic ligand: `native_reference.sdf`;
- receptor used by the docking benchmark: `receptor_extracted.pdb`.

## PoseBusters identity

```text
PoseBusters = 0.6.5
config = redock
redock config Git blob SHA-1 = 8bcceebd7901e06759176d3a2b6b35965033464a
max_workers = 0
full_report = false
```

The official `redock` binary report covers loading, molecular chemistry/identity, internal geometry, ring/double-bond geometry, internal energy, protein/cofactor/water distances and overlaps, plus an RMSD binary.

## Endpoints

### 1. Source localization

The canonical localization endpoint remains the Research OS REDOCK v1.2 same-frame, symmetry-aware heavy-atom RMSD. No post-docking rigid-body alignment is allowed.

The frozen ten-pose cohort contains **7/10** rank-1 poses with source same-frame RMSD <= 2 Å: 5/5 from REDOCK-001 and 2/5 from REDOCK-002.

### 2. PB-valid

`PB-valid` is the literal all-tests PoseBusters endpoint: every binary output in the official `redock` configuration must pass, including PoseBusters' own RMSD binary.

### 3. PB-plausible

`PB-plausible` is the primary plausibility endpoint for this benchmark. Every official PoseBusters `redock` binary output must pass **except the RMSD binary**.

This separation is deliberate: physical/chemical plausibility must not be conflated with localization, which is already measured independently by the corrected Research OS same-frame RMSD endpoint.

Missing or indeterminate binary outputs fail closed for both `PB-valid` and `PB-plausible` when applicable.

### 4. Combined endpoint

A pose passes the combined endpoint only when:

```text
Research OS same-frame pose-1 RMSD <= 2 Å
AND
PB-plausible = true
```

## Scientific identity

The scientific result hash contains:

- this protocol identity;
- PoseBusters version and frozen config identity;
- source benchmark scientific hashes;
- source same-frame pose-1 RMSDs;
- normalized PoseBusters binary results;
- `PB-valid`, `PB-plausible` and combined endpoint outcomes;
- aggregate counts.

It excludes local paths, runtime, stdout/stderr, artifact transport metadata, host details and dataframe formatting.

## Interpretation boundary

This benchmark can support statements about geometric/chemical plausibility of these ten already-generated docking poses under PoseBusters 0.6.5. It does not establish measured affinity, potency, selectivity, biological activity, toxicity, safety, efficacy, clinical performance or universal docking correctness.

Any methodological defect discovered after the first valid PoseBusters execution must be corrected through an explicitly versioned protocol rather than by changing the frozen inputs in response to results.
