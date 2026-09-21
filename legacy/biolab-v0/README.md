# Biolab Legacy Archaeology v0.1

This directory contains a deterministic, read-only reconstruction of the six
priority historical Biolab/formolecular CSV sources.  The source corpus stays
outside Git; only normalized indexes, summaries, manifests, tests, and
provenance are committed.

## Evidence boundary

Every imported record is classified as `evidence_origin=LEGACY`,
`evidence_level=COMPUTATIONAL`, `experimental_validation=NONE`, and
`promotion_to_current_evidence=FORBIDDEN`.  Historical labels and scores are
preserved as provenance, not current scientific conclusions.  This corpus
cannot create E4 evidence and cannot open the next-generation gate.

## Scope

- source root used for this generation: `G:\Meu Drive\Samuel – Pessoal\03 Projetos e programação\02 - Ciência, IA e dados\molecule-generation-suite`
- priority sources found: `6`
- rows scanned: `3827`
- identity-valid rows: `3817`
- exact identities after deduplication: `3795`
- duplicate exact-identity rows: `22`
- multi-source exact identities: `10`

The comparison output is a historical comparison with the frozen BIOEXP-001
panel (`A0B0`, `A1B0`, `A0B1`, `A1B1`).  It is not a ranking and contains no
new molecule generation, docking, lead selection, model training, or E4
promotion.

## Legacy pipeline vs Research OS

Legacy: generation/filtering → scoring/docking → ranking.

Current Research OS: hypothesis → bounded computation → provenance/evidence
gate → experiment.

## Reproduction

```text
python tools/legacy_biolab_import.py --legacy-root <external-corpus> --scope priority
```

Use `--dry-run` to inspect source schemas and identity statistics without
writing artifacts.
