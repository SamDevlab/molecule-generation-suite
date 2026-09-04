# Oracle architecture

```text
user text
  -> ResearchQuestion
  -> KnowledgeRetriever + ResearchMemory
  -> LLMProvider structured proposal
  -> ResearchPlan
  -> PlanValidator
  -> ResearchOrchestrator
  -> Labs/engines
  -> Evidence/Claims/Bundle/Ledger
  -> OracleAnswer
```

The LLM proposal is data, not executable code. Tool capabilities, evidence
ceilings, required engines, inputs, units and claims are checked before an
orchestrator receives a plan.

## 3.2 live Codex boundary

`CodexTestProvider` remains the deterministic CI provider. `CodexLiveProvider`
uses the local Codex session through a fixed read-only `codex exec` transport
for live interpretation, plan proposal and narration. Neither provider is a
scientific evidence provider. The live provider records runtime identity,
request/response digests and validation context in the Oracle audit trace.

Live narration is accepted only after its evidence/run references, status,
evidence-level wording and numeric content are checked against the recorded
execution payload. A bounded Codex-driven loop stops when the next required
level is experimental rather than repeating computational work.
# Operational Oracle experience (3.1)

The chat UI is a transport client of `OracleService`. Its flow is
`ResearchQuestion → ResearchPlan → PlanValidator → ResearchJob →
ResearchOrchestrator → OracleAnswer`; `CodexTestProvider` contributes only
structured planning. Session/job persistence is deliberately separate from
scientific Evidence and Ledger records.
