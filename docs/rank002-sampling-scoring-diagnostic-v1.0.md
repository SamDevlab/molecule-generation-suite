# RANK-002 — sampling vs scoring diagnostic v1.0

## Role

RANK-002 is a **retrospective diagnostic**, not a new prospective benchmark and not an independent holdout. It analyzes pose sets that were already produced and sealed by REDOCK-003 and CROSSDOCK-001.

The question is narrower than “did docking succeed?”:

1. **RANK1_SUCCESS** — Vina rank 1 already has same-frame symmetry-aware heavy-atom RMSD <= 2 Å.
2. **RANKING_MISS** — rank 1 is >2 Å, but at least one returned pose is <=2 Å.
3. **POSE_SET_MISS** — no returned pose is <=2 Å.

`POSE_SET_MISS` is intentionally not called a “search failure”. The observed pose set can be limited by search, rigid-receptor mismatch, preparation, or other protocol assumptions; this diagnostic does not identify one unique cause.

## Sealed sources

No new docking is executed.

| Source | Run | Artifact | ZIP SHA-256 | Scientific hash | Cases |
| --- | ---: | ---: | --- | --- | ---: |
| REDOCK-003 | `34546751594` | `10179660428` | `fb0dadb67186eb2899b4c79f0a0a67683a16783cf834c587d43cdac076a98b7f` | `e4e4693f890b86327fac16b547966fe64862045d1562c4340dcc3d7d4a06b762` | 15 |
| CROSSDOCK-001 v1.1 first complete run | `34615447564` | `10271091364` | `a5094acefffa7d52e30d887ef765d7524e728faff0beb9cf5eb6048caa663e91` | `d1d5b980816837301c1fe70d2c0a397ba4a0e662bced7aa17bb118c61f2bff16` | 10 |

The compact snapshot at `validation/rank002-sampling-scoring-input-v1.0.json` is derived directly from those two evidence bundles. It contains the source identities and only the per-case fields needed to reproduce this diagnostic: pose count, rank-1 RMSD/score, first <=2 Å pose rank/RMSD/score, and best-returned RMSD/score.

Snapshot SHA-256:

```text
3f256dada77e5eb030d5c281359b7a154bdb683a1d960047c9bfbc31349b5e9c
```

## Results

### REDOCK-003

- rank-1 success: **8/15 = 53.3%**
- ranking miss: **4/15 = 26.7%**
- pose-set miss: **3/15 = 20.0%**
- any returned pose <=2 Å: **12/15 = 80.0%**
- first near-native ranks for the four ranking misses: `[5, 3, 2, 3]`
- score penalty of first near-native pose versus rank 1: `[0.678, 0.469, 0.144, 0.589]` kcal/mol
- mean score penalty: **0.470 kcal/mol**

### CROSSDOCK-001

- rank-1 success: **3/10 = 30.0%**
- ranking miss: **2/10 = 20.0%**
- pose-set miss: **5/10 = 50.0%**
- any returned pose <=2 Å: **5/10 = 50.0%**
- first near-native ranks for the two ranking misses: `[4, 6]`
- score penalties: `[0.648, 0.971]` kcal/mol
- mean score penalty: **0.8095 kcal/mol**

### Descriptive cross-cohort contrast

The pose-set-miss fraction is **20% in REDOCK-003** and **50% in CROSSDOCK-001**, a descriptive difference of **+30 percentage points** in the cross-docking cohort. Rank-1 success falls from 53.3% to 30%.

This comparison is **not a randomized or matched causal estimate**. The two cohorts differ in receptor condition and case composition. It supports the narrower observation that the tested non-cognate holo cohort contains a larger fraction of cases where no <=2 Å pose was returned.

Across the six ranking misses from both cohorts:

- first near-native rank: `[5, 3, 2, 3, 4, 6]`
- mean rank: **3.833**
- median rank: **3.5**
- score penalty versus rank 1: `[0.678, 0.469, 0.144, 0.589, 0.648, 0.971]` kcal/mol
- mean penalty: **0.5832 kcal/mol**
- median penalty: **0.6185 kcal/mol**
- all six penalties are positive.

A positive score penalty means the first <=2 Å pose received a numerically worse Vina score than rank 1. These differences diagnose ranking behavior; they are **not binding free energies** and do not establish affinity, potency, efficacy, safety, or biological activity.

## Deterministic diagnostic identity

Expected diagnostic hash:

```text
e9bd4c6d3dd6ce88381cc85edf4cb2f74782b67d172b75659c7178bd0b86852d
```

The diagnostic hash commits to the sealed source identities, all per-case classifications and measurements, separated cohort summaries, and the explicitly descriptive pooled ranking-miss summary.
