# MOLDISC-001 — ID5 halogen-neighborhood solubility triage

Status: **protocol frozen before first program output is inspected**

## Scientific use case

MOLDISC-001 is the first real program that uses Research OS 5.1 as infrastructure instead of extending the framework.

It starts from the crystallographic ligand ID5 (IDD552) in PDB 1T40, human aldose reductase, and explores a deliberately narrow single-halogen substitution neighborhood. Generated candidates are then passed through the existing Molecular Discovery workflow for:

1. molecular validity and deterministic characterization;
2. frozen ESOL aqueous-solubility prediction;
3. inherited applicability-domain classification;
4. deterministic review triage.

No generated analog is automatically docked in program v1.

## Frozen public source

Target:

- PDB: `1T40`
- protein: human aldose reductase
- chain: `A`
- resolution: `1.80 Å`
- crystallographic ligand: `ID5`
- Research OS historical validation link: REDOCK-003 case `ATX-005`

Seed:

- PDB chemical component: `ID5`
- synonym: IDD552
- formula: `C17H10F4N2O4S`
- InChIKey: `ZCAGEXZTORJQDZ-UHFFFAOYSA-N`
- frozen SMILES: `Fc1ccc(c(OCC(=O)O)c1)C(=O)NCc2nc3c(F)c(F)cc(F)c3s2`

Sources:

- https://www.rcsb.org/structure/1T40
- https://www.rcsb.org/ligand/ID5

The program verifies the seed InChIKey with the active RDKit runtime before generation.

## Frozen generation rule

Generator:

`research-os.molecular-discovery.halogen-single-substitution.v1`

Rule:

- inspect only F, Cl and Br atoms;
- replace exactly one halogen per generated molecule;
- for F: enumerate Cl and Br replacements;
- sanitize with RDKit;
- canonicalize;
- deduplicate;
- sort by canonical SMILES;
- assign deterministic candidate IDs;
- cap the output at the frozen `max_candidates`.

The ID5 seed contains four fluorine atoms. The protocol does not select generated structures using solubility, docking, residuals or any downstream score.

Generated molecules are `E0_HEURISTIC` candidate sources. Validity or a downstream prediction does not retroactively make the generation step experimental evidence.

## Frozen triage

The seed is included alongside generated analogs.

Candidate review order is inherited unchanged from Molecular Discovery v0.1:

1. evidence-complete, in-domain candidates;
2. out-of-domain candidates;
3. incomplete-evidence candidates;
4. structurally excluded candidates.

Within the eligible group, higher predicted aqueous logS is shown first.

This is a review queue, not an efficacy score.

## Docking boundary

MOLDISC-001 v1 does not automatically dock the analogs.

The ID5 seed is cognate to 1T40, but a generated analog is not the crystallographic cognate ligand. If a later version prepares a generated ligand and docks it against the 1T40 holo receptor/known pocket, the declared context must be:

`NON_COGNATE_HOLO_CROSSDOCKING`

Research OS currently classifies that context as **partially validated**, based on CROSSDOCK-001. A Vina score would remain E2 computational evidence and would not be affinity, potency or efficacy.

## First-run acceptance checks

Before any observed program result is accepted, CI must confirm:

- config identity remains frozen;
- seed InChIKey matches;
- generator produces valid, unique structures;
- generation precedes all downstream predictions;
- all candidates pass through MoleculeLab;
- the frozen ESOL predictor reconstructs from the recorded public source;
- dataset/training identity checks pass;
- every prediction records AD status;
- no docking is silently executed;
- program, generation and workflow scientific hashes are emitted.

No generation rule, candidate cap, target, seed, solubility model or triage rule may be changed in response to the first observed output within MOLDISC-001 v1.

## Interpretation limits

MOLDISC-001 does not establish:

- binding affinity;
- inhibition or potency;
- therapeutic efficacy;
- safety;
- synthetic accessibility;
- chemical stability;
- experimental solubility;
- superiority of one analog as a drug candidate.

Its first purpose is narrower: prove that Research OS 5.1 can take a real source-backed molecular seed, generate traceable candidate structures, execute bounded scientific capabilities, and produce an auditable review set without inventing evidence.
