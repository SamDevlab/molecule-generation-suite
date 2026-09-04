# Security audit — Research OS 4.0

The v4.0 security audit scans the active `src/` implementation and exercises
the policy boundary in the 50-case stress matrix.

| Check | Result |
|---|---|
| `shell=True` / `os.system` / unsafe deserialization | PASS; no active hits |
| subprocess execution | PASS; explicit argument lists and bounded calls |
| source and user-corpus prompt injection | PASS; content is data only |
| path traversal and argument injection | PASS; typed artifact/tool guards |
| secrets | PASS; audit redaction remains active |
| loop limits | PASS; immutable bounded limits |
| PlanValidator / typed tool registry | PASS |
| EvidenceLevel manipulation | PASS; live authority fields rejected |
| source verification bypass | PASS |
| sealed-run mutation | PASS; mutation raises `RunMutationError` |

Historical legacy code was not deleted to satisfy a scanner. The preserved
`Biolab/` and `formolecular/` trees remain documented as MIGRATING, and the
machine-readable audit is `.research-os-live-4.0/master-validation.json`.
