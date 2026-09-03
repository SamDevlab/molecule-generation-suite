# Security Audit — Research OS 3.1

## Operational boundary

The web server serves a fixed allowlist (`index.html`, `app.js`,
`styles.css`) and rejects traversal. JSON requests are size-limited and are
validated before entering `OracleService`. The Oracle accepts only structured
plans; no chat text is passed to a shell, evaluator or arbitrary tool.

Engine adapters use argv lists, `shell=False`, timeouts and path/hash checks.
Source URLs are rendered only for `http`/`https` schemes. User material enters
the Knowledge review queue and is not auto-verified.

## Scan result

The new `src/research_os` and `web/` paths contain no `shell=True`, `eval`,
`exec`, unsandboxed subprocess or unvalidated tool dispatch. The 3.2 live
bridge is the explicit exception: it uses the fixed read-only Codex command
described below. SQL in the experience store uses fixed statements and bound
parameters; the existing Ledger allowlists dynamic sort columns.

The preserved legacy `Biolab/` tree still contains historical `shell=True`
subprocess calls. It remains outside the Research OS web/service import graph
and was not modified because its retirement gate is not satisfied. This is an
explicit legacy finding, not a claim that those scripts are safe for web use.

Research OS 3.2's live Oracle bridge uses a fixed argv, `shell=False`, read-only
Codex sandbox, strict JSON envelope and timeout. Its output is treated as
untrusted planning/narration data and is checked by the same allowlist,
evidence-ceiling and grounding gates before any Lab execution.

## Scientific invariants

LLM output cannot create Evidence; narrators cannot raise EvidenceLevel;
docking remains computational E2; simulations do not become experiments;
synthetic fixtures remain test-only; OOD candidates do not enter normal
rankings; missing evidence is not PASS; and verified Knowledge requires a
source locator.
