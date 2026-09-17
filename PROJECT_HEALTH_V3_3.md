# Project health — Research OS 3.3

Branch: `research-os-v1.3`
Version: `3.3.0`
Scope: Research OS only; `Biolab/` and `formolecular/` remain outside the
boundary.

## Scientific coverage

- 11 source-backed real problems are registered across all required domains.
- 13 primary/official source records are registered with quality metadata and
  URLs.
- Three primary and two secondary campaigns were selected by live
  `gpt-5.6-luna` through separate discovery and constrained-selection calls;
  the deterministic provider exists only for CI.
- AqSolDB real-data campaign: scaffold split, real NumPy/ridge model, OOD and
  residual-calibrated interval analysis, failure segmentation and explicit
  external-test promotion gap.
- Cantera campaign: H2/CH4 E3 equilibrium runs with declared conditions,
  mechanism provenance, bundles, Ledger registration and rerun comparison.
- Materials campaign: source synthesis stops at `INSUFFICIENT_EVIDENCE` when
  material/condition-matched measurements are absent.
- Battery and pharma reach first gates; target species is mandatory and absent
  species normalizes to `UNKNOWN`.
- Final live acceptance (`.research-os-live-3.3-final7`) passed with five
  campaigns: 1 `SUPPORTED`, 1 `PARTIALLY_SUPPORTED`, 2
  `INSUFFICIENT_EVIDENCE`, and 1 `INDETERMINATE`.

## Milestone metrics

| Metric | Recorded value |
|---|---:|
| Real problems discovered | 11 |
| Source records registered | 13 |
| Campaigns started/completed | 5 / 5 |
| Supported campaign results | 1 |
| Partially supported results | 1 |
| Insufficient-evidence results | 2 |
| Indeterminate results | 1 |
| Supported computational claims | 3 Cantera E3 claims plus bounded source/ML claims at their declared status |
| Rejected/negative results | promotion not accepted; universal GRI30 safety claim rejected; generic qualification claim rejected |
| Molecular held-out OOD fraction | 0.80 |
| Molecular observed interval coverage | 0.70 |
| Campaign research gaps identified | 5 primary gap records, plus source/engine/data blockers |

## Evidence and reproducibility controls

- Live Codex is a reasoning/planning/narration provider only; it cannot create
  Evidence, claims, runs, sources, conditions or bundles.
- Source content is DATA, not instructions; no source injection is promoted to
  a plan or evidence record.
- OOD molecular predictions remain visible for audit and are excluded from
  normal ranking. Intervals report observed coverage, not certainty.
- Every executable run is sealed and linked to a verified bundle and Ledger
  record. Reports retain `FIRST_LOSS` and `FIRST_DIVERGENCE`.
- Cross-campaign memory is read-only context over campaign history, Ledger
  records and reviewed citations.

## Validation record

The committed acceptance suite contains 143 tests on Python 3.11 and 143 on
Python 3.12, including `tests/test_v33_campaign_contract.py` (8 PASS). The live campaign
script passed with runtime model `gpt-5.6-luna`; its JSON is intentionally
ignored because it contains environment-specific runtime IDs and hashes.

Known evidence ceilings are intentional: no local Vina executable/prepared
receptor, no downloaded battery record, no condition-matched materials test,
and no independent external AqSolDB test source.
