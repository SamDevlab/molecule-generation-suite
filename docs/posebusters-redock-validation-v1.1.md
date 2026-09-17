# PoseBusters redock validation v1.1

Status: **validated on the frozen 10-pose cohort**.

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

The independent source-localization endpoint is fixed at **7/10** rank-1 poses with Research OS same-frame RMSD <= 2 Å.

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

## Validated result — run 272

The first successfully completed v1.1 scientific execution after the final implementation guard fix was GitHub Actions run **272** (`34542598641`) on frozen head `34c20c2ac70cbab70bba095bba7c0e1e8f246d90`.

```text
source same-frame RMSD <= 2 Å = 7/10
PB-plausible                    = 10/10
PB-valid                        = 7/10
localized AND PB-plausible      = 7/10
scientific_result_hash          = 6d2a165eca8104e3700d7be3963274afec7795eca95d05d58eafb2475723ce01
artifact_id                     = 10177834738
artifact_sha256                 = 13e44f76c43c424d97995b4568e13b31c50b3ac8e6deaa74a53e244386b3cf08
```

Per-case outcome:

| Case | Source pose-1 RMSD (Å) | PB-plausible | PB-valid | Non-passing PoseBusters binaries |
| --- | ---: | --- | --- | --- |
| RDK-001 | 0.556594 | PASS | PASS | none |
| RDK-002 | 0.313450 | PASS | PASS | none |
| RDK-003 | 1.514788 | PASS | PASS | none |
| RDK-004 | 1.360666 | PASS | PASS | none |
| RDK-005 | 0.854407 | PASS | PASS | none |
| HLD-001 | 0.617957 | PASS | PASS | none |
| HLD-002 | 9.786177 | PASS | FAIL | PoseBusters RMSD only |
| HLD-003 | 9.163211 | PASS | FAIL | PoseBusters RMSD only |
| HLD-004 | 1.249656 | PASS | PASS | none |
| HLD-005 | 3.233724 | PASS | FAIL | PoseBusters RMSD only |

All ten cases satisfy every non-RMSD binary in the official PoseBusters `redock` configuration, including molecule loading/sanitization, formula/bond identity, radical checks, stereochemical checks, bond lengths/angles, ring/double-bond geometry, internal clashes/energy, and protein/cofactor/water distance and overlap checks.

The three PB-valid failures are exactly the three source cases whose rank-1 same-frame localization exceeds 2 Å. No additional physical/chemical failure was observed after representation normalization.

### Coordinate-preservation audit

All ten chemistry-restoration records report:

```text
max_heavy_atom_coordinate_delta_angstrom = 0.0
```

For every case, restored formula equals both the starting-conformer formula and frozen native-reference formula. Crystallographic coordinates were not used for the restoration mapping, and no rigid fit or minimization was performed.

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

Run 269 is preserved as a pre-result implementation failure: a formula guard removed explicit hydrogens without restoring implicit-H state and terminated before any v1.1 PoseBusters scientific report was produced. The corrected guard was frozen before run 272 interpretation.

## Interpretation

The result supports a clear separation between pose plausibility and pose localization for this cohort. All ten frozen rank-1 poses are physically/chemically plausible under PoseBusters 0.6.5 after lossless heavy-coordinate chemistry restoration, while only seven of ten are correctly localized within the independent 2 Å same-frame endpoint.

Thus the dominant observed limitation in this 10-pose cohort is **pose localization/ranking**, not a detectable PoseBusters physical/chemical plausibility failure.

## Interpretation boundary

The benchmark can support claims only about localization and PoseBusters plausibility of these ten frozen rank-1 docking poses after lossless heavy-coordinate chemistry restoration. It does not establish measured affinity, potency, selectivity, biological activity, toxicity, safety, efficacy, clinical performance or universal docking correctness.
