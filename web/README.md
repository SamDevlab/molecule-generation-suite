# ORÁCULO · Research OS 3.1

The operational client is a dependency-free HTML/CSS/JS chat served by the
Python standard library. It calls `research_os.service` through the typed HTTP
boundary in `research_os.web.server`; it must not import `research_os.*.lab`
modules directly.

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
