# REDOCK-003 / Astex-20 redocking benchmark v1.0

Status: **prospective structural preflight phase — no new docking result exists yet**.

## Purpose

REDOCK-003 extends the Astex Diverse Set evaluation from the five already-observed REDOCK-002 cases to an Astex-20 view while keeping the new scientific endpoint genuinely prospective.

The benchmark is split into two blocks:

- **historical Astex block (5 cases):** the already-observed REDOCK-002 cases;
- **prospective Astex extension (15 cases):** structurally eligible cases selected before any REDOCK-003 Vina execution.

The primary prospective endpoint is the 15-case extension. The 20-case aggregate is descriptive and must not be presented as if all twenty cases were unseen.

## Frozen source universe

Source set: Astex Diverse Set, 85 PDB/CCD complex identifiers.

Reference list used for identity:

```text
https://github.com/oxpig/RLDiff/blob/main/data/astex_diverse_85_ids.txt
SHA-256 of newline-terminated 85-ID list:
7c2bc6702b62abe282bbd6f67146ec071c623cc3bd17d4683c1afd898b2df5ef
```

The list agrees with the 85-complex Astex Diverse data set described in the PoseBusters materials.

## Historical five — excluded from prospective selection

```text
1V0P_PVB
1W1P_GIO
2BM2_PM2
1VCJ_IBA
1TT1_KAI
```

These are already scientifically observed by REDOCK-002 and therefore cannot count toward the prospective denominator.

## Deterministic ranking rule

For each of the remaining 80 `PDB_CCD` identifiers:

```text
selection_key = SHA-256("research-os.astex20.v1.0:" + PDB_CCD)
```

Candidates are sorted lexicographically by the full SHA-256 digest. No target class, ligand size, score, RMSD, docking feasibility result or human preference participates in ranking.

The first fifteen hash-ranked candidates before structural eligibility screening are frozen as:

```text
1R1H_BIR
1SJ0_E4D
1MEH_MOA
1Q41_IXM
1T9B_1CS
1MMV_3AR
1JJE_BYS
1V4S_MRK
1T40_ID5
1PMN_984
1KZK_JE2
1W2G_THM
1HQ2_PH2
1S3V_TQD
1HVY_D16
```

## Structural eligibility screening

The preflight walks the 80 candidates in frozen hash order and accepts the first 15 that satisfy all of the following without invoking Vina:

1. the RCSB PDB file downloads successfully;
2. exactly one heavy-atom instance of the frozen CCD ligand exists in the PDB;
3. at least one polymer author chain has a heavy atom within 8.0 Å of the ligand;
4. the RCSB ligand-instance SDF downloads and sanitizes;
5. PDB and SDF ligand heavy-atom counts agree;
6. the unchanged REDOCK v1.2 native-centered box rule is inside its frozen domain;
7. structure resolution is parseable from the PDB.

If a candidate is structurally ineligible, the rejection reason is retained and the next hash-ranked candidate is evaluated. This is an input-domain screen only. It cannot see or use Vina scores, poses or RMSDs.

The contact-chain rule is deterministic: all author chains with at least one protein heavy atom within 8.0 Å of any native-ligand heavy atom become the frozen receptor-chain set.

## Preflight safety boundary

The structural-preflight workflow for `benchmark/astex20-v1`:

- does not install AutoDock Vina;
- does not import or instantiate `VinaEngine`;
- does not run docking;
- writes `docking_executed = false` and `vina_imported_or_invoked = false` into its report.

Only after the 15-case manifest is inspected and committed as explicit frozen `RedockingCase` values will a second commit add the Vina execution job.

## Planned docking protocol after freeze

REDOCK-003 will reuse the validated REDOCK-001 v1.2 executor/evaluator unchanged:

- AutoDock Vina 1.2.7;
- seed 42;
- CPU 1;
- exhaustiveness 16;
- up to 20 poses;
- independently generated ETKDG seed-42 + UFF starting conformer;
- Open Babel ligand/receptor preparation;
- native-centered heavy-atom span + 12 Å box rule, minimum side 20 Å, maximum side 30 Å;
- same-frame, symmetry-aware heavy-atom RMSD with no translation, rotation, superposition or fitting;
- rank-1 RMSD <= 2 Å as the primary localization success threshold.

## Planned reporting

The result will report separately:

1. the **15-case prospective success fraction** — primary REDOCK-003 generalization endpoint;
2. the prior REDOCK-002 5-case result — historical context only;
3. a 20-case combined descriptive summary with explicit observed/prospective labels;
4. per-case pose-1 RMSD, minimum RMSD, Vina rank-1 score, pose count and first-loss state;
5. a portable scientific result hash excluding runtime/path/log noise.

No change to protocol or case selection is permitted in response to a docking outcome without a new explicit benchmark version.
