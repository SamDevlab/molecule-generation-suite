# Research memory

`ResearchMemory` stores questions, plans and continuation records without
depending on an LLM's conversational memory. Ledger-backed snapshots expose
prior workflows/runs. Continuing a study creates a new plan with `rerun_of`;
the previous sealed run or plan is never edited.

## Live Oracle context

In 3.2, the active session, available Labs/capabilities, engine status, tool
contracts, sources and prior memory are passed as explicit context to the live
Codex boundary. The context is audit metadata and planning input; it does not
grant the model authority over Evidence or Ledger state. Continuation invokes
the live provider again while preserving the parent plan and run lineage.
# 3.1 session integration

`ResearchMemory` remains the immutable context/follow-up layer. The web
experience persists its conversation in `ResearchStore`; a continuation creates
a new question, workflow and runs with lineage and never edits the prior run.
