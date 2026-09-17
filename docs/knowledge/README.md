# Research OS knowledge workflow

Research OS already contains a knowledge subsystem: source registry, conservative ingestion, Zettelkasten notes, claims, lineage, graph/retrieval helpers, and private-corpus support.

This layer adds the missing bridge between that knowledge system and the reproducible benchmark suite.

The operating rule is:

> **Sem fonte, sem fato.**

For benchmark design and interpretation, reviewed knowledge must remain traceable to a registered source and a specific locator.

## End-to-end flow

```text
PDF / book / paper / dataset
        |
        v
SourceRecord
        |
        v
table of contents / pages / sections
        |
        v
draft notes (AUTO_GENERATED / REVIEW_REQUIRED)
        |
     review
        |
        v
VERIFIED Zettel + exact page/chapter/section locator
        |
        v
BenchmarkKnowledgeLink (evidence bridge)
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

Papers, books, datasets, benchmarks, standards, databases, reports, manuals,
web sources, experiments, and simulations already have a common provenance
record. External sources retain DOI, ISBN, or URL as applicable. Books can
retain ISBN and edition; local documents can retain a SHA-256 content hash.

### `KnowledgeIngestionPipeline`

Ingestion extracts candidate Zettels, claims, equations, and entities, but it never silently promotes generated material to verified knowledge. Auto-extracted material enters the review queue.

### `Zettel`

Atomic notes are the v1 `NoteRecord`: they retain evidence level, review state,
limitations, connections, and one or more `SourceLocator`s. Every note in a
validated benchmark bundle must resolve to a registered source and retain a
specific `page`, `chapter`, or `section` locator. A note without provenance is
not silently promoted into scientific knowledge.

### `ScientificClaim`

Claims remain tied to run evidence and evidence levels in the existing
Research OS claim subsystem. The literature bridge does not invent a second
parallel claim model: reviewed notes provide the source-backed rationale, and
benchmark evidence links provide the bridge to the result identity.

### `BenchmarkKnowledgeLink`

The v1 evidence link associates reviewed source IDs and Zettel IDs with:

- benchmark ID;
- protocol ID;
- scientific result hash;
- optional artifact ID;
- boundary such as `pre-result`.

`artifact_id` is execution/package metadata and is deliberately excluded from
the scientific knowledge identity. Repackaging the same result therefore does
not create a new scientific identity. The scientific result hash remains the
benchmark identity used for the link.

The verifier also fails closed on duplicate source, note, or evidence-link IDs,
duplicate references, unknown note locators, non-specific locators, and
malformed source document hashes. Record order, JSON whitespace, retrieval
timestamps, and note creation timestamps do not change the identity.

## Books and PDFs

The future ingestion architecture is intentionally small:

```text
PDF / book
    |
    v
SourceRecord
    |
    v
table of contents / pages / sections
    |
    v
draft notes -> review -> claims -> evidence
```

Store bibliographic metadata, edition/ISBN or URL/DOI as applicable, page or
section locators, short notes/paraphrases, claims, hashes, and relationships.
Never copy an entire book or PDF into the repository. A private corpus may
remain outside the public repository while its provenance and review outputs
remain auditable. Future embeddings are a derived, disposable index; they are
never the source of truth.

## Determinism

`benchmark_knowledge_identity(...)` hashes a canonical scientific payload. Retrieval timestamps and Zettel creation timestamps are intentionally excluded from this identity; changing when a source was fetched must not make the underlying scientific knowledge appear different.

The committed JSON bundle verifier fails closed on:

- unknown source/Zettel IDs;
- unreviewed benchmark-linked Zettels;
- missing page/chapter/section locators;
- malformed scientific hashes;
- duplicate IDs and unresolved note/source references;
- unsupported schemas;
- mismatched frozen knowledge identity once one is sealed.

Run the verifier locally without GitHub Actions:

```bash
python scripts/verify_knowledge.py knowledge/*.json
python scripts/verify_knowledge.py --json knowledge/*.json
```

The command prints one scientific identity per valid bundle and exits non-zero
if any bundle cannot be loaded or validated.

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
