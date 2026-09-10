# PoseBusters redock validation v1.1

Status: **frozen before v1.1 PoseBusters outcome interpretation**.

## Purpose

v1.1 validates physical/chemical plausibility of the exact ten Vina rank-1 heavy-atom poses already frozen by REDOCK-001 v1.2 and REDOCK-002 v1.0. It supersedes v1.0 only because v1.0 passed chemically degraded PDBQT-to-SDF round-trip representations directly to PoseBusters.

No docking is repeated. No rank is changed. No Vina score or REDOCK RMSD is changed.

## Frozen source cohort

```text
GitHub Actions source run = 261 / 34540186017
REDOCK-001 scientific_result_hash = 4c24876d0a744f28b3ff4d2792102b708d9447bfd7dd35bdfa5aaf11be1bf16b
REDOCK-002 scientific_result_hash = 8540d1acf507047af402013f9d9d5d6ad93c5ac63123b95ab2876a46ecabb00c
REDOCK-001 artifact_id = 10177251400
REDOCK-002 artifact_id = 10177125237
```

The independent source-localization endpoint is already fixed at **7/10** rank-1 poses with Research OS same-frame RMSD <= 2 Å.

## Frozen chemistry-restoration rule

For each case:

1. load `pose_01.sdf` only as the source of docked heavy-atom coordinates/connectivity;
2. load `starting_conformer.sdf` as the known pre-docking ligand chemistry template;
3. remove hydrogens from both for graph correspondence;
4. require an exact element-labeled heavy-atom connectivity isomorphism using the same REDOCK normalization that ignores bond-order/protonation annotations lost by PDBQT;
5. choose the lexicographically first exact graph mapping, without using crystallographic coordinates;
6. copy every docked heavy-atom coordinate exactly onto the corresponding atom of the pre-docking chemistry template;
7. perform **no translation, rotation, fitting, optimization or minimization**;
8. clear template stereochemical labels and reassign stereochemistry from the resulting docked 3D coordinates;
9. require RDKit sanitization to succeed;
10. require the pre-docking template formula/connectivity to match the frozen native reference chemistry before PoseBusters evaluation.

The implementation fails closed if the mapping is absent/ambiguous beyond the bounded enumeration, if chemistry does not match the frozen reference, or if restoration cannot sanitize.

For every case the audit record includes the atom mapping and must report:

```text
max_heavy_atom_coordinate_delta_angstrom = 0.0
crystal_coordinates_used_for_mapping = false
rigid_fit_performed = false
minimization_performed = false
```

Chemistry-restored SDFs are uploaded as audit artifacts but their serialization bytes are not part of scientific identity.

## PoseBusters identity

```text
PoseBusters = 0.6.5
config = redock
redock config Git blob SHA-1 = 8bcceebd7901e06759176d3a2b6b35965033464a
max_workers = 0
full_report = false
```

## Endpoints

### Source localization

Research OS REDOCK v1.2 same-frame symmetry-aware rank-1 heavy-atom RMSD <= 2 Å. This remains independent and immutable.

### PB-valid

Every official PoseBusters `redock` binary output passes, including PoseBusters' RMSD binary.

### PB-plausible

Every official PoseBusters `redock` binary output **except its RMSD binary** passes. Missing/indeterminate values fail closed.

### Combined

```text
source same-frame RMSD <= 2 Å
AND
PB-plausible = true
```

## Scientific identity

The v1.1 hash includes:

- v1.1 protocol identity;
- PoseBusters version/config identity;
- frozen REDOCK source scientific hashes;
- source same-frame rank-1 RMSDs;
- deterministic chemistry-restoration metadata and atom mapping;
- normalized PoseBusters binary outcomes;
- PB-valid, PB-plausible and combined outcomes;
- aggregate counts.

It excludes runtime, machine/path metadata, logs/stdout, artifact transport metadata and SDF writer bytes.

## Audit history

PoseBusters v1.0 run 263 and hash `432a9ac17bc06a0709ecd897ae6c4955eedb3b37b8528803d5fff7a578564087` are preserved as invalidated history. v1.1 is a protocol version change made because of the representation defect, not because any specific pose was selected for a more favorable outcome.

## Interpretation boundary

The benchmark can support claims only about localization and PoseBusters plausibility of these ten frozen rank-1 docking poses after lossless heavy-coordinate chemistry restoration. It does not establish measured affinity, potency, selectivity, biological activity, toxicity, safety, efficacy, clinical performance or universal docking correctness.
