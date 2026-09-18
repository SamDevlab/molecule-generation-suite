# MOLDISC-003 — Solubility-coverage scan across REDOCK-003 seeds

Status: **protocol frozen before first cohort-coverage result is inspected**

## Why this program exists

MOLDISC-001 showed that the ID5 neighborhood is outside the frozen ESOL
applicability domain.

MOLDISC-002 then showed that the exact same nine structures have no AqSolDB
neighbor at the pre-existing 0.4 Morgan/Tanimoto boundary.

MOLDISC-003 changes the **seed-selection question**, not either closed result.

It scans the 15 crystallographic ligands already frozen in REDOCK-003 and asks
which, if any, has measured-solubility structural coverage in AqSolDB.

## Frozen cohort

The cohort is exactly the 15 REDOCK-003 prospective cases:

| Case | PDB | CCD ligand | Target |
|---|---|---|---|
| ATX-001 | 1R1H | BIR | NEPRILYSIN |
| ATX-002 | 1SJ0 | E4D | ESTROGEN RECEPTOR |
| ATX-003 | 1MEH | MOA | INOSINE-5'-MONOPHOSPHATE DEHYDROGENASE |
| ATX-004 | 1V4S | MRK | GLUCOKINASE ISOFORM 2 |
| ATX-005 | 1T40 | ID5 | ALDOSE REDUCTASE |
| ATX-006 | 1PMN | 984 | MITOGEN-ACTIVATED PROTEIN KINASE 10 |
| ATX-007 | 1KZK | JE2 | PROTEASE |
| ATX-008 | 1HQ2 | PH2 | 6-HYDROXYMETHYL-7,8-DIHYDROPTERIN PYROPHOSPHOKINASE |
| ATX-009 | 1S3V | TQD | DIHYDROFOLATE REDUCTASE |
| ATX-010 | 1Z95 | 198 | ANDROGEN RECEPTOR |
| ATX-011 | 1UNL | RRC | CYCLIN-DEPENDENT KINASE 5 |
| ATX-012 | 1TOW | CRZ | FATTY ACID-BINDING PROTEIN, ADIPOCYTE |
| ATX-013 | 1UOU | CMU | THYMIDINE PHOSPHORYLASE |
| ATX-014 | 1P2Y | NCT | CYTOCHROME P450-CAM |
| ATX-015 | 1L7F | BCZ | NEURAMINIDASE |

No case is added or removed after coverage is observed.

## RCSB chemical identity

For each frozen CCD ligand ID, MOLDISC-003 retrieves its chemical component from
the RCSB PDB Data API:

`https://data.rcsb.org/rest/v1/core/chemcomp/{chem_comp_id}`

The program extracts a usable SMILES descriptor, canonicalizes it with the
active RDKit runtime and derives an active-runtime InChIKey.

The first successful program execution will freeze a scientific projection hash
over:

- case ID;
- PDB ID;
- CCD ligand ID;
- target label;
- selected RCSB SMILES;
- RDKit canonical SMILES;
- RDKit InChIKey;
- reported RCSB InChIKey when present;
- chemical name/formula/weight when present.

This protects later reproduction from silently accepting changed chemical
identities as the same program.

## AqSolDB coverage

MOLDISC-003 reuses the already integrated capability:

`research-os.molecular-discovery.aqsoldb-coverage.v1`

Therefore the AqSolDB source, parsed-source hash, Morgan representation and
descriptive similarity bins remain unchanged.

No model is fitted.

## Frozen eligibility and selection rule

Eligibility boundary:

`nearest AqSolDB Tanimoto >= 0.4`

This is not a threshold selected from MOLDISC-003 results. It is the existing
ONLINE-EXP-002 descriptive boundary that MOLDISC-002 already reused.

If one or more seeds are eligible:

1. select the highest nearest-neighbor similarity;
2. break an exact tie by ascending REDOCK-003 case ID.

If no seed reaches 0.4, MOLDISC-003 closes with no selected seed.

A selected seed is only eligible to open a separately frozen next Molecular
Discovery program. It is **not** declared the best drug, the strongest binder,
or the most effective target.

## Explicitly out of scope

MOLDISC-003 performs no:

- molecule generation;
- solubility-model training;
- hyperparameter optimization;
- docking execution;
- efficacy scoring;
- affinity inference;
- post-result threshold tuning.

## Acceptance gates

Before accepting the first result, CI must confirm:

- exactly 15 frozen cases are present;
- every CCD identity is retrievable and RDKit-valid;
- a deterministic RCSB scientific identity hash is emitted;
- all 15 seeds are evaluated against the immutable AqSolDB coverage source;
- the eligibility boundary remains exactly 0.4;
- selection follows the frozen highest-similarity/tie-break rule;
- no model fitting or molecule generation occurs.

## Interpretation boundary

Crystallographic presence in the PDB is structural provenance.

AqSolDB similarity is measured-solubility **coverage evidence**.

Neither establishes:

- therapeutic value;
- shared biological mechanism;
- binding affinity;
- potency;
- efficacy;
- safety;
- synthesizability;
- clinical utility.
