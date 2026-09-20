# MOLDISC-017 — HIV-1 Protease Receptor-State and Resistance Megacampaign

MOLDISC-017 is a bounded E2 computational challenge of the frozen
MOLDISC-016 four-member JE2-derived panel.  R0 (1KZK) is imported from the
closed MOLDISC-016 artifact and is never rerun.  R1 (1MSM) and R2 (1MSN) are
matched JE2/KNI-764 receptor states; R2 adds V82F/I84V to the Q7K/L33I/L63I
background.

The four candidates are retained exactly as MOLDISC-016 defined them:
CONTROL, DELTA-OH, DELTA-NSUB, and DELTA-BOTH.  No molecule is generated,
selected, or promoted to a lead.  The KNI-577 structures 1MRW and 1MRX are
native crystallographic context only.  They are audited for identity and
mutation mapping, but are never docked and no activity measurement is
transferred from them.

The new execution is exactly 36 Vina runs: four JE2 native redocking
diagnostics and 32 panel crossdocks, with Vina seed 42, one CPU,
exhaustiveness 16, and 20 modes.  Starting conformers use ETKDGv3 seeds 42,
1337, and 2025.  No Vina-seed or exhaustiveness grid is permitted.

All geometry endpoints are descriptive.  Same-receptor comparisons use the
receptor frame without rigid-body fitting.  R1/R2 comparisons use a recorded
Kabsch alignment of receptor C-alpha atoms from chains A and B, excluding
residues 82 and 84; the same transform is applied to R2 ligand poses.  Strict
MCS definitions are frozen before pose analysis at 38, 35, 33, and 32 heavy
atoms for the four chemical edges.  Contacts use a 4.0 Å heavy-atom cutoff.

Vina scores are engine outputs, not affinity, potency, resistance, efficacy,
or clinical measurements.  The 2 Å redocking value is diagnostic only.
