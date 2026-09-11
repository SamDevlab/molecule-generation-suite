# Research OS knowledge workflow

Research OS already contains a knowledge subsystem: source registry, conservative ingestion, Zettelkasten notes, claims, lineage, graph/retrieval helpers, and private-corpus support.

This layer adds the missing bridge between that knowledge system and the reproducible benchmark suite.

The operating rule is:

> **Sem fonte, sem fato.**

For benchmark design and interpretation, reviewed knowledge must remain traceable to a registered source and a specific locator.

## End-to-end flow

```text
book / paper / dataset
        |
        v
SourceRecord
        |
        v
KnowledgeIngestionPipeline
        |
        v
AUTO_GENERATED / REVIEW_REQUIRED Zettel
        |
     review
        |
        v
VERIFIED Zettel + exact page/chapter/section locator
        |
        v
BenchmarkKnowledgeLink
        |
        +--> benchmark_id
        +--> protocol_id
        +--> scientific_result_hash
        |
        v
ScientificClaim / lineage after an executed run exists
```

## Existing components reused

### `SourceRecord` / `SourceRegistry`

Papers, books, standards, datasets, databases, reports, manuals, web sources, experiments, and simulations already have a common provenance record. Books can retain ISBN and edition; local documents can retain a SHA-256 content hash.

### `KnowledgeIngestionPipeline`

Ingestion extracts candidate Zettels, claims, equations, and entities, but it never silently promotes generated material to verified knowledge. Auto-extracted material enters the review queue.

### `Zettel`

Atomic notes retain evidence level, review state, limitations, connections, and one or more `SourceLocator`s. A benchmark-linked Zettel must now be `VERIFIED` and retain a specific `page`, `chapter`, or `section` locator.

### `ScientificClaim`

Claims remain tied to run evidence and evidence levels. The literature bridge does not invent a second claim system.

### `BenchmarkKnowledgeLink`

The new bridge associates reviewed source IDs and Zettel IDs with:

- benchmark ID;
- protocol ID;
- scientific result hash;
- optional artifact ID;
- boundary such as `pre-result`.

Artifact ZIP identity is execution metadata. The scientific result hash remains the benchmark identity used for the link.

## Books and PDFs

The workflow inspired by the S3 research process is now:

1. register a book/PDF as a `SourceRecord`;
2. retain edition/ISBN and file hash when available;
3. ingest text into review-required candidate notes;
4. atomize useful knowledge into small Zettels;
5. add exact page/chapter/section locators;
6. review before changing the Zettel to `VERIFIED`;
7. link only reviewed notes to benchmark/protocol identities;
8. use the existing lineage/graph/retrieval layer to query the resulting knowledge;
9. permit training/RAG export only from reviewed, sourced Zettels.

Raw copyrighted book text should not be committed as a knowledge artifact. Durable public-repository artifacts are bibliographic metadata, concise paraphrased notes, locators, relationships, and hashes. A private corpus can remain outside the public repository while its provenance and review outputs remain auditable.

## Determinism

`benchmark_knowledge_identity(...)` hashes a canonical scientific payload. Retrieval timestamps and Zettel creation timestamps are intentionally excluded from this identity; changing when a source was fetched must not make the underlying scientific knowledge appear different.

The committed JSON bundle verifier fails closed on:

- unknown source/Zettel IDs;
- unreviewed benchmark-linked Zettels;
- missing page/chapter/section locators;
- malformed scientific hashes;
- unsupported schemas;
- mismatched frozen knowledge identity once one is sealed.

## First seeded bridge: APODOCK-001

The first bundle records Seeliger & de Groot (2010) as the literature source for the ten-case apo/holo large-motion cohort and links the reviewed note to the already frozen APODOCK-001 structural-preflight identity:

`c5fae682ecf6b7e8884de8b4d02fd052d306ea3b5d421b6ad44814289afae805`

This is a **pre-result** literature/provenance link. It does not add an APODOCK docking outcome and does not alter the frozen cases, receptor alignment, grid, or future Vina parameters.

## Direction from here

The best path is to grow knowledge and experiments together:

```text
literature -> reviewed notes -> frozen protocol -> experiment -> evidence -> claim revision
```

For APODOCK-001 specifically, the next scientific step remains: resolve the predeclared APD-010 glycan preparation, freeze that representation and the execution runner, and only then allow the first Vina outcome.
