# MOLDISC-007 — Operational fallback seed selection

Status: **protocol frozen before the fallback result is materialized**

## Why this program exists

MOLDISC-006 closed as `CLOSED_INDETERMINATE_TARGET_PREPARATION` because
PDB 1P2Y requires HEM and the current validated preparation stack could not
produce a defensible holo receptor PDBQT without introducing new
metalloprotein-specific chemistry.

MOLDISC-007 does not repair or bypass that result.

Instead, it returns to the already frozen MOLDISC-003 seed cohort and asks a
narrow operational question: among seeds with measured-solubility structural
coverage, which remaining target also demonstrated rank-1 pose localization
inside the existing REDOCK-003 protocol?

## Frozen evidence sources

MOLDISC-003:

- program scientific hash:
  `977428ab62ff38cda8033f5daf9ecc85e93f9f9994240ca2f13729405ab58e2b`
- AqSolDB eligibility boundary: `0.4`
- eligible cases: `ATX-014`, `ATX-007`, `ATX-013`, `ATX-012`

REDOCK-003:

- scientific result hash:
  `e4e4693f890b86327fac16b547966fe64862045d1562c4340dcc3d7d4a06b762`
- operational localization criterion reused here:
  rank-1 RMSD <= `2.0 Å`

MOLDISC-006:

- merge commit:
  `464ab97017439caf6c8de75ef2aad42f11b2cf03`
- status:
  `CLOSED_INDETERMINATE_TARGET_PREPARATION`

## Frozen fallback rule

A candidate is eligible only if all conditions are true:

1. AqSolDB nearest similarity >= `0.4`;
2. target is not operationally blocked by a closed Molecular Discovery program;
3. REDOCK-003 rank-1 RMSD <= `2.0 Å`;
4. the REDOCK-003 rank-1 success flag is true.

If more than one candidate is eligible:

1. highest AqSolDB nearest similarity wins;
2. exact tie -> ascending case ID.

No Vina score enters the rule.

No new docking is executed.

## Frozen candidate table

| Case | PDB | Ligand | AqSolDB nearest | REDOCK pose-1 RMSD | blocked |
|---|---|---|---:|---:|---|
| ATX-014 | 1P2Y | NCT | 1.000000 | 4.385 Å | yes — MOLDISC-006 |
| ATX-007 | 1KZK | JE2 | 0.569620 | 1.902 Å | no |
| ATX-013 | 1UOU | CMU | 0.547619 | 6.473 Å | no |
| ATX-012 | 1TOW | CRZ | 0.454545 | 4.588 Å | no |

## Interpretation boundary

This is a seed-selection program from **previously observed evidence**.

It is not:

- an independent docking validation;
- a binding-affinity comparison;
- a potency comparison;
- an efficacy ranking;
- a therapeutic-target ranking;
- a new solubility measurement.

Rank-1 RMSD is used here only as an operational-readiness filter.

AqSolDB similarity is used only as a measured-source coverage signal.

The selected seed, if any, may open a separately frozen Molecular Discovery
program. It does not become a biological winner.
