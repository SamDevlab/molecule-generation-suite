# MOLDISC-010 — DEMETHYL-03 non-cognate docking in 1KZK

Status: **executed and closed; first CI result preserved with deterministic scientific identity**

## Why this program exists

MOLDISC-009 selected exactly one generated JE2 analog, `DEMETHYL-03`, using
only the predeclared immutable AqSolDB structural-coverage rule.

MOLDISC-010 asks the next narrow question: can that one selected structure run
reproducibly through the already operational 1KZK/JE2 pocket docking protocol?

No molecule generation or candidate selection occurs here.

## Frozen parent and candidate

Parent MOLDISC-009:

- program hash:
  `75ffaf31d6df6983e7692fca4f0a3fa2277c743dcac2b99cee179c9b39116615`
- selected variant: `DEMETHYL-03`
- selected candidate: `MOLDISC-009-JE2-5461A4A267`
- AqSolDB nearest similarity: `0.631578947368421`
- selection used ESOL: no

Frozen candidate:

- canonical SMILES:
  `Cc1ccccc1CNC(=O)[C@H]1N(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2cccc(O)c2)CSC1(C)C`
- InChIKey:
  `XBNKKAGGYBXOJG-GMQQYTKMSA-N`
- generation evidence: `E0_HEURISTIC`

## Frozen target

The target is the existing REDOCK-003 case:

- case: `ATX-007`
- PDB: `1KZK`
- native ligand: `JE2`
- native ligand author chain: `A`
- receptor author chains: `A + B`
- resolution: `1.09 Å`
- frozen historical REDOCK-003 pose-1 RMSD: `1.902 Å`

The receptor extraction rule is not changed for DEMETHYL-03. Protein ATOM
records from the same frozen A+B receptor chains are used.

The docking box is derived from the exact crystallographic JE2 reference
coordinates using the existing `research-os.redocking.v1.1` native-ligand
box rule.

## Frozen preparation

DEMETHYL-03 starting conformer:

- RDKit ETKDGv3;
- random seed `42`;
- UFF optimization when parameters are available.

PDBQT preparation reuses the operational REDOCK-003 Open Babel route:

Receptor:

`-h --partialcharge gasteiger -xr`

Ligand:

`-h --partialcharge gasteiger`

Both outputs must be non-empty and contain atom records.

## Frozen Vina run

- AutoDock Vina: `1.2.7`
- seed: `42`
- CPU: `1`
- exhaustiveness: `16`
- modes: `20`
- context: `NON_COGNATE_HOLO_CROSSDOCKING`
- capability: `PARTIALLY_VALIDATED`
- evidence level: `E2_COMPUTATIONAL`

## Primary endpoint

The endpoint is technical completion, not a favorable score.

PASS requires:

1. exact parent/candidate/target identities;
2. source receptor and JE2 reference retrieval;
3. valid JE2-derived grid;
4. non-empty receptor and ligand PDBQT;
5. exact Vina 1.2.7 availability;
6. Vina return code zero;
7. at least one finite non-zero scored pose;
8. complete scientific and transport provenance.

## No native RMSD claim

DEMETHYL-03 and JE2 are different molecular graphs.

Therefore MOLDISC-010 does not calculate or report a native-JE2 RMSD. A Vina
pose is not labeled native-like merely because it occupies the same pocket.

## Reproduction gate

Dedicated CI executes the entire program twice independently with frozen
inputs and requires identical program scientific hashes.

Raw transport hashes are preserved separately. The scientific identity uses
the parsed JE2 structure/coordinates, extracted receptor, candidate conformer,
prepared inputs, grid, engine versions, scores and capability metadata.

## First preserved result

The first green CI execution is preserved in
`validation/moldisc-010-first-run-v1.json`:

- GitHub Actions run: `35474219286` (`moldisc-010-ci`), result `PASS`;
- independent runs A/B: identical `program_scientific_hash`;
  `360ef9eb66981287781a971a7e09aebbe2749be765af5b4c6dcb33e3839eb48b`;
- technical status: `PASS`, with 20 scored poses;
- pose 1: `-11.03 kcal/mol`;
- grid hash: `a0bf032d8bdb1bc20f13f298d604673cac1d2c7da8596cc228ec6602b5989aef`;
- native JE2 structure hash:
  `82b48b534ff870fb8a922ed62da905bf77fe2e54f2420143986a4c5f9b9c9a4b`;
- receptor scientific identity:
  `f4182f7337c0509db49d34c97b6a1cf9639b0b3e3cb25735265fd8daede9b32c`;
- ligand scientific identity:
  `0fc2ec1c34cc9abe2223d860c35fe2c64576e72f4ed4b3c9bd2b502c1d36290b`.

The receptor PDBQT raw SHA differed between A/B only because Open Babel
embedded different temporary paths in `REMARK Name`; the parsed atom records,
coordinates, partial charges and atom types were identical. The downloaded
native SDF also varied only in ModelServer metadata and timing fields. Both
raw hashes remain recorded in provenance. Neither observation changes the
frozen candidate, target, grid, engine, or docking parameters.

## Interpretation boundaries

A successful run does not establish measured affinity, free energy, potency,
protease inhibition, efficacy, safety, a correct experimental binding mode, or
clinical utility.

MOLDISC-010 produces bounded E2 computational evidence only.
