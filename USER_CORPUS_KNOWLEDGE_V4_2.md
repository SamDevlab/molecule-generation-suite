# User Corpus Knowledge v4.2

## Readiness result

`INFRASTRUCTURE_READY_AWAITING_USER_CORPUS`

Discovery was limited to explicitly supplied corpus paths and existing project
sources. No PDFs, notes, spreadsheets or private datasets were found as a
user corpus, so there are zero ingested files, zero verified corpus claims and
zero corpus-grounded programs.

## Safety contract

- `PrivateSourceRecord` stores filename, content hash, provenance and review
  metadata, not the document body.
- Extraction is `AUTO_EXTRACTED` and remains `REVIEW_REQUIRED`.
- A `VERIFIED` claim must carry a source, locator, readable context, review
  action and a clean extraction.
- Equations remain candidates until review; symbols, units, assumptions and
  source location are not silently filled.
- Private/public conflicts are recorded as `SourceConflict`; neither source is
  preferred automatically.
- Explicit corpus paths are confined to their root, and symlink traversal is
  rejected.

When a real reviewed corpus is supplied, at least three corpus-grounded
ResearchPrograms must be run before the full v4.2 gate can pass.
