# ORÁCULO · Research OS 3.3

The operational client is a dependency-free HTML/CSS/JS chat served by the
Python standard library. It calls `research_os.service` through the typed HTTP
boundary in `research_os.web.server`; it must not import `research_os.*.lab`
modules directly. The server defaults to the deterministic `CodexTestProvider`
for repeatable local/CI behavior. Set `--oracle-mode live` or
`RESEARCH_OS_ORACLE_MODE=live` to use the local Codex session bridge for live
planning and narration; the bridge is not a standalone web LLM and cannot
create scientific Evidence.

## Run locally

From the repository root:

```bash
py -3.11 -m pip install -e .
py -3.11 -m research_os.web --port 8000
```

Then open <http://127.0.0.1:8000>. Use `--data-root` or `RESEARCH_OS_DATA`
to select the local state directory. The default `.research-os/` contains
experience SQLite state, the existing Ledger, bundles, Knowledge OS manifests,
retrieval index and engine reference results.

For the optional local Cantera reference environment created during this
milestone, use `.\.venv\Scripts\python.exe -m research_os.web --port 8000`.

The UI is chat-first. It keeps Labs, engines, plans, evidence, sources, runs,
lineage and review state in the trace inspector so a normal user only needs to
describe the research question.

The service returns a compact summary for normal users and retains plan,
engine manifests, hashes, bundles and lineage for technical inspection. A
process restart recovers non-terminal jobs as `FAILED` with
`PROCESS_RESTARTED`; it never pretends that execution resumed.

The Research OS 3.3 sidebar adds persistent Real Campaigns. “Discover
source-backed problems” invokes live Codex discovery/ranking, while campaign
history and the inspector expose sources, datasets, models, engines, gaps,
conditions, runs and bundles. Campaign execution is bounded to registered
problem IDs; source text remains DATA ONLY.

The live audit trace is available at `/api/oracle/audit` and is surfaced in the
system-status panel. Campaign routes include `/api/campaigns`,
`/api/campaigns/discover`, `/api/campaigns/start` and
`/api/campaigns/memory`. The non-CI live acceptance command is documented in
`REAL_CAMPAIGNS_V3_3.md`; deterministic CI never depends on a live Codex call.
