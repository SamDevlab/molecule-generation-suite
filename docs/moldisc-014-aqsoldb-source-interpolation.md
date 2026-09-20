# MOLDISC-014 — AqSolDB source-directed interpolation panel

Status: **protocol frozen; execution pending**

## Scientific question

MOLDISC-014 starts from the already selected MOLDISC-011
`STEP2-DEMETHYL-01` candidate and creates exactly three bounded structures by
applying two connectivity edits that point toward its recurring measured
AqSolDB neighbor:

- `SOURCE-DELTA-OH`: delete the phenolic hydroxyl;
- `SOURCE-DELTA-NSUB`: replace terminal N-benzyl with N-tert-butyl;
- `SOURCE-DELTA-BOTH`: apply both edits.

The panel is a characterization panel, not an automatic demethylation series.
No third demethylation, halogen scan, random substitution, bioisostere
enumeration, docking, or winner selection is executed.

## Frozen upstream and source

The seed is the MOLDISC-011-selected
`MOLDISC-011-JE2-286E6F2BE8` candidate with frozen program hash
`8cb29619a82ca4680424c1b37c9bdce37b83e6cc8d570788435e1e9a62b159ff`.
MOLDISC-013 is recorded only as context (`325edfa890dabc1f8640f9977c6b2e308b582293493631a040752739fd6d89a4`);
its geometry is not used for generation or selection.

The source is the immutable AqSolDB capability at DOI
`10.1038/s41597-019-0151-1`, source commit
`98cdd10a372058743e4f3fb950a1c9974ec9603a`, blob
`67016e030cf0a741e250ba0267bd84461041db5f`, and parsed-source hash
`2c6e56f56389f0fd99fa2a3c843446f98b6b068a3f93aaab71a08822caa085f4`.
The recurring source record is preserved by its exact source ID, raw SMILES,
active-runtime InChIKey `URHJIBSBOJFXDI-UHFFFAOYSA-N`, one observation, and
measured logS `-3.62`.

The active source does not specify the same stereochemistry as the JE2
lineage. The implementation records the raw source and its canonical
isomeric/non-isomeric forms without borrowing or inventing stereocenters.

## Measurement-transfer boundary

The `-3.62` measurement belongs only to the immutable AqSolDB source
structure. Tanimoto 1.0, equal connectivity, or an equal first InChIKey block
does not authorize transfer. Transfer requires an exact canonical isomeric
structure match and full active-runtime InChIKey match. In particular,
`SOURCE-DELTA-BOTH` is expected to share the source connectivity block while
retaining a different stereochemical InChIKey; its measurement remains
non-transferable.

## Evidence boundary

All three products are generated `E0_HEURISTIC` structures, even though their
edits are source-directed. MoleculeLab chemistry, frozen ESOL applicability,
and immutable AqSolDB coverage are reported for the seed and all three
products. ESOL is secondary and is not used for filtering or ranking; an
`OUT_OF_DOMAIN` prediction is preserved as an unsupported extrapolative model
output, not as a measurement.

MOLDISC-014 executes no Vina docking, does not use MOLDISC-010/012 scores or
MOLDISC-013 geometry, and records `candidate_selection_executed=false` with
`selected_candidate_id=null`.
