# Project health — v5.0 attempt

## Status

`READY_FOR_TOP_LEVEL_SCHEMA_SMOKE`; release remains `BLOCKED_BEFORE_PASS` and the published package remains `4.5.0`.

## Healthy properties

The attempt retained the canonical evidence levels, sealed runs and bundles, append-only impact/challenge records, explicit OOD and uncertainty, declared units/conditions/species, and v4.2 private-corpus separation. Attempts 1–6 are preserved at `.research-os-live-5.0-top-level/` and the numbered namespaces; `Biolab/` and `formolecular/` were not modified. The legacy components remain preserved and are not deprecated.

## Blocking property

The repository-side `CodexLiveProvider` is available as a configured transport. Attempt 5 proved 30 real calls and process cleanup, Attempt 6 proved that routing is correct (`CONSISTENCY`/`live_consistency.schema.json`), and the first real schema smoke completed the provider/schema/grounding/consistency path successfully. Its only blocker was a cleanup event aggregation bug: the historical `RUNNING` event was treated as still active after the same PID emitted `EXITED`. The provider-facing schema is structurally portable, cross-field semantics remain deterministic validators, and recognized schema-admission failures receive a bounded typed diagnostic. The provider still forwards only an explicit per-call allowlist, preserves security-sensitive global owner/state fields, keeps calls isolated, freezes Run A's literal support basis for independent Run B, and compares canonical scientific signatures. It did not replace the Live provider with `CodexTestProvider` or reinterpret deterministic answers as Live review.

## Next gate

Run the one-call schema smoke from a genuinely top-level terminal first; only its `PASS` permits the bounded v5.0 Live stages. Do not rerun the stable scientific workflows merely to change the release label. See [TOP_LEVEL_LIVE_ACCEPTANCE_V5_0.md](TOP_LEVEL_LIVE_ACCEPTANCE_V5_0.md).
