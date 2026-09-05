# Research OS v4.3 — External Validation Campaigns

Status: **PASS**

Branch: `research-os-v1.3`

Five validation campaigns were attempted after the v4.1 impact deployment and
v4.2 corpus readiness gate. Every campaign carries an independence assessment.
One truly independent, non-overlapping public solubility source was evaluated
once against the frozen V39 model before any retraining or threshold change.

The result is a preserved `FAILED_VALIDATION`, not a promoted model: all 56
DLS-100 unique records were OOD under the locked Morgan/Tanimoto threshold.
The claim history was revised to state that the existing support is
sample-specific and cannot be generalized unrestrictedly.

Campaign summary:

| Campaign | Result | Scientific meaning |
| --- | --- | --- |
| DLS-100 unique solubility | `FAILED_VALIDATION` | Independent/non-overlapping source; all records OOD and condition semantics are not identical |
| COX-2 / RCSB 4Z0L | `NO_ELIGIBLE_EXTERNAL_DATA` | Alternate structure is still E2 structural comparison; Vina cross-structure run unavailable |
| Cantera ↔ experiment | `BLOCKED_EXTERNAL` | No condition-matched downloaded/hashed/parsed experiment |
| NASA battery ALT | `NO_ELIGIBLE_EXTERNAL_DATA` | Candidate metadata found; exact artifact not ingested in this run |
| Hydrogen materials | `BLOCKED_EXTERNAL` | Public candidates found; no condition-complete record was matched |

No external source was relabeled as E4/E5 validation of a computational claim,
and no EvidenceLevel was changed.

Machine artifact: `.research-os-live-4.3/external-validation-campaigns.json`.
