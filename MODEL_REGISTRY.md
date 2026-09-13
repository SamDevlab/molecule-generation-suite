# Model registry

`ModelRegistry` keeps model artifacts, stages, training references and
promotion gates separate from deterministic calculators and physics engines.
It now has a durable, content-addressed provenance mode documented in
[`docs/model-registry-durable-provenance-v1.md`](docs/model-registry-durable-provenance-v1.md).

An ML model can produce E1 evidence only under its declared validation/OOD
contract; R² is never a confidence percentage. Registration proves identity,
integrity and lineage only. It does not prove generalization, biological
validity, clinical value or affinity.

