# MOLDISC-006 — selected N-H non-cognate holo docking

Status: **v1.2 corrective protocol frozen; v1.0/v1.1 failures preserved**

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

## Preserved v1.0 invalid preparation

The first v1.0 execution is retained in
`validation/moldisc-006-v1.0-invalid-preparation.json`.

Open Babel returned code zero while reporting `0 molecules converted` for
the holo receptor, produced a zero-byte receptor PDBQT, and Vina subsequently
returned twenty zero-valued scores. Those outputs are **invalid** and are not
docking evidence.

The v1.0 investigation also showed that repeated HTTP retrievals of the same
RCSB NCT SDF can differ at the raw-byte level. v1.1 therefore records raw
transport SHA-256 separately while using the canonical parsed NCT graph plus
heavy-atom coordinates as the scientific reference identity.

No candidate, target, box rule, Vina setting, docking context, or endpoint was
changed in response to the invalid scores.

## Preserved v1.1 target-template failure

MOLDISC-006 v1.1 installed Meeko 0.8.0 successfully but stopped before Vina:
the default residue template registry did not contain HEM, and Meeko's
automatic CCD template reconstruction failed for residue A:430.

That attempt is preserved as
`validation/moldisc-006-v1.1-indeterminate-heme-template.json` and contains
no valid docking result.

## Corrected v1.2 preparation

MOLDISC-006 v1.2 still uses **Meeko 0.8.0** for receptor and ligand PDBQT
preparation, but supplies HEM explicitly through Meeko's supported
`--add_templates HEM:<sdf>` mechanism.

The template source is the official RCSB Chemical Component Dictionary ideal
SDF:

`https://files.rcsb.org/ligands/download/HEM_ideal.sdf`

The template download SHA-256 is recorded as a scientific preparation input.
The corrected gate requires a non-empty receptor PDBQT and explicit
preservation of HEM with exactly one iron atom.

## Frozen ligand preparation

The N-H SMILES is converted to one starting conformer with:

- RDKit ETKDGv3;
- random seed `42`;
- UFF optimization when all parameters are available.

Meeko 0.8.0 prepares the ligand PDBQT from the frozen 3D SDF and prepares the
holo receptor PDBQT from the extracted chain-A + HEM PDB.

All source, conformer and prepared-artifact SHA-256 identities are recorded.
The receptor output must be non-empty and contain the HEM residue with exactly
one Fe record.

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
- Vina/Meeko versions;
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
