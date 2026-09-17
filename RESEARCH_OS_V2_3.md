# Research OS v2.3 — scale and production hardening

The core now exposes `LocalExecutor` and `ProcessExecutor`, with a typed
`SlurmExecutor` interface that fails explicitly when no scheduler adapter is
configured. `CacheKey` includes input hash, config hash, code commit, engine
version and protocol version; changing the protocol necessarily changes the
cache key.

The existing content-addressed filesystem artifact store is behind an
`ArtifactBackend` interface. `PersistenceBackend` is available for future
storage implementations without rewriting the domain. `create_backup` makes a
non-destructive, hash-indexed export of ledger/bundles/manifests/artifacts.

`ObservabilityMetrics` records durations, engine availability, failures,
FIRST_LOSS counts, cache hits and job states. No operational metric is treated
as scientific evidence.

Security boundaries remain explicit: no shell execution from Oracle text,
validated paths, typed tools, subprocess adapters without `shell=True`, and no
secrets in manifests or LLM audit records.

