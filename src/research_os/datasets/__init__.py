"""Dataset manifests, provenance classification and storage boundaries."""

from research_os.datasets.gates import dataset_ground_truth_gate, is_experimental_ground_truth
from research_os.datasets.registry import DatasetInspection, DatasetRegistry, DatasetRegistryError, DatasetSchemaError, DuckDBDatasetQuery, ParquetDatasetStore, StorageUnavailableError, convert_csv_to_parquet, inspect_dataset, list_versions, load_manifest, register_dataset, verify_dataset
from research_os.datasets.schema import DatasetManifest, DatasetSourceType, DatasetType
from research_os.datasets.real import AQSOLDB_G_SAMPLE_SPEC, AQSOLDB_G_SPEC, AQSOLDB_G_SHA256, AQSOLDB_G_URL, RealDatasetIngestResult, RealDatasetSpec, RealDatasetValidation, SourceRecord, download_aqsoldb_g, ingest_aqsoldb_g, source_record_digest, validate_real_aqsoldb_g
from research_os.datasets.query import DatasetQueryLayer, query_dataset

__all__ = [
    "DatasetManifest",
    "DatasetInspection",
    "DatasetRegistry",
    "DatasetRegistryError",
    "DatasetSchemaError",
    "DatasetSourceType",
    "DatasetType",
    "DatasetQueryLayer",
    "DuckDBDatasetQuery",
    "ParquetDatasetStore",
    "convert_csv_to_parquet",
    "inspect_dataset",
    "list_versions",
    "load_manifest",
    "register_dataset",
    "verify_dataset",
    "query_dataset",
    "StorageUnavailableError",
    "dataset_ground_truth_gate",
    "is_experimental_ground_truth",
    "AQSOLDB_G_SAMPLE_SPEC",
    "AQSOLDB_G_SPEC",
    "AQSOLDB_G_SHA256",
    "AQSOLDB_G_URL",
    "RealDatasetIngestResult",
    "RealDatasetSpec",
    "RealDatasetValidation",
    "SourceRecord",
    "download_aqsoldb_g",
    "ingest_aqsoldb_g",
    "source_record_digest",
    "validate_real_aqsoldb_g",
]
