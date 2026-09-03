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

