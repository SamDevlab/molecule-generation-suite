# Security audit — v5.0 attempt

The final runner report records `security_audit.status = PASS`. The audit covered the v5.0 execution surface and the new impact, private-corpus, and external-validation contracts.

Checked properties include shell execution with `shell=False`, absence of unsafe deserialization and dynamic SQL, path confinement, private-source review gating, no arbitrary download execution, no environment mutation, PlanValidator presence, bounded iteration, no file leakage, and safe temporary tamper probes.

Scientific safety checks also passed: Codex created zero Evidence, no EvidenceLevel changed, no E1/E2/E3 inflation occurred, OOD/uncertainty remained visible, missing battery fields were not imputed, Cantera remained E3 rather than experiment, and blocked/no-progress paths stopped.

This PASS is a security/scientific-integrity result for the attempted runner. It does not override the separate `CODEX_LIVE` operational blocker and does not authorize a 5.0 release.

The recovery boundary audit additionally passed fixed executable/schema allowlists, fixed argv with `shell=False`, audited environment forwarding, byte-only diagnostic capture, bounded timeout/retry behavior, schema fail-closed handling, and recursive Live-provider rejection. Its evidence is in `.research-os-live-5.0-recovery/live-boundary-diagnostics.json`; this still does not constitute a completed Live review or v5.0 release.

The grounding recovery adds a second fail-closed boundary: only literal IDs from `ALLOWED_GROUNDED_RECORD_IDS` may ground a response, `GROUNDED` cannot carry an empty list, `NO_GROUNDED_ANSWER` cannot carry IDs, and rejected responses persist only safe final fields plus hashes and validation codes. The consistency response now has a strict six-field schema, a bounded canonical limitation-code enum, and a required primary record; limitation prose is not parsed. Consistency Run B additionally receives only Run A's frozen support basis; globally known IDs outside that basis and plausible invented IDs remain failures. The final gate preserves provider/process, underlying grounding, and consistency failures in precedence order. The worktree policy allows only recognized JSON artifacts inside `.research-os-live-5.0-top-level-attempt-N/`; source, test, tool, documentation, configuration, and unknown artifact changes remain dirty.
