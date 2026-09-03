# Research OS 3.1 — Operational Oracle Experience

Status: remotely validated on `research-os-v1.3`.

## Product boundary

The user-facing path is:

`chat → ResearchQuestion → ResearchPlan → PlanValidator → ResearchJob → ResearchOrchestrator → Labs → Evidence → OracleAnswer`

The web layer only calls typed `OracleService` methods. Conversation messages
are persisted separately from scientific Evidence. The Ledger remains the
source of truth for sealed runs, bundles, evidence and lineage.

## Local operation

```bash
py -3.11 -m pip install -e .
py -3.11 -m research_os.web --port 8000
```

The application stores sessions/jobs in `ResearchStore` SQLite and scientific
execution in the existing `RunRegistry`. A reload reopens sessions, messages,
jobs, answers and references. Non-terminal jobs found after restart are marked
`FAILED/PROCESS_RESTARTED`; no work is silently resumed.

When the project `.venv` is used, Cantera 3.2.0 and RDKit are available for the
safe reference path. The system Python remains a valid lightweight runtime
where optional engines report their actual unavailable state.

## Experience surface

The chat-first UI provides:

- persistent research history and `Continue`;
- current status, progress and `FIRST_LOSS`;
- expandable plan steps with inputs, dependencies and evidence requirement;
- result, Evidence, source, run and lineage views;
- a system engine-status dialog;
- a Knowledge review queue and user-material import boundary;
- safe error responses without stack traces.

The API is intentionally small and transport-safe: `/api/chat`, session and
job reads, plan/results/evidence/sources/runs/lineage views, engine status,
Knowledge import/review and a fail-closed explanation endpoint.

## Scientific boundaries

`CODEX_TEST` is `INTEGRATION_TEST`, has no external API, is not an evidence
provider and is not a production LLM. It proposes structured plans only.

The canonical scientific levels are `E0_HEURISTIC`, `E1_ML`,
`E2_COMPUTATIONAL`, `E3_PHYSICS`, `E4_CURATED_EXPERIMENTAL` and
`E5_VALIDATED_EXPERIMENTAL`. Retrieval adds citations only; it never promotes
Evidence. Computational docking cannot produce clinical, cure, efficacy or
safety claims. Synthetic fixtures remain test bookkeeping and cannot become
E4/E5.

## Engines and Knowledge OS

Engine status is probed through the existing safe registry and reports
availability, configuration, execution and reference validation independently.
Cantera gets a small CH4/O2/N2 reference-case attempt when the environment
permits; absence is recorded as `INDETERMINATE`. Open Babel and Vina use
argv-based probes and remain `NOT_CONFIGURED` when absent. pymatgen, matminer
and pycalphad are reported from their actual import state.

The app bootstraps a small public SQLite FTS5 documentation citation and keeps
user imports in `REVIEW_REQUIRED` until a human verifies them. Review status
does not alter EvidenceLevel.

## Acceptance coverage

The service and web tests cover supported molecular execution, unavailable
combustion with downstream skips, overclaim rejection, E4 insufficiency, OOD
exclusion, prompt-injection allowlisting, persistence/reload, continuation
lineage, Knowledge citation boundaries, engine status, import/review and
fail-closed explanations. Existing core, bundle, Ledger, dataset, ML,
Knowledge, legacy and engine suites remain active.

## Validation record

The Oracle checkpoint CI run `33795616635` passed on Python 3.11 and 3.12.
The operational web commit CI run `33798333792` also passed on both versions.
The final local suite contains 128 passing tests on Python 3.11 and 128 on
Python 3.12. The only CI annotation is GitHub's Node 20 action deprecation
warning; it does not affect test results.
