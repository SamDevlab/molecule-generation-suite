# MOLDISC-004 — NCT exact measured-anchor calibration

Status: **protocol frozen before the first NCT predictor comparison is inspected**

## Why this program exists

MOLDISC-003 selected `ATX-014 / PDB 1P2Y / NCT` using a predeclared
measured-solubility coverage rule.

The selected seed is unusually useful because its canonical structure has an
exact match in the immutable AqSolDB source:

- canonical SMILES: `CN1CCCC1c1cccnc1`
- InChIKey: `SNICXCGAKADSCV-UHFFFAOYSA-N`
- AqSolDB source ID: `E-468`
- recorded logS: `0.79`

MOLDISC-004 does not generate molecules yet. It first asks whether the already
frozen ESOL predictor meaningfully supports this selected seed.

## Frozen parent selection

Parent program: `MOLDISC-003 v1.0`

Parent hashes:

- RCSB identity: `62b6808bea71479a2c5c56f905cb22127a4834461500c555c902a4d7a56b39c8`
- coverage: `90bd8e99c926993cc2e0e950da246945b1db199b9b1f027e2ba2b44ff0147e35`
- program: `977428ab62ff38cda8033f5daf9ecc85e93f9f9994240ca2f13729405ab58e2b`

Selected seed:

`ATX-014 / 1P2Y / NCT / CYTOCHROME P450-CAM`

## Exact measured anchor

MOLDISC-004 re-downloads the same immutable AqSolDB source used by the prior
coverage programs and requires source record `E-468` to still have:

- the frozen NCT canonical identity;
- InChIKey `SNICXCGAKADSCV-UHFFFAOYSA-N`;
- logS exactly `0.79`.

If that source identity changes, the program fails closed.

The measured value is source evidence. AqSolDB aggregates heterogeneous
measurement protocols, so this value is not treated as a universal assay truth.

## Frozen predictor

Capability:

`research-os.molecular-discovery.solubility.esol-v2.v1`

The program requires the already accepted identities:

- ESOL dataset hash: `6de39771743dc4f15b191cffc27e1e02eb474457cc841afda565f31aff198e85`;
- training hash: `300ddc4981e1a9c2fb3735e598bcca89fb98a1cd4722cd58454e5d923781f00b`;
- AD threshold: `0.26684684684684684`.

No training example, hyperparameter, representation or applicability threshold
is changed in MOLDISC-004.

## Frozen comparison

For the single NCT seed, report:

- measured logS;
- predicted logS;
- signed error = prediction - measurement;
- absolute error;
- maximum ESOL-training Tanimoto;
- inherited applicability-domain status;
- predictor model identity.

There is deliberately **no error pass/fail threshold**. A one-compound
comparison cannot become a new validation benchmark after the result is seen.

## No generation or docking

MOLDISC-004 performs neither molecule generation nor docking.

A future analog-generation program may be opened only after this seed-level
comparison is preserved. Every generated analog must then receive its own
applicability-domain assessment; the NCT seed's status does not transfer to its
analogs.

## Interpretation boundaries

This program does not establish:

- general ESOL-model performance;
- binding affinity;
- CYP inhibition or metabolism;
- potency;
- efficacy;
- safety;
- synthetic accessibility;
- clinical utility.

Its purpose is narrower: calibrate one source-backed crystallographic seed with
an exact measured-solubility observation before candidate generation resumes.
