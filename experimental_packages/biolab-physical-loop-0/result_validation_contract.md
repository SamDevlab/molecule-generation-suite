# External result validation contract

`validate-result` is read-only. A result becomes eligible for
`E4_CURATED_EXPERIMENTAL` only when the actual experiment, attributable
provider/laboratory, recorded protocol, sample identity, conditions, measured
value, raw or official report artifact, and artifact hashes are all present.

The requested panel identity is compared with the reported physical sample.
An InChIKey, isomeric representation, batch identity, or identity-method
mismatch returns `EXPERIMENT_IDENTITY_MISMATCH` and fails closed.

`TEST_SYNTHETIC` fixtures are explicitly `NOT_SCIENTIFIC_EVIDENCE`. Validation
does not mutate the package or create an Evidence record.
