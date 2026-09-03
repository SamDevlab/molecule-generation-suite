# Research OS v2.0 — ORÁCULO

The Oracle is an intellectual coordination boundary, not a universal
prediction model. Its flow is:

```text
user language -> ResearchQuestion -> retrieval/memory -> structured proposal
-> ResearchPlan -> PlanValidator -> Orchestrator
```

`ResearchQuestion`, `ResearchPlan`, `PlanStep`, `ClaimTarget`, `ResearchGap`
and `OracleAnswer` are typed records. Each Lab declares its experiments,
required inputs, engine requirements, side effects and maximum evidence level.
The validator rejects unknown Labs/experiments, dependency cycles, invalid
units, missing references, unsupported claims and impossible evidence levels;
missing engines are `INDETERMINATE`.

`LLMProvider` is provider-neutral. It can interpret questions and propose or
repair structured JSON, but it has no execution method. Prompt/response hashes,
provider, model and planning run ID are recorded in `LLMCallAudit`, with secret
fields redacted. Free text cannot become a tool call.

The built-in rule-based provider is a deterministic test provider only. It is
not scientific evidence. The overclaim guard rejects “docking proves a cure”
and reformulates it as an E2 computational hypothesis. Docking never exceeds
E2.

`ResearchMemory` stores immutable records and continuation creates a new plan
with `rerun_of`; previous plans are not edited. `AutonomousResearchLoop` has
bounded steps, runs, candidates, iterations and failures and stops explicitly
on indeterminate engines or satisfied evidence requirements.

