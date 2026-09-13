# Durable Model Registry and Provenance v1

## Purpose

The model registry is a durable provenance boundary for trained model
artifacts. It is not a model-quality claim and it does not promote evidence
levels. The registry can prove what was recorded, which bytes were stored,
and whether the declared lineage is still internally consistent.

The pre-v1 registry was intentionally small and memory-only. This version
adds filesystem persistence while retaining that API for legacy callers.

## Identity hierarchy

These identities are deliberately distinct:

```text
scientific_model_id
    != artifact_sha256 / artifact_id
    != implementation_identity
    != training execution identity
    != registry record_id
```

`scientific_model_id` is derived from canonical training/scientific fields:
model family and adapter, dataset identity, feature schema, target,
preprocessing, split, seed, hyperparameters, and recorded metrics. It does
not include timestamps, absolute paths, registry roots, hostnames, or JSON
formatting. `artifact_sha256` is the SHA-256 of the persisted bytes and may
change without changing the scientific protocol identity. `implementation`
and `execution` provenance remain separate so a reproduction can have the
same scientific identity but a different execution identity.

## Durable storage

```text
<registry-root>/
  records/<record-id>.json
  artifacts/sha256/<prefix>/<sha256>
```

Registration copies bytes into the content-addressed store and writes the
record using a temporary file followed by an atomic replace. Existing records
are never silently overwritten:

- same record identity and same artifact: idempotent success;
- same record identity with different bytes or provenance: conflict;
- different scientific identity: a distinct record is required.

Listing and inspection operate on JSON metadata. Verification hashes bytes;
it does not deserialize pickle, joblib, torch, or other executable model
formats.

## Record and lineage

`research-os.model-record.v1` stores the model manifest, record identity,
artifact reference, stage, source training run, dataset reference, split,
preprocessing, target, hyperparameters, implementation identity, environment
identity, and operational registration metadata. Paths and timestamps are
operational metadata and are excluded from scientific identity hashes.

The intended lineage is:

```text
registered model
  <- training run / execution
  <- scientific protocol and implementation
  <- dataset id + version + SHA-256
  <- feature schema, preprocessing, split, target
```

Legacy manifests without a durable model file remain readable through the
memory-only API. A durable registration requires an artifact file and fails
closed when its declared hash, size, dataset reference, record identity, or
implementation provenance does not match.

## API and CLI

The Python API provides `register`, `get`, `list`, `inspect`, `verify`, and
stage operations. The CLI is intentionally metadata-oriented:

```text
research-os registry model register MANIFEST.json --root models
research-os registry model verify MODEL_OR_RECORD_ID --root models
research-os registry model inspect MODEL_OR_RECORD_ID --root models
research-os registry model list --root models
```

Verification returns structured gates and a `first_loss` such as
`MODEL_ARTIFACT_MISSING`, `MODEL_ARTIFACT_HASH_MISMATCH`,
`MODEL_RECORD_HASH_MISMATCH`, `DATASET_IDENTITY_MISMATCH`,
`SOURCE_RUN_MISSING`, or `IMPLEMENTATION_IDENTITY_MISMATCH`.

## Declarative Experiment Engine

Model registration is an explicit protocol opt-in, not a hidden side effect:

```yaml
model_registry:
  enabled: true
  root: model-registry
```

When enabled, the engine writes deterministic, adapter-owned model artifact
bytes to the durable registry and records only model record IDs, scientific
model IDs, and artifact hashes in the experiment run. `experiment-verify`
revalidates those references and bytes; `experiment-inspect` exposes them;
`experiment-reproduce` uses a separate registry root so it cannot overwrite
the source record. `experiment-compare` reports scientific-model and artifact
identity comparisons without treating registration as a quality ranking.

Old protocols without `model_registry` retain their original artifacts and
verification behavior. Historical runs are not rewritten.

## Evidence boundary and security

Registration proves artifact identity, provenance, integrity, and lineage. It
does not prove generalization, biological validity, causal correctness,
clinical value, affinity, or any other stronger scientific claim. A registered
model remains subject to the validation run that produced its metrics.

The registry protects record filenames from traversal, uses a constrained
content-addressed SHA-256 path, performs atomic writes, and refuses corrupted
records, unsupported schemas, missing artifacts, and hash mismatches. `verify`
does not execute model code.

This capability is deliberately narrow: it closes provenance gaps without
turning model persistence into a validation claim.
