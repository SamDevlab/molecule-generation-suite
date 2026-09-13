# APODOCK-001 v1.1 postmortem

This document records a post-result diagnostic only. It does not replace the
sealed v1.1 analysis, change the protocol, or authorize another prospective
run.

## Scope and boundary

PR #35 was reviewed and merged into `research-os-v1.3` at merge commit
`264c8b833d3785d4395b7940714d33ad80d53e1f`. The v1.1 raw seal remains
unchanged:

- protocol: `research-os.apodock001.protocol.v1.1+b1a3c7b16db63ea4`
- protocol hash: `b1a3c7b16db63ea426202a82db2551cc07301e34ea5584bfab75706681481a9e`
- run: `research-os.apodock001.run.v2+852d9aa525862df6`
- raw-results seal: `ee31206f4d97e8fc5085374dfae5d85b23844bf2d969b9fe4b1c972d52cc7715`

The official v1.1 result is still the result in
`runs/apodock001-v1.1/analysis-manifest.json`: five determinate cases, five
indeterminate cases, primary success `0/5`, and secondary success `0/5`.
Nothing in this postmortem is part of that preregistered primary analysis.

The four new conversion failures were audited from the sealed raw PDBQT:
APD-001, APD-002, APD-005, and APD-008. Their raw files were not rewritten,
re-sealed, rerun, or replaced.

## Diagnostic adapter

`research_os.docking.apodock001_raw_coordinate_adapter` is explicitly marked
`POSTMORTEM_DIAGNOSTIC_ONLY`. It:

1. parses pose order, scores, and Cartesian coordinates directly from the
   sealed raw PDBQT;
2. checks the raw atom identity sequence against a preserved converted
   representation template;
3. copies raw coordinates into that template without changing the raw file;
4. calls the existing same-frame, symmetry-aware heavy-atom evaluator.

The adapter does not call Vina or Open Babel, does not infer connectivity from
distances, does not fit or superpose a pose, and does not use
`rdMolAlign.GetBestRMS`, `AlignMol`, or Kabsch predicted-to-reference fitting.
The representation template supplies connectivity; the raw PDBQT supplies
coordinates. If that identity cannot be proven, the adapter fails closed.

The diagnostic identity is:

`research-os.apodock001.postmortem.raw-coordinate-adapter.v1+65c84622c2697b8e`

The reproducible outputs are
`postmortem/apodock001-v11-diagnostic-analysis.json` and
`postmortem/apodock001-v102-v11-diagnostic-comparison.json`. Every record is
labelled `POSTMORTEM_DIAGNOSTIC_ONLY` and
`NOT_PART_OF_PREREGISTERED_PRIMARY_ANALYSIS`.

## Finding for the four conversion failures

The strict v1.1 repair adapter failed before the official evaluator. The raw
coordinate diagnostic is determinate for all 20 poses in each of the four
cases when paired with the preserved representation templates. This shows
that the sealed raw coordinates are diagnostically usable, but it does not
retroactively convert the official v1.1 indeterminates into official primary
metrics.

| Case | v1.0.2 pose 1 | v1.0.2 best | v1.1 diagnostic pose 1 | v1.1 diagnostic best | v1.1 diagnostic best pose |
| --- | ---: | ---: | ---: | ---: | ---: |
| APD-001 | 5.606384 | 3.323511 | 5.606384 | 3.047304 | 19 |
| APD-002 | 7.231625 | 4.762285 | 7.292139 | 4.762285 | 18 |
| APD-005 | 3.164066 | 2.556364 | 3.116927 | 2.556364 | 7 |
| APD-008 | 6.384141 | 4.894072 | 6.378692 | 5.300286 | 14 |

These values are diagnostic comparisons only. They are not substituted into
the v1.1 analysis manifest.

## Exhaustiveness assessment

v1.1 used exhaustiveness `32`; v1.0.2 used `16`. The four diagnostic paired
cases do not show a consistent improvement: one best-of-20 value improves,
one is unchanged, and two worsen; pose-1 deltas also change in both
directions. The three cases determinate in both official analyses likewise
do not establish a systematic improvement. The representation-path failure
also means the v1.1 official denominator cannot be used as a clean
exhaustiveness comparison.

Therefore exhaustiveness `32` is **not supported as a scientific basis for a
new protocol** by this postmortem. No v1.2 protocol was frozen. A future
protocol would require an explicitly reviewed representation contract and a
new preregistration; it must not reuse these post-result diagnostics as if
they were a prospective benchmark.

## Operational metadata

The `.gitattributes` rules for v1.1 PDBQT/SDF/stdout/stderr are classified as
`POST_RESULT_OPERATIONAL_BYTE_PRESERVATION_METADATA`. They protect byte
addressability across Windows checkouts and do not change executed bytes,
parameters, analysis, or raw hashes.

No v1.0.2 or v1.1 docking was rerun. No Vina process was started during this
postmortem. The prospective boundary remains intact.
