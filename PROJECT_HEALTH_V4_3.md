# Project Health v4.3

Status: **PASS** on `research-os-v1.3`.

- Five external validation campaigns attempted.
- Independence assessment present for all campaigns.
- One independent non-overlapping source executed under a frozen protocol.
- `FAILED_VALIDATION` preserved as a valid scientific outcome.
- `NO_ELIGIBLE_EXTERNAL_DATA` and `BLOCKED_EXTERNAL` outcomes preserved.
- Claim revision is append-only and EvidenceLevels were not changed.
- Fresh external-validation Ledger and bundle verify PASS.
- Python 3.11/3.12 regression remains green before this release commit.

The v4.3 result does not close the solubility external-validity gap; it makes
the gap more precise: the model's current data-supported boundary is not
portable to the tested DLS-100 OOD population under the locked protocol.

`Biolab/` and `formolecular/` remain preserved. No retirement or deprecation
gate has been satisfied for either legacy tree.
