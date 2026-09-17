# Dataset registry

`DatasetRegistry` remains the source of truth for dataset records. New durable
registries store atomic record envelopes and content-addressed managed bytes;
external references must be explicit. CSV is the portable interchange format;
Parquet and DuckDB are optional storage/query boundaries. Legacy flat manifests
remain readable and are reported as legacy provenance without invented IDs.

See [docs/dataset-registry-durable-provenance-v1.md](docs/dataset-registry-durable-provenance-v1.md)
for the identity hierarchy, fail-closed verification, lineage rules, and
Declarative Experiment Engine integration.

Registration proves identity and integrity only. It does not elevate Evidence
Level or establish scientific validity.

