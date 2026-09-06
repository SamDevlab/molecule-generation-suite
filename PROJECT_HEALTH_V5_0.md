# Project health — v5.0 attempt

## Status

`READY_FOR_TOP_LEVEL_LIVE_EXECUTION`; release remains `BLOCKED_BEFORE_PASS` and the published package remains `4.5.0`.

## Healthy properties

The attempt retained the canonical evidence levels, sealed runs and bundles, append-only impact/challenge records, explicit OOD and uncertainty, declared units/conditions/species, and v4.2 private-corpus separation. Attempts 1–5 are preserved at `.research-os-live-5.0-top-level/` and the four numbered namespaces; `Biolab/` and `formolecular/` were not modified. The legacy components remain preserved and are not deprecated.

## Blocking property

The repository-side `CodexLiveProvider` is available as a configured transport. Attempt 5 proved 30 real calls and process cleanup, then exposed a per-call context propagation defect: consistency metadata was inside the scientific payload but absent from the transport context, so the outer envelope was selected. The provider now forwards only an explicit per-call allowlist, preserves security-sensitive global owner/state fields, and keeps calls isolated. The transport boundary still selects the strict consistency schema before `codex exec`, records `output_contract` and `output_schema_name`, freezes Run A's literal support basis for independent Run B, and compares canonical scientific signatures. It did not replace the Live provider with `CodexTestProvider` or reinterpret deterministic answers as Live review.

## Next gate

The top-level launcher is implemented and ready. Run only the bounded v5.0 Live stages from a genuinely top-level Codex CLI owner when it can return structured, grounded responses. Do not rerun the stable scientific workflows merely to change the release label. See [TOP_LEVEL_LIVE_ACCEPTANCE_V5_0.md](TOP_LEVEL_LIVE_ACCEPTANCE_V5_0.md).
