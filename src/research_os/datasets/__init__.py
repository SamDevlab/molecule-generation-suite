"""Dataset manifests, provenance classification and storage boundaries."""

from research_os.datasets.gates import dataset_ground_truth_gate, is_experimental_ground_truth
from research_os.datasets.registry import DatasetInspection, DatasetRegistry, DatasetRegistryError, DatasetSchemaError, DuckDBDatasetQuery, ParquetDatasetStore, StorageUnavailableError, convert_csv_to_parquet, inspect_dataset, list_versions, load_manifest, register_dataset, verify_dataset
from research_os.datasets.schema import DatasetManifest, DatasetSourceType, DatasetType
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
]
