# Research OS Knowledge Layer v1

The knowledge layer turns literature, books, datasets, and benchmark outputs into auditable research context.

Its core rule is simple:

> **Sem fonte, sem fato.**

A statement that is presented as scientific knowledge must be traceable to a source note or be explicitly labelled as a hypothesis.

## Pipeline

```text
Source -> Note -> Claim -> EvidenceLink -> Benchmark / scientific result hash
```

### Source

A source is a stable bibliographic or experimental object: paper, book, dataset, webpage, benchmark, or experiment.

External sources require a DOI, ISBN, or URL. Books should use ISBN when available and retain edition information in their title/metadata rather than silently merging editions.

### Note

A note is a concise paraphrase tied to an exact locator such as:

- `p. 143`
- `pp. 143-147`
- `Chapter 6, section 6.2`
- `Table 1`
- `Methods > Docking`
- `Supplementary Table S3`

Notes are not free-floating summaries. A locator is mandatory.

### Claim

A claim is a statement the project may rely on when designing or interpreting work. Supported, contested, and rejected claims require one or more notes. A hypothesis may be source-free, but must remain explicitly labelled `HYPOTHESIS` until evidence changes its status.

### EvidenceLink

An evidence link connects a claim to an executed benchmark using the benchmark ID, protocol ID, and **scientific result hash**. Artifact IDs are execution metadata and may also be recorded, but they are not substitutes for scientific identity.

## Why files first

Version 1 deliberately uses canonical JSON records and Git instead of a database:

- deterministic diffs;
- reviewable provenance;
- rollback safety;
- hashes can be tested in CI;
- no hidden mutable state;
- easy export to SQLite, graph databases, or vector indexes later.

This mirrors the Research OS/S3 approach: keep a simple reference representation first; optimize only after equivalence can be tested.

## Books and PDFs

The intended ingestion flow for books and long PDFs is:

1. register the book/PDF as a `SourceRecord`;
2. extract its table of contents and stable page/section boundaries;
3. create small, paraphrased `NoteRecord`s with exact page/section locators;
4. derive claims only from those notes;
5. connect relevant claims to protocols and benchmark outcomes;
6. compute a canonical knowledge-bundle hash;
7. only then build search/embedding indexes as disposable derived data.

The raw copyrighted book text should not be copied into the repository. The durable repository objects are bibliographic metadata, concise notes, locators, claims, and evidence identities.

## First seeded case: APODOCK-001

The first knowledge records are anchored to Seeliger & de Groot (2010), which motivates the published ten-case apo/holo large-motion cohort used by APODOCK-001. The knowledge layer records the literature rationale separately from the prospective benchmark outcome. No APODOCK Vina result existed when the structural preflight boundary was frozen.

## Next stages

- `v1.1`: JSON loader/writer + CLI verifier.
- `v1.2`: source registry and cross-file reference validation.
- `v1.3`: PDF/book ingestion helpers that create draft notes, never autonomous claims.
- `v1.4`: SQLite read model for fast queries.
- `v1.5`: optional embeddings/vector search as a derived index.
- `v2`: claim graph + automatic experiment-to-literature comparison reports.
