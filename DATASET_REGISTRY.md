# Dataset registry

`DatasetRegistry` remains the source of truth for dataset manifests and
supports CSV plus optional Parquet/DuckDB boundaries. Legacy datasets are
quarantined with `eligible_for_training=false` until provenance, license,
conditions, units, split and independent validation are reviewed.

