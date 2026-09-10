# PoseBusters redock validation v1.0

Status: **INVALIDATED for physical/chemical plausibility interpretation**.

## Audit outcome

The first execution was GitHub Actions run `263` (`34541851196`) on the prospectively frozen 10-pose cohort. It produced:

```text
source same-frame RMSD <= 2 Å = 7/10
PB-plausible                    = 0/10
PB-valid                        = 0/10
scientific_result_hash          = 432a9ac17bc06a0709ecd897ae6c4955eedb3b37b8528803d5fff7a578564087
```

The zero-PB result is retained as audit history but is not interpreted as evidence that every docked heavy-atom geometry is physically invalid.

## Methodological defect discovered after execution

v1.0 passed the direct `pose_01.sdf` files produced by the REDOCK Open Babel PDBQT-to-SDF round trip to PoseBusters. PDBQT does not preserve the full ligand chemical representation and the round trip had dropped most non-polar hydrogens / chemical valence information.

Concrete examples from the frozen run-261 evidence:

```text
RDK-001 ligand chemistry: C10H16N2O3S
RDK-001 pose_01.sdf:      C10H3N2O3S

HLD-001 ligand chemistry: C20H25ClN6O3
HLD-001 pose_01.sdf:      C20H4ClN6O3
```

Consequently every case failed PoseBusters molecular-formula and radical/identity-related checks even though all ten passed the internal bond-length, bond-angle, internal-clash, internal-energy and protein-overlap/distance checks. Several cases also became indeterminate for InChI-based identity.

This is a representation-layer mismatch: the redocking RMSD evaluator intentionally normalizes bond-order/protonation annotations because PDBQT cannot preserve them, whereas PoseBusters expects a chemically meaningful molecular representation.

## Why v1.0 is not silently repaired

The run and hash above remain recorded. The correction is explicitly versioned as PoseBusters redock validation **v1.1** rather than rewriting v1.0 after observing its outcome.

v1.1 keeps the exact same ten frozen Vina rank-1 heavy-atom poses and source benchmark identities. It restores only the known pre-docking ligand chemistry from `starting_conformer.sdf`, copies the docked heavy-atom coordinates exactly, performs no rigid fit or minimization, and reassigns stereochemistry from the docked 3D coordinates rather than forcing stereochemical labels from the template.

No REDOCK pose, ranking, score or source RMSD is changed by this correction.
