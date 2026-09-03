# Research memory

`ResearchMemory` stores questions, plans and continuation records without
depending on an LLM's conversational memory. Ledger-backed snapshots expose
prior workflows/runs. Continuing a study creates a new plan with `rerun_of`;
the previous sealed run or plan is never edited.
# 3.1 session integration

`ResearchMemory` remains the immutable context/follow-up layer. The web
experience persists its conversation in `ResearchStore`; a continuation creates
a new question, workflow and runs with lineage and never edits the prior run.
