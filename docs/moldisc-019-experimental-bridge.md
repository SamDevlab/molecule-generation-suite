# MOLDISC-019 — First Experimental Bridge and Biolab Autonomous-Loop Transition

MOLDISC-019 closes the current computation-only Molecular Discovery phase and
opens the Biolab / Molecular Discovery experimental-feedback bridge. It does
not run docking, generate molecules, select candidates, select leads, or train
an ML model.

## Scientific boundary

MOLDISC-018 established a bounded E2 computational docking capability profile.
The remaining decision-changing gaps require E4 curated experimental evidence.
The first practical gap is `GAP-EXPERIMENTAL-SOLUBILITY`, addressed by the
frozen `BIOEXP-001-SOLUBILITY-2X2` panel. The complete 2x2 design is retained:

| Panel key | Factor A | Factor B | Role |
|---|---|---|---|
| A0B0 | CONTROL | CONTROL | control |
| A1B0 | DELTA-OH | CONTROL | single edit |
| A0B1 | CONTROL | DELTA-NSUB | single edit |
| A1B1 | DELTA-OH | DELTA-NSUB | interaction member |

The panel is not ranked by docking and no member is called a lead or winner.
C-2545 remains unresolved in stereochemistry and its measurement cannot be
transferred to any panel member.

## Autonomous loop v0.1

The Molecular-Discovery-specific loop composes existing Research OS contracts.
It reads scientific state and returns one of `COMPUTE`, `EXTERNAL_EVIDENCE`,
`EXPERIMENT`, or `STOP`. For the first state it records:

- current program `MOLDISC-018`;
- highest local evidence `E2_COMPUTATIONAL`;
- target gap `GAP-EXPERIMENTAL-SOLUBILITY`;
- required evidence `E4_CURATED_EXPERIMENTAL`;
- selected action `EXPERIMENT`;
- stop reason `EXPERIMENTAL_VALIDATION_REQUIRED`.

The same-level guard prevents a new docking campaign or analog series from
being opened merely because local compute is available. A new E2 action can be
reconsidered only for a direct blocker, genuinely new independent external
information, or a confirmed implementation/scientific bug.

## Physical bridge

`BIOEXP-001-SOLUBILITY-2X2` starts as
`AWAITING_EXTERNAL_PROTOCOL_OR_QUOTE`. The repository does not invent pH,
temperature, medium, buffer, ionic strength, compound form, units, or
replicate policy. `BIOEXP-002-PROTEASE-2X2` is planning-only and does not
implement culture, infection, or pathogen handling.

`validate-result` is read-only and fails closed on missing provenance, missing
artifact hashes, missing conditions, non-experimental fixtures, or identity
mismatch. `ingest-result` creates an append-only external update only after
all E4 gates pass. E5 requires independent eligible validation and is never
created from technical replicates or duplicate reports.

## What this increment proves

The repository can truthfully state that the computation-only phase is closed,
the next decision-changing evidence is physical, the first physical package
is frozen without pretending to have a protocol or result, and a future real
result has a fail-closed path into a recomputed Biolab decision.

This is `AUTONOMOUS_LOOP_V0_1`; it is not a self-driving laboratory, a fully
autonomous scientist, S3 integration, or large-scale hypothesis throughput.
