# MOLDISC-005 — Bounded NCT N-alkyl analog series

Status: **protocol frozen before the first generated-analog evidence profile is inspected**

## Why this program exists

MOLDISC-003 selected NCT because its exact canonical structure is represented in
AqSolDB.

MOLDISC-004 then showed a critical limitation: the frozen ESOL predictor calls
NCT `IN_DOMAIN`, but underpredicts the exact measured source observation by
about `2.31` logS units.

MOLDISC-005 therefore resumes molecule generation without pretending that the
largest ESOL-predicted logS is a trustworthy winner.

## Frozen seed

- REDOCK-003 case: `ATX-014`
- PDB: `1P2Y`
- CCD ligand: `NCT`
- target label: `CYTOCHROME P450-CAM`
- canonical SMILES: `CN1CCCC1c1cccnc1`
- InChIKey: `SNICXCGAKADSCV-UHFFFAOYSA-N`
- exact AqSolDB source: `E-468`
- recorded seed logS: `0.79`

## Frozen generator

Generator identity:

`research-os.molecular-discovery.nct-n-alkyl-series.v1`

NCT contains one exocyclic N-methyl substituent on its saturated ring nitrogen.

Exactly three generated variants are predeclared:

1. `N-H`: remove the seed N-methyl substituent;
2. `N-ETHYL`: extend the seed N-methyl substituent by one carbon;
3. `N-PROPYL`: extend it by two carbons.

The generator:

- changes only this frozen N-substituent series;
- sanitizes with RDKit;
- canonicalizes each product;
- requires each product to be unique and non-seed;
- assigns a deterministic generation hash;
- labels every generated analog `E0_HEURISTIC`.

No downstream property, prediction or AqSolDB match participates in generation.

## Dual evidence

The seed plus three generated analogs are evaluated through two independent
solubility lenses.

### Frozen ESOL capability

For every structure, retain:

- molecular validity;
- predicted logS;
- maximum training Tanimoto;
- inherited AD threshold;
- `IN_DOMAIN` / `OUT_OF_DOMAIN` status.

Because MOLDISC-004 observed a large measured-anchor error on NCT,
**absolute ESOL prediction is not a selection score in MOLDISC-005**.

### Immutable AqSolDB coverage

For every structure, retain:

- nearest unique AqSolDB Morgan/Tanimoto similarity;
- historical similarity bin;
- count of neighbors at >=0.4;
- nearest measured-source structure and its recorded logS.

The same pre-existing `0.4` boundary is used.

## Frozen generated-analog follow-up rule

The NCT seed itself is not a generated candidate and cannot win this rule.

A generated analog is eligible for a separately frozen follow-up only when:

1. MoleculeLab chemistry status is `PASS`; and
2. nearest AqSolDB Tanimoto is >= `0.4`.

If more than one generated analog is eligible:

1. highest AqSolDB nearest similarity wins;
2. exact tie -> ascending frozen variant ID.

ESOL predicted logS is **not** used in this selection.

If no generated analog reaches the boundary, MOLDISC-005 closes without a
selected generated analog.

## Docking boundary

MOLDISC-005 executes no docking.

If a later program docks an NCT analog into the PDB 1P2Y holo receptor, the
generated analog is non-cognate and the context must be declared as:

`NON_COGNATE_HOLO_CROSSDOCKING`

That context remains partially validated and E2 computational.

## Interpretation boundaries

This program does not establish:

- experimental solubility for generated analogs;
- equal solubility to a neighboring AqSolDB molecule;
- binding affinity;
- CYP activity, inhibition or metabolism;
- potency;
- efficacy;
- safety;
- synthetic accessibility;
- clinical utility.

Its purpose is to prove that molecule generation can continue while preserving
the measured-anchor model discrepancy instead of hiding it behind a composite
score.
