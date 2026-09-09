from __future__ import annotations

from pathlib import Path

import pytest

from research_os.experiments import ProtocolError, load_protocol


def test_yaml_duplicate_keys_fail_closed(tmp_path: Path) -> None:
    protocol = tmp_path / "duplicate.yaml"
    protocol.write_text(
        """protocol: research-os.declarative-experiment.v1
protocol: research-os.declarative-experiment.v1
experiment: {id: SAFE-ID, task: regression, seed: 42}
dataset: {adapter: csv, path: data.csv, target: y, features: [x]}
split: {strategy: random, train_fraction: 0.8}
models: [{id: ols, adapter: linear_regression}]
metrics: [mae]
evidence: {require_dataset_hash: true, require_protocol_hash: true, fail_closed: true}
""",
        encoding="utf-8",
    )
    with pytest.raises(ProtocolError, match="duplicate protocol key: protocol"):
        load_protocol(protocol)


def test_json_duplicate_keys_fail_closed(tmp_path: Path) -> None:
    protocol = tmp_path / "duplicate.json"
    protocol.write_text(
        '{"protocol":"research-os.declarative-experiment.v1",'
        '"protocol":"research-os.declarative-experiment.v1",'
        '"experiment":{"id":"SAFE-ID","task":"regression","seed":42},'
        '"dataset":{"adapter":"csv","path":"data.csv","target":"y","features":["x"]},'
        '"split":{"strategy":"random","train_fraction":0.8},'
        '"models":[{"id":"ols","adapter":"linear_regression"}],'
        '"metrics":["mae"],'
        '"evidence":{"require_dataset_hash":true,"require_protocol_hash":true,"fail_closed":true}}',
        encoding="utf-8",
    )
    with pytest.raises(ProtocolError, match="duplicate protocol key: protocol"):
        load_protocol(protocol)


def test_experiment_id_cannot_escape_output_root(tmp_path: Path) -> None:
    protocol = tmp_path / "unsafe.yaml"
    protocol.write_text(
        """protocol: research-os.declarative-experiment.v1
experiment:
  id: ../../escaped
  task: regression
  seed: 42
dataset:
  adapter: csv
  path: data.csv
  target: y
  features: [x]
split:
  strategy: random
  train_fraction: 0.8
models:
  - id: ols
    adapter: linear_regression
metrics: [mae]
evidence:
  require_dataset_hash: true
  require_protocol_hash: true
  fail_closed: true
""",
        encoding="utf-8",
    )
    with pytest.raises(ProtocolError, match="single safe identifier"):
        load_protocol(protocol)
