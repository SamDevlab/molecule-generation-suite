# MOLDISC-001 — ID5 halogen-neighborhood solubility triage

Status: **executed and closed; first result preserved without post-hoc protocol changes**

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


## First execution — GitHub Actions run 3

The first MOLDISC-001 execution completed successfully in workflow run `35293207930`.

Environment:

- CPython `3.12.14`
- NumPy `2.5.3`
- RDKit `2026.3.6`
- scikit-learn `1.9.1`

Execution identities:

- candidates: `9`
- generated analogs: `8`
- generation scientific hash: `d2881a9906a6a60d54e90a303601d9509983e6f1a0b9ce01a0792bf088890abe`
- workflow scientific summary hash: `fa36dc8b82a60d6edccad464c7c0dc3297e39c28ca52a40694da67cab3c1d48e`
- program scientific hash: `421541946e6e008441b0c5fa867fe200aeaf09c8aa0fb87c115af11e637c13d0`

### Observed boundary

All nine candidates passed molecular validation, and docking remained `NOT_REQUESTED` as frozen.

However, all nine candidates were **OUT_OF_DOMAIN** for the frozen ESOL model.

The inherited AD threshold is:

`0.26684684684684684`

The highest maximum-train Tanimoto similarity observed in MOLDISC-001 was only:

`0.22666666666666666`

The crystallographic ID5 seed itself was:

`0.19736842105263158`

Therefore MOLDISC-001 v1 contains:

- `0` in-domain solubility candidates;
- `9` out-of-domain candidates;
- `0` candidates eligible for an in-domain solubility prioritization claim.

The model emitted logS values between approximately `-4.526` and `-4.915`, but these are retained only as out-of-domain model outputs. They are **not** promoted to reliable solubility ranking evidence.

### Scientific conclusion

This is a useful negative/boundary result.

The first real program demonstrates that Research OS does not force a positive answer: a real crystallographic seed and its generated analogs can pass chemistry while the next evidence layer explicitly refuses domain support.

The generator, seed, model, threshold and triage rules are not changed after seeing this result.

MOLDISC-001 is closed. Any attempt to obtain broader solubility coverage, use a different training population, introduce a different property model, or change the generated chemical neighborhood is a new program/protocol.
