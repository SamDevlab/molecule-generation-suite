# Dataset Registry durable provenance v1

The Dataset Registry is the durable boundary for dataset identity and
provenance. Registration does not claim that a dataset is scientifically
valid, representative, or suitable as experimental ground truth; those claims
remain controlled by the dataset evidence gates.

## Identity hierarchy

The registry keeps these identities separate:

```text
scientific_dataset_id  !=  artifact_id / artifact_sha256
                       !=  record_id / record_hash
                       !=  transformation_run_id
                       !=  implementation identity
```

`scientific_dataset_id` is a canonical hash of the declared scientific
dataset contract: dataset/version, schema, dimensions, source/evidence
classification, target and measurement metadata, and parent references. It
excludes timestamps, absolute paths, registry locations, and transformation
execution metadata. `artifact_sha256` identifies the exact bytes. A changed
artifact is therefore detectable without silently changing the logical
scientific declaration.

`record_id` and `record_hash` identify the persisted registry envelope. The
envelope records the manifest, byte identity, lineage, provenance, and
registration metadata. Timestamps are operational metadata and do not enter
record identity.

## Durable storage

With a registry root configured, new registrations are stored as:

```text
<root>/
  manifests/<record-id>.manifest.json
  artifacts/sha256/<prefix>/<sha256>
```

Managed artifacts are copied byte-for-byte into the content-addressed store.
Registration validates the source hash and size, writes the record using a
same-directory temporary file plus atomic replace, then reads the record back
and verifies its identity before indexing it in memory. A process restart can
reconstruct the registry from records alone.

External references are explicit with `artifact_mode="external"`. They are
never copied. If the source path disappears, verification returns
`INSUFFICIENT_EVIDENCE` with `SOURCE_ARTIFACT_UNAVAILABLE`; a changed source
returns a failed hash gate. Restricted/non-redistributable inputs cannot be
managed accidentally.

The registry is idempotent for the same dataset version, scientific identity,
and artifact bytes. A conflicting registration for the same `dataset_id` and
`version` fails closed. It never silently overwrites a record.

## Verification

`DatasetRegistry.verify()` returns a structured result with gate records,
status, and `first_loss`. The boolean `verify_dataset()` facade remains for
legacy callers. Verification checks:

- record schema and persisted record hash;
- scientific identity reproduction;
- managed path containment or explicit external mode;
- artifact existence, SHA-256, and byte size;
- parent availability and acyclic lineage;
- durable artifact boundary.

Typical first-loss values include `DATASET_RECORD_HASH_MISMATCH`,
`DATASET_ARTIFACT_MISSING`, `DATASET_ARTIFACT_HASH_MISMATCH`,
`DATASET_PATH_ESCAPE`, `DATASET_PARENT_MISSING`, and
`SOURCE_ARTIFACT_UNAVAILABLE`. Legacy flat manifests remain readable but are
reported with insufficient durable record evidence rather than receiving an
invented record ID.

Verification is metadata/bytes-only. It does not deserialize pickle, joblib,
Torch, or other executable model/data formats. Path traversal and managed
artifact symlink escapes are rejected.

## Lineage and experiment integration

Parent datasets are recorded as `dataset_id@version` references. A missing
parent or cycle blocks registration/verification. Transformation execution
IDs remain lineage metadata and do not masquerade as scientific identity.

Declarative Experiment Engine protocols may explicitly declare:

```yaml
dataset_registry:
  enabled: true
  root: /path/to/dataset-registry
  dataset_id: training-set
  version: v1
```

The engine verifies the record before loading bytes, records the registry
reference in the run manifest and provenance, and re-verifies it in
`experiment-verify` and `experiment-reproduce`. Reproduction never overwrites
the source dataset record. Model Registry integration likewise verifies the
referenced dataset before accepting a durable model record.

Historical runs without a dataset registry reference remain readable and are
not rewritten. They retain their existing path/hash provenance and are not
retroactively assigned registry identities.

## Evidence boundary

Dataset registration proves identity, byte integrity, and attributable
lineage. It does not increase Evidence Level, establish generalization,
biological validity, clinical value, or causal correctness. Metrics and
scientific conclusions belong to the corresponding validation run.

Short operational flow:

```text
prepare dataset -> register -> verify -> inspect -> train -> reproduce -> compare
```

`Dataset registration is now a durable provenance operation rather than a
path-based manifest convenience.`
