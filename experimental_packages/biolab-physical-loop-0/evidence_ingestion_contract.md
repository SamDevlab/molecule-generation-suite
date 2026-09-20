# Evidence ingestion contract

`ingest-result` first runs the complete validation contract. It creates an
append-only `ExternalEvidenceUpdate` only when the result is eligible for E4.
The update carries the new evidence id, affected gap and claim ids, source
identity, report version, and compatibility assessment.

The next `BiolabScientificState` is recomputed from the update. E5 is never
created automatically: `ExternalEvidenceIntegrator.assess_dependency()` must
find independent eligible evidence before any future validation promotion.
