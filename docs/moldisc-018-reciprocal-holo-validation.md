# MOLDISC-018 — reciprocal non-cognate holo cross-docking

MOLDISC-018 is a bounded E2 computational capability campaign. It pauses
generated-candidate exploration and tests the `NON_COGNATE_HOLO_CROSSDOCKING`
capability directly with known experimental structures from the official RCSB
archive.

## Scope and frozen design

The benchmark contains exactly four primary reciprocal cases:

| Case | Ligand | Target receptor | Experimental reference | State |
| --- | --- | --- | --- | --- |
| RX-01 | K57 / KNI-577 | 1MSM JE2 background | 1MRW K57 background | background |
| RX-02 | JE2 / KNI-764 | 1MRW K57 background | 1MSM JE2 background | background |
| RX-03 | K57 / KNI-577 | 1MSN JE2 mutant | 1MRX K57 mutant | V82F/I84V |
| RX-04 | JE2 / KNI-764 | 1MRX K57 mutant | 1MSN JE2 mutant | V82F/I84V |

The campaign also performs four cognate K57 controls (1MRW A/B and 1MRX
A/B). These controls and the four primary cases are expanded to 20 declared
Vina runs: ETKDG seeds 42, 1337, and 2025, with the primary denominator fixed
to seed 42 / RUN_A. Conformer and RUN_B replicates are robustness diagnostics,
not additional benchmark cases.

The frozen protocol uses AutoDock Vina 1.2.7, seed 42, CPU 1,
exhaustiveness 16, and 20 output modes. Receptor alignment is receptor-only
Kabsch fitting over all matching C-alpha residues; no ligand fit is applied.
Success is defined as symmetry-aware heavy-atom RMSD ≤2.0 Å. Failure classes
separate rank-1 recovery, near-native pose misranking, sampling failure,
analysis indeterminacy, and execution failure.

JE2 grids are imported and verified from the prior evidence chain. K57 grids
are derived once from 1MRW and 1MRX and frozen before execution. Official RCSB
source, ligand identity, mutation state, receptor chains, and grid hashes are
audited before docking.

## First result

The first result executed all 20 declared runs with zero technical non-pass
cases. The four primary cases produced 2/4 rank-1 successes and 4/4 cases with
at least one returned pose within 2.0 Å. RX-01 and RX-02 are
`RANK1_NEAR_NATIVE`; RX-03 and RX-04 are
`NEAR_NATIVE_POSE_MISRANKED`. The cognate K57 controls were technical PASS and
rank-1 near-native in both receptor states.

The evidence is appended under `MOLDISC-018-RECIPROCAL-HOLO` while preserving
`CROSSDOCK-001`. The capability classification remains
`PARTIALLY_VALIDATED`, and the evidence ceiling remains `E2_COMPUTATIONAL`.
MOLDISC-018 does not pool the new four-case denominator with CROSSDOCK-001.

## Interpretation boundary

MOLDISC-016/017 produced substantial candidate-specific computational
evidence, but candidate interpretation depends on a partially validated
non-cognate holo cross-docking capability. MOLDISC-018 therefore spends the
next computation budget on known experimental structures rather than
additional generated chemistry.

No molecule generation, generated-candidate docking, candidate selection,
lead selection, affinity inference, resistance claim, biological activity
inference, or experimental-truth claim is part of this program. MOLDISC-019 is
not opened by this campaign.

The machine-readable first result is
`validation/moldisc-018-first-run-v1.json`.
