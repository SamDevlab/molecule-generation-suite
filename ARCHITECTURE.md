# Research OS architecture

The repository has four separable layers:

1. domain Labs and real-engine adapters;
2. proof/evidence, bundles and immutable Ledger;
3. source-first knowledge and the Oracle planner;
4. service/executor interfaces for chat and production operation.

The preserved `Biolab/` and `formolecular/` trees are audit inputs only. New
flows cross typed contracts for conditions, units, evidence level, engine
manifest, dataset/model/source provenance, lineage and first loss.

## 3.2 live operational boundary

The web server can select `test` or `live` Oracle mode. Live mode uses the
active Codex host's local CLI bridge for structured reasoning only; the
Research OS executor and registered Labs remain the source of scientific
truth. Deterministic CI continues to use `CodexTestProvider` and does not
depend on a live model.

## 3.3 campaign boundary

`research_os.campaigns` adds source-backed problem discovery, constrained
3-primary/2-secondary selection, persistent campaign history and bounded
campaign execution. The live Codex ranks registered data and explains a
selection; it cannot add a source, evidence, run, condition or claim. Campaign
reports link to sealed ResearchBundle/Ledger records and preserve OOD,
uncertainty, gaps, conflicts, negative results and first loss/divergence.
# Research OS 3.1 operational boundary

The supported web entry point is `research_os.web`, which calls the typed
`research_os.service` facade. `ResearchStore` persists conversational
sessions/jobs while the existing Ledger remains the immutable source of truth
for scientific runs, bundles and lineage. The client never selects a Lab or
executes free-form model output.
