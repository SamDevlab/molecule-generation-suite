# RANK-001 / Astex-20 pose-ranking diagnostic v1.0

Status: **retrospective deterministic diagnostic over sealed REDOCK-003 run 280**.

## Purpose

RANK-001 answers a narrower question raised by REDOCK-003: when rank-1 pose localization fails, did the returned pose set contain a native-like pose at all, and if so, did AutoDock Vina rank it first?

This is **not a new holdout** and is not independent evidence of generalization. The same already-observed 15 prospective Astex cases from REDOCK-003 are re-read without any new docking, optimization, parameter change, model fitting, or case selection.

## Sealed source

The diagnostic is bound to the final non-regression REDOCK-003 artifact from GitHub Actions run `280` / `34546751594`:

```text
source benchmark             = REDOCK-003
source protocol              = research-os.redocking.astex20.v1.0
evaluator protocol           = research-os.redocking.v1.2
artifact_id                  = 10179660428
artifact_zip_sha256          = fb0dadb67186eb2899b4c79f0a0a67683a16783cf834c587d43cdac076a98b7f
source scientific_result_hash= e4e4693f890b86327fac16b547966fe64862045d1562c4340dcc3d7d4a06b762
source summary_hash          = 7fff66446032e26e4fa77d4c348a5cc5de499495025fcbf979f0e5124a316fd8
sealed snapshot sha256       = 1f8a7fe04550003e79711918d0c30e1c42b3ddfae072b4dbab179263d01f262f
```

The versioned snapshot contains only the source identities plus the already-produced ordered per-pose Vina scores and same-frame RMSDs required for this diagnostic. `load_sealed_input()` rejects any byte-level change to that snapshot and the analyzer separately validates source identities, criterion, case count, and matching non-empty score/RMSD arrays.

## Frozen diagnostic criterion

A returned pose is localization-successful when its symmetry-aware heavy-atom RMSD in the receptor coordinate frame is `<= 2.0 Å`, using the already-frozen REDOCK v1.2 evaluator. Coordinate fitting remains forbidden.

The diagnostic reports cumulative recovery at `top-1`, `top-3`, `top-5`, `top-10`, and any returned pose. These are retrospective summaries of the same pose sets, not newly selected endpoints.

## Result

```text
top-1 recovery    =  8 / 15 = 53.33%
top-3 recovery    = 11 / 15 = 73.33%
top-5 recovery    = 12 / 15 = 80.00%
top-10 recovery   = 12 / 15 = 80.00%
any returned pose = 12 / 15 = 80.00%
```

Failure decomposition:

```text
rank-1 localization success                  = 8
rank-1 failure with lower-ranked <=2 Å pose  = 4
no returned <=2 Å pose                       = 3
```

The four ranking-recoverable cases are:

| Case | Rank-1 RMSD (Å) | First <=2 Å rank | Score penalty vs rank 1 (kcal/mol) |
|---|---:|---:|---:|
| ATX-006 | 7.016 | 5 | +0.678 |
| ATX-009 | 6.498 | 3 | +0.469 |
| ATX-012 | 4.588 | 2 | +0.144 |
| ATX-013 | 6.473 | 3 | +0.589 |

For these four cases, the first native-like pose appears at mean rank `3.25` (median `3`). Its Vina score is worse than the selected rank-1 pose by mean `0.470 kcal/mol` (median `0.529 kcal/mol`).

The three cases with no returned pose within 2 Å are `ATX-003`, `ATX-004`, and `ATX-014`.

```text
diagnostic_hash = 36af521a178327b77e19a9bb2338637627312293d8ebddd7418f0b6c96a2b238
```

## Interpretation

Within the already-observed REDOCK-003 pose sets, four of seven rank-1 localization failures are consistent with a **ranking limitation**: a <=2 Å pose exists, but Vina's score places another pose above it. Three failures remain **pose-set misses under this protocol**, because no returned pose reaches <=2 Å. This diagnostic alone does not identify why those three pose sets missed the threshold.

The small score differences in the four recoverable cases show that native-like and selected non-native poses can be close under the frozen Vina scoring function. They do **not** prove that a different scorer would generalize, nor that re-ranking would improve affinity prediction or biological performance.

## Claim boundary

RANK-001 does not add independent test cases, does not upgrade the REDOCK-003 evidence level, and does not establish binding affinity, potency, selectivity, biological activity, safety, efficacy, clinical performance, or universal docking correctness. It is a deterministic post-hoc diagnostic intended to guide the next prospective experiment.
