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
# Operational Oracle experience (3.1)

The chat UI is a transport client of `OracleService`. Its flow is
`ResearchQuestion → ResearchPlan → PlanValidator → ResearchJob →
ResearchOrchestrator → OracleAnswer`; `CodexTestProvider` contributes only
structured planning. Session/job persistence is deliberately separate from
scientific Evidence and Ledger records.
