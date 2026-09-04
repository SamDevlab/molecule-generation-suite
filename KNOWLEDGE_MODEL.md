# Knowledge model

Sources are registered before documents are atomized. Documents produce
review-required zettels, claims, equations and entities. A knowledge graph
stores explicit, source-linked edges only. SQLite FTS5 retrieval returns
source, locator, review status, zettel ID and score. Training/RAG eligibility
requires reviewed, source-located atoms.
# 3.1 operational retrieval

The web service exposes reviewed source citations through the Oracle trace.
Imported material enters `REVIEW_REQUIRED`; human review may verify, reject or
edit it, but review status never promotes EvidenceLevel. Retrieval remains a
citation/context operation and cannot turn a computational result into
experimental evidence.

## 3.3 real source-backed campaigns

The real campaign catalog registers primary/official source metadata before
discovery. Source URLs and retrieved summaries are DATA ONLY, never
instructions. `CampaignStore` keeps campaign history separately from the
immutable Ledger; source-synthesis campaigns stop at `INSUFFICIENT_EVIDENCE`
when condition-matched records are unavailable.
