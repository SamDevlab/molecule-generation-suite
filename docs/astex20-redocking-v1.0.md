# REDOCK-003 / Astex-20 redocking benchmark v1.0

Status: **prospective 15-case result observed; reporting-layer aggregate corrected after run 279**.

## Purpose

REDOCK-003 extends the Astex Diverse Set evaluation from the five already-observed REDOCK-002 cases to an Astex-20 view while keeping the new scientific endpoint genuinely prospective.

The benchmark is split into two blocks:

- **historical Astex block (5 cases):** the already-observed REDOCK-002 cases;
- **prospective Astex extension (15 cases):** structurally eligible cases selected and frozen before any REDOCK-003 Vina execution.

The primary endpoint is the 15-case prospective extension. The 20-case aggregate is descriptive only and must not be presented as if all twenty cases were unseen.

## Frozen source universe and ranking

Source set: Astex Diverse Set, 85 PDB/CCD complex identifiers.

```text
source-list SHA-256 = 7c2bc6702b62abe282bbd6f67146ec071c623cc3bd17d4683c1afd898b2df5ef
selection key       = SHA-256("research-os.astex20.v1.0:" + PDB_CCD)
```

The already-observed REDOCK-002 complexes `1V0P_PVB`, `1W1P_GIO`, `2BM2_PM2`, `1VCJ_IBA` and `1TT1_KAI` were removed before ranking. The remaining 80 were sorted lexicographically by the full selection-key digest.

No target class, ligand size, Vina score, pose, RMSD or human preference enters the ranking.

## Preflight result — run 275

The no-docking structural preflight completed successfully in GitHub Actions run `275` / `34544166868`.

```text
screened candidates       = 24
selected prospective      = 15
rejected before fill      = 9
selection_manifest_hash   = 8119f2ece8bd1be2612e74520871cbeddb5fa9be7951d23c88db478e122a1690
artifact_id               = 10178395083
artifact_sha256           = 56240b2eb1493190e7902ac26a026183a906d0e4a5b0f1068cdd43f185b62314
docking_executed          = false
vina_imported_or_invoked  = false
```

All nine pre-cohort rejections were structural multiplicity failures: the PDB contained more than one instance of the frozen CCD ligand. Their selection ranks were `4, 5, 6, 7, 12, 15, 16, 17, 23`. No rejection depended on a docking outcome.

## Frozen prospective cohort

The successful preflight evidence was inspected and then committed as explicit `RedockingCase` values in commit `f76978ce44b282c93290ad65ff2280caa018524e`, before adding REDOCK-003 Vina execution.

| Case | Complex | Ligand chain | Receptor chains | Resolution (Å) |
|---|---|---|---|---:|
| ATX-001 | 1R1H / BIR | A | A | 1.95 |
| ATX-002 | 1SJ0 / E4D | A | A | 1.90 |
| ATX-003 | 1MEH / MOA | A | A | 1.95 |
| ATX-004 | 1V4S / MRK | A | A | 2.30 |
| ATX-005 | 1T40 / ID5 | A | A | 1.80 |
| ATX-006 | 1PMN / 984 | A | A | 2.20 |
| ATX-007 | 1KZK / JE2 | A | A+B | 1.09 |
| ATX-008 | 1HQ2 / PH2 | A | A | 1.25 |
| ATX-009 | 1S3V / TQD | A | A | 1.80 |
| ATX-010 | 1Z95 / 198 | A | A | 1.80 |
| ATX-011 | 1UNL / RRC | A | A | 2.20 |
| ATX-012 | 1TOW / CRZ | A | A | 2.00 |
| ATX-013 | 1UOU / CMU | A | A | 2.11 |
| ATX-014 | 1P2Y / NCT | A | A | 2.30 |
| ATX-015 | 1L7F / BCZ | A | A | 1.80 |

Changing any of these cases/chains in response to a later score or RMSD requires a new explicit benchmark version.

## Structural eligibility rule

The preflight walked candidates in frozen hash order and accepted the first 15 satisfying all of the following without invoking Vina:

1. RCSB PDB download succeeds;
2. exactly one heavy-atom instance of the frozen CCD ligand exists in the PDB;
3. at least one polymer author chain has a heavy atom within 8.0 Å of the ligand;
4. the RCSB ligand-instance SDF downloads and sanitizes;
5. PDB and SDF ligand heavy-atom counts agree;
6. the unchanged REDOCK v1.2 native-centered box rule is inside its frozen domain;
7. structure resolution is parseable from the PDB.

The deterministic receptor-chain rule is: all author chains with at least one protein heavy atom within 8.0 Å of any native-ligand heavy atom.

## Frozen docking protocol

After the cohort freeze, REDOCK-003 reuses the validated REDOCK-001 v1.2 executor/evaluator unchanged:

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

A scientific failure does not make the workflow fail merely because RMSD exceeds 2 Å; scientific outcomes are recorded rather than optimized away.

## First interpretable prospective execution — run 279

GitHub Actions run `279` / `34544932121` executed commit `e2fedd02e7241f12c43d45d2f5cc448f8d9f3af2` after the pre-result case-count guard correction. Core Python 3.11/3.12, Cantera, REDOCK-001 regression, structural preflight and REDOCK-003 all completed successfully.

Environment identity:

```text
Python                 = 3.12.14
Open Babel             = 3.1.1
AutoDock Vina          = 1.2.7
Vina binary SHA-256    = f31f774f723bba7bbe6e9d1c47577020eea9a8da16424284c043d22593570644
```

The frozen prospective outcomes were:

| Case | Pose-1 RMSD (Å) | Minimum RMSD (Å) | Vina rank-1 (kcal/mol) | Poses | Rank-1 <=2 Å |
|---|---:|---:|---:|---:|---|
| ATX-001 | 1.261 | 1.261 | -9.563 | 13 | yes |
| ATX-002 | 0.962 | 0.962 | -11.217 | 4 | yes |
| ATX-003 | 7.228 | 3.992 | -7.376 | 20 | no |
| ATX-004 | 5.656 | 5.656 | -7.417 | 20 | no |
| ATX-005 | 1.122 | 1.122 | -10.367 | 18 | yes |
| ATX-006 | 7.016 | 1.589 | -8.987 | 19 | no |
| ATX-007 | 1.902 | 1.902 | -11.106 | 17 | yes |
| ATX-008 | 0.546 | 0.546 | -8.229 | 20 | yes |
| ATX-009 | 6.498 | 0.459 | -9.454 | 20 | no |
| ATX-010 | 0.489 | 0.489 | -10.328 | 5 | yes |
| ATX-011 | 0.534 | 0.534 | -8.897 | 20 | yes |
| ATX-012 | 4.588 | 0.702 | -7.900 | 20 | no |
| ATX-013 | 6.473 | 0.621 | -8.289 | 20 | no |
| ATX-014 | 4.385 | 4.385 | -6.033 | 20 | no |
| ATX-015 | 1.577 | 1.577 | -7.552 | 20 | yes |

Primary prospective endpoint:

```text
rank-1 RMSD <= 2 Å       = 8 / 15 = 53.3333333333%
mean pose-1 RMSD          = 3.3491571633530675 Å
median pose-1 RMSD        = 1.9023353234713458 Å
technically evaluable     = 15 / 15
scientific_result_hash    = e4e4693f890b86327fac16b547966fe64862045d1562c4340dcc3d7d4a06b762
execution_hash            = 4b2e438dd7e78462f5daae62712def563df96a90aa79ef22180973d70fce1420
summary_hash              = 7fff66446032e26e4fa77d4c348a5cc5de499495025fcbf979f0e5124a316fd8
artifact_id               = 10179158216
artifact_zip_sha256       = 5d4e8140f7de1c18f6a7eb0ba449c16d2eb1f1b3fa7d71c6818fd0fa3493225c
```

`status = PASS` for all 15 cases means that the docking/RMSD evaluation completed and produced an evaluable pose-1 RMSD. It does **not** mean that all 15 met the <=2 Å scientific success criterion.

### Secondary sampling/ranking diagnostic

This was not the pre-registered primary endpoint, but the already-generated returned poses permit a useful diagnosis without rerunning or retuning anything:

- 12/15 cases had at least one returned pose with RMSD <=2 Å;
- `ATX-006`, `ATX-009`, `ATX-012` and `ATX-013` contained a <=2 Å pose but did not rank it first;
- `ATX-003`, `ATX-004` and `ATX-014` had no returned pose <=2 Å among the frozen set of modes.

This separates rank-1 selection error from failure to sample a <=2 Å pose under the frozen search protocol. It is diagnostic only and does not replace the 8/15 primary endpoint.

## Reporting-layer defect found after run 279

Run 279 correctly reported the primary threshold field `pose_1_rmsd_le_2_angstrom.count = 8` with denominator 15. However, the top-level descriptive Astex-20 helper incorrectly treated `passing_rmsd_cases = 15` as if it meant 15 threshold successes. In the shared summary, `passing_rmsd_cases` means only that RMSD was technically evaluable.

Consequently the run-279 descriptive value `17/20 = 85%` is **invalidated and must not be cited**. It did not alter the frozen docking outcomes or the 15-case primary endpoint.

The corrected descriptive calculation is:

```text
historical REDOCK-002       = 2 / 5
prospective REDOCK-003      = 8 / 15
combined descriptive only   = 10 / 20 = 50%
```

The reporting helper now reads the explicit `pose_1_rmsd_le_2_angstrom.count` and `.denominator` fields and uses threshold-specific output names. A regression test deliberately supplies `passing_rmsd_cases = 15` together with threshold count `8` and requires the combined result to remain `10/20 = 50%`.

The primary `scientific_result_hash` excludes the top-level descriptive Astex-20 context and remains bound to the frozen prospective cases, records and primary summary. The reporting correction therefore does not reinterpret or alter the underlying prospective experiment.

## Reporting contract

The result reports separately:

1. the **15-case prospective success fraction** as the primary REDOCK-003 generalization endpoint;
2. the immutable prior REDOCK-002 result (`2/5`, scientific hash `8540d1acf507047af402013f9d9d5d6ad93c5ac63123b95ab2876a46ecabb00c`) as historical context only;
3. a 20-case combined descriptive summary with explicit historical/prospective labels;
4. per-case pose-1 RMSD, minimum RMSD, Vina rank-1 score, pose count and first-loss state;
5. a portable scientific result hash for the 15-case prospective experiment, excluding runtime/path/log noise.

## Interpretation boundary

REDOCK-003 measures pose-localization reproduction for this frozen prospective Astex extension under this exact protocol. It does not establish measured affinity, potency, selectivity, biological activity, toxicity, safety, efficacy, clinical performance or universal docking correctness.
