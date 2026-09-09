from __future__ import annotations

from dataclasses import dataclass
import csv
import math
from pathlib import Path
import random
from typing import Any, Callable, Mapping, Protocol, Sequence

from research_os.core.hashing import sha256_file, sha256_json
from research_os.experiments.schema import DatasetSpec, ModelSpec, SplitSpec


class ExperimentExecutionError(RuntimeError):
    """Raised when a declared experiment cannot execute safely."""


@dataclass(frozen=True)
class DatasetTable:
    features: tuple[tuple[float, ...], ...]
    target: tuple[float, ...]
    row_ids: tuple[str, ...]
    source_path: str
    dataset_hash: str
    schema_hash: str

    @property
    def row_count(self) -> int:
        return len(self.target)


@dataclass(frozen=True)
class SplitResult:
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    membership_hash: str


@dataclass(frozen=True)
class ModelResult:
    predictions: tuple[float, ...]
    model_identity: str
    fitted_parameters: Mapping[str, Any]


class DatasetAdapter(Protocol):
    def load(self, spec: DatasetSpec, protocol_path: Path) -> DatasetTable: ...


class SplitStrategy(Protocol):
    def split(self, row_count: int, spec: SplitSpec, seed: int) -> SplitResult: ...


class ModelAdapter(Protocol):
    def fit_predict(
        self,
        train_x: Sequence[Sequence[float]],
        train_y: Sequence[float],
        test_x: Sequence[Sequence[float]],
        spec: ModelSpec,
    ) -> ModelResult: ...


Metric = Callable[[Sequence[float], Sequence[float]], float]


def _finite_float(value: str, *, field_name: str, row_number: int) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ExperimentExecutionError(f"row {row_number}: {field_name} is not numeric") from exc
    if not math.isfinite(result):
        raise ExperimentExecutionError(f"row {row_number}: {field_name} is not finite")
    return result


class NumericCSVAdapter:
    adapter_id = "csv"

    def load(self, spec: DatasetSpec, protocol_path: Path) -> DatasetTable:
        declared = Path(spec.path)
        if declared.is_absolute():
            source = declared
        else:
            relative_to_protocol = (protocol_path.parent / declared).resolve()
            relative_to_cwd = declared.resolve()
            source = relative_to_protocol if relative_to_protocol.is_file() else relative_to_cwd
        if not source.is_file():
            raise ExperimentExecutionError(f"dataset file does not exist: {spec.path}")

        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                headers = next(reader)
            except StopIteration as exc:
                raise ExperimentExecutionError("dataset is empty") from exc
            if not headers or any(not header.strip() for header in headers):
                raise ExperimentExecutionError("dataset headers must be non-empty")
            if len(set(headers)) != len(headers):
                raise ExperimentExecutionError("dataset contains duplicate headers")
            required = (*spec.features, spec.target)
            missing = sorted(set(required) - set(headers))
            if missing:
                raise ExperimentExecutionError(f"dataset is missing required columns: {', '.join(missing)}")
            positions = {header: index for index, header in enumerate(headers)}
            features: list[tuple[float, ...]] = []
            targets: list[float] = []
            row_ids: list[str] = []
            for row_number, row in enumerate(reader, start=2):
                if not row or all(not item.strip() for item in row):
                    continue
                if len(row) != len(headers):
                    raise ExperimentExecutionError(f"row {row_number}: expected {len(headers)} columns, got {len(row)}")
                x = tuple(_finite_float(row[positions[name]], field_name=name, row_number=row_number) for name in spec.features)
                y = _finite_float(row[positions[spec.target]], field_name=spec.target, row_number=row_number)
                features.append(x)
                targets.append(y)
                row_ids.append(str(row_number - 1))

        if len(targets) < 3:
            raise ExperimentExecutionError("dataset must contain at least three numeric rows")
        schema_hash = sha256_json({
            "adapter": self.adapter_id,
            "features": [{"name": name, "type": "finite_float"} for name in spec.features],
            "target": {"name": spec.target, "type": "finite_float"},
        })
        return DatasetTable(
            features=tuple(features),
            target=tuple(targets),
            row_ids=tuple(row_ids),
            source_path=str(source),
            dataset_hash=sha256_file(source),
            schema_hash=schema_hash,
        )


class SeededRandomHoldout:
    strategy_id = "random"

    def split(self, row_count: int, spec: SplitSpec, seed: int) -> SplitResult:
        train_count = int(row_count * spec.train_fraction)
        if train_count < 2 or train_count >= row_count:
            raise ExperimentExecutionError("split must leave at least two training rows and one test row")
        indices = list(range(row_count))
        random.Random(seed).shuffle(indices)
        train = tuple(sorted(indices[:train_count]))
        test = tuple(sorted(indices[train_count:]))
        membership_hash = sha256_json({"train": list(train), "test": list(test), "seed": seed})
        return SplitResult(train, test, membership_hash)


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [list(matrix[row]) + [vector[row]] for row in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= 1e-12:
            raise ExperimentExecutionError("ordinary least squares design matrix is singular")
        if pivot != column:
            augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0.0:
                continue
            augmented[row] = [current - factor * pivot_value for current, pivot_value in zip(augmented[row], augmented[column])]
    result = [augmented[row][-1] for row in range(size)]
    if not all(math.isfinite(value) for value in result):
        raise ExperimentExecutionError("ordinary least squares produced non-finite coefficients")
    return result


class OrdinaryLeastSquaresAdapter:
    adapter_id = "linear_regression"

    def fit_predict(
        self,
        train_x: Sequence[Sequence[float]],
        train_y: Sequence[float],
        test_x: Sequence[Sequence[float]],
        spec: ModelSpec,
    ) -> ModelResult:
        if spec.config:
            raise ExperimentExecutionError("linear_regression v1 does not accept model config")
        if not train_x or len(train_x) != len(train_y):
            raise ExperimentExecutionError("training data is empty or misaligned")
        width = len(train_x[0])
        if width < 1 or any(len(row) != width for row in (*train_x, *test_x)):
            raise ExperimentExecutionError("feature matrix has inconsistent width")
        design = [[1.0, *map(float, row)] for row in train_x]
        parameter_count = width + 1
        gram = [[sum(row[i] * row[j] for row in design) for j in range(parameter_count)] for i in range(parameter_count)]
        rhs = [sum(row[i] * float(target) for row, target in zip(design, train_y)) for i in range(parameter_count)]
        coefficients = _solve_linear_system(gram, rhs)
        predictions = tuple(coefficients[0] + sum(weight * float(value) for weight, value in zip(coefficients[1:], row)) for row in test_x)
        if not all(math.isfinite(value) for value in predictions):
            raise ExperimentExecutionError("model produced non-finite predictions")
        parameters = {"intercept": coefficients[0], "coefficients": coefficients[1:]}
        return ModelResult(predictions, sha256_json({"adapter": self.adapter_id, "parameters": parameters}), parameters)


def mae(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    _metric_inputs(y_true, y_pred)
    return sum(abs(actual - predicted) for actual, predicted in zip(y_true, y_pred)) / len(y_true)


def rmse(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    _metric_inputs(y_true, y_pred)
    return math.sqrt(sum((actual - predicted) ** 2 for actual, predicted in zip(y_true, y_pred)) / len(y_true))


def r2(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    _metric_inputs(y_true, y_pred)
    mean = sum(y_true) / len(y_true)
    denominator = sum((actual - mean) ** 2 for actual in y_true)
    if denominator <= 0.0:
        raise ExperimentExecutionError("r2 is undefined for a constant target")
    numerator = sum((actual - predicted) ** 2 for actual, predicted in zip(y_true, y_pred))
    return 1.0 - numerator / denominator


def _metric_inputs(y_true: Sequence[float], y_pred: Sequence[float]) -> None:
    if not y_true or len(y_true) != len(y_pred):
        raise ExperimentExecutionError("metric inputs are empty or misaligned")
    if not all(math.isfinite(value) for value in (*y_true, *y_pred)):
        raise ExperimentExecutionError("metric inputs must be finite")


class ExperimentRegistry:
    def __init__(self) -> None:
        self.datasets: dict[str, DatasetAdapter] = {"csv": NumericCSVAdapter()}
        self.splits: dict[str, SplitStrategy] = {"random": SeededRandomHoldout()}
        self.models: dict[str, ModelAdapter] = {"linear_regression": OrdinaryLeastSquaresAdapter()}
        self.metrics: dict[str, Metric] = {"mae": mae, "rmse": rmse, "r2": r2}

    def dataset(self, adapter_id: str) -> DatasetAdapter:
        return self._get(self.datasets, adapter_id, "dataset adapter")

    def split(self, strategy_id: str) -> SplitStrategy:
        return self._get(self.splits, strategy_id, "split strategy")

    def model(self, adapter_id: str) -> ModelAdapter:
        return self._get(self.models, adapter_id, "model adapter")

    def metric(self, metric_id: str) -> Metric:
        return self._get(self.metrics, metric_id, "metric")

    @staticmethod
    def _get(registry: Mapping[str, Any], identifier: str, kind: str) -> Any:
        try:
            return registry[identifier]
        except KeyError as exc:
            raise ExperimentExecutionError(f"unsupported {kind}: {identifier}") from exc
