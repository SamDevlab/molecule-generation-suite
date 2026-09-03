# Research OS architecture

The repository has four separable layers:

1. domain Labs and real-engine adapters;
2. proof/evidence, bundles and immutable Ledger;
3. source-first knowledge and the Oracle planner;
4. service/executor interfaces for chat and production operation.

The preserved `Biolab/` and `formolecular/` trees are audit inputs only. New
flows cross typed contracts for conditions, units, evidence level, engine
manifest, dataset/model/source provenance, lineage and first loss.
# Research OS 3.1 operational boundary

The supported web entry point is `research_os.web`, which calls the typed
`research_os.service` facade. `ResearchStore` persists conversational
sessions/jobs while the existing Ledger remains the immutable source of truth
for scientific runs, bundles and lineage. The client never selects a Lab or
executes free-form model output.
