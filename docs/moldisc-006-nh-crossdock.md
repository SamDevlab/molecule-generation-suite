# MOLDISC-006 — selected N-H non-cognate holo docking

Status: **protocol frozen before the first N-H Vina score is inspected**

## Purpose

MOLDISC-005 selected exactly one generated analog, N-H, using the predeclared
AqSolDB measured-source coverage rule. MOLDISC-006 now tests whether that
single selected analog can be prepared and docked reproducibly into the known
1P2Y holo pocket under the already-defined Research OS docking capability
boundary.

This is not another generation program and it performs no candidate selection.

## Frozen parent

Parent:

- program: `MOLDISC-005`
- program scientific hash: `88e28697f8ce5ae14d0737089130c469275d28950c63e90053bc6fe6012dcac7`
- selected candidate: `MOLDISC-005-NCT-84632F8200`
- variant: `N-H`
- canonical SMILES: `c1cncc(C2CCCN2)c1`
- AqSolDB nearest similarity: `0.896551724137931`

The candidate remains a generated E0 source structure. MOLDISC-006 does not
reinterpret the MOLDISC-005 selection as biological evidence.

## Frozen target

The target is the existing REDOCK-003 case:

- case: `ATX-014`
- PDB: `1P2Y`
- native ligand: `NCT`
- receptor chain: `A`
- native ligand chain: `A`
- historical target label: `CYTOCHROME P450-CAM`

The receptor is extracted from the exact RCSB PDB content downloaded at run
time. Chain A protein atoms are retained together with the crystallographic
`HEM` cofactor and its iron atom. Other HETATM records, including
crystallographic waters, are excluded.

This target-specific retention is mandatory: 1P2Y is cytochrome P450cam and
the deposited complex contains HEM; the crystallographic interpretation
describes nicotine pyridine nitrogen coordination to the heme iron. A
receptor missing HEM is therefore a protocol failure, not a permitted
simplification.

The docking box is derived from the exact NCT crystallographic reference
coordinates using the existing `research-os.redocking.v1.1` native-ligand
box rule.

No box coordinate is tuned after seeing the N-H result.

## Frozen ligand preparation

The N-H SMILES is converted to one starting conformer with:

- RDKit ETKDGv3;
- random seed `42`;
- UFF optimization when all parameters are available.

Open Babel then prepares the ligand PDBQT with:

```text
-h --partialcharge gasteiger
```

The receptor PDBQT uses:

```text
-h --partialcharge gasteiger -xr
```

All source, conformer and prepared-artifact SHA-256 identities are recorded.

## Frozen Vina execution

Required engine:

- AutoDock Vina `1.2.7`
- scoring: Vina
- random seed: `42`
- CPU: `1`
- exhaustiveness: `16`
- requested modes: `20`

Docking context:

`NON_COGNATE_HOLO_CROSSDOCKING`

The current Research OS capability profile classifies this as
`PARTIALLY_VALIDATED`, with evidence level `E2_COMPUTATIONAL`.

## Primary endpoint

The primary endpoint is **technical completion under the frozen protocol**.

PASS requires:

1. exact target/candidate/config identity checks;
2. RCSB receptor and NCT reference retrieval;
3. explicit HEM retention with exactly one iron atom;
4. valid native-ligand grid derivation;
5. successful receptor and ligand PDBQT preparation;
6. exact Vina 1.2.7 availability;
7. Vina return code zero;
8. at least one parseable scored pose;
9. complete provenance hashes.

There is deliberately no threshold such as “score better than X”.

## Why there is no RMSD to native NCT

N-H and NCT are different molecular graphs.

A same-graph redocking RMSD endpoint is therefore not defined. MOLDISC-006
must not fit N-H onto NCT and report that as a native-pose recovery metric.

The result may report Vina scores and returned-pose count only within the
declared non-cognate computational context.

## Reproduction requirement

The dedicated CI job executes MOLDISC-006 twice with the same frozen inputs and
requires identical scientific hashes.

The scientific hash includes:

- source PDB/reference identities;
- extracted receptor identity;
- native-derived grid;
- N-H starting conformer identity;
- prepared receptor/ligand identities;
- Vina/Open Babel versions;
- all returned Vina pose scores;
- Vina output identity;
- docking capability profile metadata.

Operational output paths are excluded.

## Interpretation boundaries

A successful run does **not** establish:

- measured binding affinity;
- free energy;
- potency;
- CYP activity, inhibition or metabolism;
- correct experimental binding pose;
- efficacy;
- safety;
- clinical utility.

MOLDISC-006 answers one narrower question: whether the selected N-H analog can
be executed reproducibly through the frozen non-cognate holo docking protocol
and what bounded E2 computational output that protocol returns.
