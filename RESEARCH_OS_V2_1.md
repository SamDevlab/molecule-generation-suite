# Research OS v2.1 — chat-first service

`research_os.service` is the UI boundary. `OracleService` supports `ask`,
`continue_research`, `get_plan`, `get_results`, `get_evidence`, `get_sources`,
`get_runs`, `get_lineage`, `compare_runs` and evidence-based ranking
explanations. It produces a `ResearchJob` with QUEUED/PLANNING/VALIDATING/
RUNNING/WAITING/COMPLETED/FAILED/INDETERMINATE/CANCELLED states and explicit
progress events.

The frontend does not import Lab internals. The chat surface is the normal
entry point; technical users can inspect plans, runs, datasets, models,
bundles, engine manifests, hashes and provenance through service responses.

No web framework is forced into the scientific core. `web/README.md` defines
the integration boundary for a later browser implementation.

