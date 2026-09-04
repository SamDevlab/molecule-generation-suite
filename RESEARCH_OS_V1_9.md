# Research OS v1.9 — Knowledge OS

v1.9 adds a source-first knowledge boundary. The knowledge tree is created by
`ensure_knowledge_layout`:

```text
knowledge/{inbox,sources,documents,zettels,mocs,equations,claims,entities,review,training,rejected}
```

`SourceRegistry` stores bibliographic identity, DOI/ISBN/URL/license,
retrieval time and document hash. `KnowledgeIngestionPipeline` converts a
source document into sections and candidate zettels, claims, equations and
entities, then places every extracted item in `REVIEW_REQUIRED`. No
AI-generated atom is automatically promoted to `VERIFIED`.

`EquationRegistry` requires a declared domain and conditions before an
equation is applicable. `KnowledgeGraph` stores explicit relations such as
`SOURCE supports CLAIM`, `CLAIM uses EVIDENCE`, `RUN produces EVIDENCE`,
`ZETTEL describes CONCEPT`, `DATASET derived_from SOURCE` and `MODEL trained_on
DATASET`. Unknown relations are rejected.

`KnowledgeRetriever` uses SQLite FTS5 and returns the source ID, locator,
review status, zettel ID and score for every hit. It never fabricates a source.
Embeddings remain optional and are not required for the provenance contract.

Source-to-Ledger helpers provide `runs_from_source`, `claims_from_source`,
`evidence_from_source`, `sources_for_claim` and `source_lineage` by reading
immutable bundle provenance and ledger records.

Default navigation maps are provided for fuels, combustion, propulsion,
metallurgy, degradation, pharma and hydrogen materials. They contain no
invented scientific content.

