# MOLDISC-014 — AqSolDB source-directed interpolation panel

Status: **CLOSED_FIRST_RESULT_PRESERVED**

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

## First result preserved

The first independent CI execution passed as run `35482672526` on head
`4c4662aa12c42e1935243cc366ffbbf43bbf7170`. The complete preserved record is
[`validation/moldisc-014-first-run-v1.json`](../validation/moldisc-014-first-run-v1.json).

The panel contained the upstream seed plus exactly three generated products;
all four passed chemistry characterization. AqSolDB nearest similarities were
`0.6857142857142857` for the seed, `0.7903225806451613` for
`SOURCE-DELTA-OH`, `0.859375` for `SOURCE-DELTA-NSUB`, and `1.0` for
`SOURCE-DELTA-BOTH`. The final product shared the source connectivity block
but not the full source InChIKey, so no panel measurement transfer was
allowed. The source observation remains preserved as `C-2545`, with measured
logS `-3.62`, only as source-neighbor context.

The frozen ESOL statuses were `OUT_OF_DOMAIN`, `IN_DOMAIN`, `OUT_OF_DOMAIN`,
and `OUT_OF_DOMAIN` in panel order. These model outputs were not used for
generation, filtering, ranking, or selection. The scientific hashes are:

- generation: `45936d983a148bbb62d9be45de4aefa53f632c877320c92dc84e615b7e96700e`;
- source audit: `b6b663b811e39b92b7db93e2c645f7016fbea73d924fb01695283e193feed383`;
- workflow: `6fdfa84f3bc737cf22217f3fb4512f5739fa7369d38f1e429edc577ec0af0f58`;
- AqSolDB coverage: `e49c660026e3ef16c638558885bcd80f130ab60ebfe36aa7baf17bc45c4bb095`;
- program: `f940d95189616131829a22f9e68a53a960eddf8fd05f5fd7ebac43ece85481ed`.

This first result is a bounded E0 characterization record. It does not
establish experimental solubility, safety, efficacy, synthesizability, or
clinical validity, and it does not open MOLDISC-015.
