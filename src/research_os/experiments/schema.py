from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Mapping

import yaml


PROTOCOL_ID = "research-os.declarative-experiment.v1"
_EXPERIMENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ProtocolError(ValueError):
    """Raised when a declarative experiment protocol is invalid."""


class _StrictSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that fails closed on duplicate mapping keys."""


def _construct_unique_mapping(loader: _StrictSafeLoader, node: yaml.nodes.MappingNode, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ProtocolError("protocol mapping keys must be hashable") from exc
        if duplicate:
            raise ProtocolError(f"duplicate protocol key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _json_object_pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for key, value in pairs:
        if key in mapping:
            raise ProtocolError(f"duplicate protocol key: {key}")
        mapping[key] = value
    return mapping


def _mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProtocolError(f"{field_name} must be a mapping")
    return value


def _strict_keys(value: Mapping[str, Any], *, allowed: set[str], required: set[str], field_name: str) -> None:
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        raise ProtocolError(f"{field_name} has unknown keys: {', '.join(unknown)}")
    if missing:
        raise ProtocolError(f"{field_name} is missing required keys: {', '.join(missing)}")


def _nonempty_string(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(f"{field_name} must be a non-empty string")
    return value.strip()


def _boolean(value: Any, *, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ProtocolError(f"{field_name} must be boolean")
    return value


@dataclass(frozen=True)
class ExperimentSpec:
    id: str
    task: str
    seed: int

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ExperimentSpec":
        _strict_keys(raw, allowed={"id", "task", "seed"}, required={"id", "task", "seed"}, field_name="experiment")
        experiment_id = _nonempty_string(raw["id"], field_name="experiment.id")
        if not _EXPERIMENT_ID.fullmatch(experiment_id):
            raise ProtocolError(
                "experiment.id must be a single safe identifier using only letters, numbers, '.', '_' or '-'"
            )
        task = _nonempty_string(raw["task"], field_name="experiment.task")
        if task != "regression":
            raise ProtocolError("experiment.task must be 'regression' in protocol v1")
        seed = raw["seed"]
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise ProtocolError("experiment.seed must be a non-negative integer")
        return cls(id=experiment_id, task=task, seed=seed)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "task": self.task, "seed": self.seed}


@dataclass(frozen=True)
class DatasetSpec:
    adapter: str
    path: str
    target: str
    features: tuple[str, ...]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "DatasetSpec":
        _strict_keys(raw, allowed={"adapter", "path", "target", "features"}, required={"adapter", "path", "target", "features"}, field_name="dataset")
        adapter = _nonempty_string(raw["adapter"], field_name="dataset.adapter")
        path = _nonempty_string(raw["path"], field_name="dataset.path")
        target = _nonempty_string(raw["target"], field_name="dataset.target")
        features_raw = raw["features"]
        if not isinstance(features_raw, list) or not features_raw:
            raise ProtocolError("dataset.features must be a non-empty list")
        features = tuple(_nonempty_string(item, field_name="dataset.features[]") for item in features_raw)
        if len(set(features)) != len(features):
            raise ProtocolError("dataset.features must not contain duplicates")
        if target in features:
            raise ProtocolError("dataset.target must not also be a feature")
        return cls(adapter=adapter, path=path, target=target, features=features)

    def to_dict(self) -> dict[str, Any]:
        return {"adapter": self.adapter, "path": self.path, "target": self.target, "features": list(self.features)}


@dataclass(frozen=True)
class SplitSpec:
    strategy: str
    train_fraction: float

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "SplitSpec":
        _strict_keys(raw, allowed={"strategy", "train_fraction"}, required={"strategy", "train_fraction"}, field_name="split")
        strategy = _nonempty_string(raw["strategy"], field_name="split.strategy")
        fraction = raw["train_fraction"]
        if isinstance(fraction, bool) or not isinstance(fraction, (int, float)):
            raise ProtocolError("split.train_fraction must be numeric")
        train_fraction = float(fraction)
        if not 0.0 < train_fraction < 1.0:
            raise ProtocolError("split.train_fraction must be between 0 and 1")
        return cls(strategy=strategy, train_fraction=train_fraction)

    def to_dict(self) -> dict[str, Any]:
        return {"strategy": self.strategy, "train_fraction": self.train_fraction}


@dataclass(frozen=True)
class ModelSpec:
    id: str
    adapter: str
    config: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], *, index: int) -> "ModelSpec":
        name = f"models[{index}]"
        _strict_keys(raw, allowed={"id", "adapter", "config"}, required={"id", "adapter"}, field_name=name)
        model_id = _nonempty_string(raw["id"], field_name=f"{name}.id")
        adapter = _nonempty_string(raw["adapter"], field_name=f"{name}.adapter")
        config = raw.get("config", {})
        if not isinstance(config, Mapping):
            raise ProtocolError(f"{name}.config must be a mapping")
        return cls(id=model_id, adapter=adapter, config=dict(config))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "adapter": self.adapter, "config": dict(self.config)}


@dataclass(frozen=True)
class EvidenceSpec:
    require_dataset_hash: bool
    require_protocol_hash: bool
    fail_closed: bool

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "EvidenceSpec":
        keys = {"require_dataset_hash", "require_protocol_hash", "fail_closed"}
        _strict_keys(raw, allowed=keys, required=keys, field_name="evidence")
        values = {key: _boolean(raw[key], field_name=f"evidence.{key}") for key in keys}
        if not values["fail_closed"]:
            raise ProtocolError("evidence.fail_closed must be true in protocol v1")
        if not values["require_dataset_hash"] or not values["require_protocol_hash"]:
            raise ProtocolError("protocol v1 requires dataset and protocol hashes")
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "require_dataset_hash": self.require_dataset_hash,
            "require_protocol_hash": self.require_protocol_hash,
            "fail_closed": self.fail_closed,
        }


@dataclass(frozen=True)
class ExperimentProtocol:
    protocol: str
    experiment: ExperimentSpec
    dataset: DatasetSpec
    split: SplitSpec
    models: tuple[ModelSpec, ...]
    metrics: tuple[str, ...]
    evidence: EvidenceSpec
    source_path: Path

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], *, source_path: str | Path) -> "ExperimentProtocol":
        allowed = {"protocol", "experiment", "dataset", "split", "models", "metrics", "evidence"}
        _strict_keys(raw, allowed=allowed, required=allowed, field_name="protocol document")
        protocol = _nonempty_string(raw["protocol"], field_name="protocol")
        if protocol != PROTOCOL_ID:
            raise ProtocolError(f"unsupported protocol: {protocol}")
        experiment = ExperimentSpec.from_mapping(_mapping(raw["experiment"], field_name="experiment"))
        dataset = DatasetSpec.from_mapping(_mapping(raw["dataset"], field_name="dataset"))
        split = SplitSpec.from_mapping(_mapping(raw["split"], field_name="split"))
        models_raw = raw["models"]
        if not isinstance(models_raw, list) or not models_raw:
            raise ProtocolError("models must be a non-empty list")
        models = tuple(ModelSpec.from_mapping(_mapping(item, field_name=f"models[{index}]"), index=index) for index, item in enumerate(models_raw))
        model_ids = [model.id for model in models]
        if len(set(model_ids)) != len(model_ids):
            raise ProtocolError("model ids must be unique")
        metrics_raw = raw["metrics"]
        if not isinstance(metrics_raw, list) or not metrics_raw:
            raise ProtocolError("metrics must be a non-empty list")
        metrics = tuple(_nonempty_string(item, field_name="metrics[]") for item in metrics_raw)
        if len(set(metrics)) != len(metrics):
            raise ProtocolError("metrics must not contain duplicates")
        evidence = EvidenceSpec.from_mapping(_mapping(raw["evidence"], field_name="evidence"))
        return cls(protocol, experiment, dataset, split, models, metrics, evidence, Path(source_path))

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "experiment": self.experiment.to_dict(),
            "dataset": self.dataset.to_dict(),
            "split": self.split.to_dict(),
            "models": [model.to_dict() for model in self.models],
            "metrics": list(self.metrics),
            "evidence": self.evidence.to_dict(),
        }


def _load_yaml_strict(text: str) -> Any:
    loader = _StrictSafeLoader(text)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def load_protocol(path: str | Path) -> ExperimentProtocol:
    source = Path(path)
    if not source.is_file():
        raise ProtocolError(f"protocol file does not exist: {source}")
    text = source.read_text(encoding="utf-8")
    try:
        if source.suffix.lower() == ".json":
            raw = json.loads(text, object_pairs_hook=_json_object_pairs_no_duplicates)
        elif source.suffix.lower() in {".yaml", ".yml"}:
            raw = _load_yaml_strict(text)
        else:
            raise ProtocolError("protocol file must use .yaml, .yml or .json")
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ProtocolError(f"invalid protocol syntax: {exc}") from exc
    return ExperimentProtocol.from_mapping(_mapping(raw, field_name="protocol document"), source_path=source)
