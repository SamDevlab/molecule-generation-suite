from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import random
from typing import Any, Callable, Sequence, TypeVar

from research_os.ml.schema import DataSplit, SplitStrategy


T = TypeVar("T")


class SplitError(ValueError):
    """Raised when a requested split cannot be materialized explicitly."""


def _strategy(value: SplitStrategy | str) -> SplitStrategy:
    try:
        return value if isinstance(value, SplitStrategy) else SplitStrategy(str(value))
    except ValueError as exc:
        raise SplitError(f"unsupported split strategy: {value}") from exc


def _fractions(validation_size: float, test_size: float) -> tuple[float, float]:
    if not 0 <= validation_size < 1 or not 0 < test_size < 1 or validation_size + test_size >= 1:
        raise SplitError("validation_size and test_size must be positive fractions with total below one")
    return validation_size, test_size


def _three_way(items: Sequence[T], *, seed: int, validation_size: float, test_size: float) -> DataSplit[T]:
    validation_size, test_size = _fractions(validation_size, test_size)
    shuffled = list(items)
    random.Random(seed).shuffle(shuffled)
    test_count = max(1, round(len(shuffled) * test_size)) if len(shuffled) >= 3 else 0
    validation_count = max(1, round(len(shuffled) * validation_size)) if len(shuffled) - test_count >= 3 else 0
    if test_count + validation_count >= len(shuffled) and len(shuffled) > 1:
        validation_count = min(validation_count, max(0, len(shuffled) - test_count - 1))
    train_end = len(shuffled) - test_count - validation_count
    return DataSplit(SplitStrategy.RANDOM, tuple(shuffled[:train_end]), tuple(shuffled[train_end:train_end + validation_count]), tuple(shuffled[train_end + validation_count:]), seed=seed)


def random_split(records: Sequence[T], *, validation_size: float = 0.1, test_size: float = 0.2, seed: int = 42) -> DataSplit[T]:
    return _three_way(records, seed=seed, validation_size=validation_size, test_size=test_size)


def _default_key(strategy: SplitStrategy) -> Callable[[Any], Any]:
    aliases = {
        SplitStrategy.SCAFFOLD: ("scaffold", "scaffold_id"),
        SplitStrategy.CLUSTER: ("cluster", "cluster_id"),
        SplitStrategy.SOURCE: ("source", "source_id", "dataset_source", "source_type"),
        SplitStrategy.GROUP: ("group", "group_id"),
        SplitStrategy.TEMPORAL: ("timestamp", "date", "created_at", "year"),
    }
    names = aliases[strategy]

    def get(record: Any) -> Any:
        if isinstance(record, dict):
            for name in names:
                if record.get(name) is not None:
                    return record[name]
        for name in names:
            if hasattr(record, name):
                return getattr(record, name)
        raise SplitError(f"{strategy.value} requires one of: {', '.join(names)}")

    return get


def _scaffold_from_smiles(record: Any) -> str:
    smiles = record.get("smiles") or record.get("SMILES") if isinstance(record, dict) else getattr(record, "smiles", None)
    if not smiles:
        raise SplitError("scaffold_split requires scaffold/scaffold_id or a SMILES field")
    try:
        from rdkit import Chem
        from rdkit.Chem.Scaffolds import MurckoScaffold
    except ImportError as exc:
        raise SplitError("scaffold_split requires RDKit when scaffold IDs are not supplied") from exc
    molecule = Chem.MolFromSmiles(str(smiles))
    if molecule is None:
        raise SplitError(f"cannot derive scaffold from invalid SMILES: {smiles!r}")
    return MurckoScaffold.MurckoScaffoldSmiles(mol=molecule) or "ACYCLIC"


def _grouped_split(records: Sequence[T], strategy: SplitStrategy, *, key: Callable[[Any], Any] | None, seed: int, validation_size: float, test_size: float) -> DataSplit[T]:
    key_fn = key or (_scaffold_from_smiles if strategy == SplitStrategy.SCAFFOLD else _default_key(strategy))
    groups: dict[str, list[T]] = defaultdict(list)
    for record in records:
        value = key_fn(record)
        if value is None or str(value).strip() == "":
            raise SplitError(f"{strategy.value} does not allow an empty grouping key")
        groups[str(value)].append(record)
    group_names = list(groups)
    random.Random(seed).shuffle(group_names)
    target_test = len(records) * test_size
    target_validation = len(records) * validation_size
    test: list[T] = []
    validation: list[T] = []
    train: list[T] = []
    for name in group_names:
        bucket = groups[name]
        if len(test) < target_test:
            test.extend(bucket)
        elif len(validation) < target_validation:
            validation.extend(bucket)
        else:
            train.extend(bucket)
    # Small datasets can leave a split empty; retaining group isolation is
    # more important than fabricating a row or breaking a group apart.
    return DataSplit(strategy, tuple(train), tuple(validation), tuple(test), seed=seed, metadata={"group_count": len(groups)})


def scaffold_split(records: Sequence[T], *, key: Callable[[Any], Any] | None = None, validation_size: float = 0.1, test_size: float = 0.2, seed: int = 42) -> DataSplit[T]:
    _fractions(validation_size, test_size)
    return _grouped_split(records, SplitStrategy.SCAFFOLD, key=key, seed=seed, validation_size=validation_size, test_size=test_size)


def cluster_split(records: Sequence[T], *, key: Callable[[Any], Any] | None = None, validation_size: float = 0.1, test_size: float = 0.2, seed: int = 42) -> DataSplit[T]:
    _fractions(validation_size, test_size)
    return _grouped_split(records, SplitStrategy.CLUSTER, key=key, seed=seed, validation_size=validation_size, test_size=test_size)


def source_split(records: Sequence[T], *, key: Callable[[Any], Any] | None = None, validation_size: float = 0.1, test_size: float = 0.2, seed: int = 42) -> DataSplit[T]:
    _fractions(validation_size, test_size)
    return _grouped_split(records, SplitStrategy.SOURCE, key=key, seed=seed, validation_size=validation_size, test_size=test_size)


def group_split(records: Sequence[T], *, key: Callable[[Any], Any] | None = None, validation_size: float = 0.1, test_size: float = 0.2, seed: int = 42) -> DataSplit[T]:
    _fractions(validation_size, test_size)
    return _grouped_split(records, SplitStrategy.GROUP, key=key, seed=seed, validation_size=validation_size, test_size=test_size)


def temporal_split(records: Sequence[T], *, key: Callable[[Any], Any] | None = None, validation_size: float = 0.1, test_size: float = 0.2, seed: int | None = None) -> DataSplit[T]:
    _fractions(validation_size, test_size)
    key_fn = key or _default_key(SplitStrategy.TEMPORAL)
    def sortable(record: T) -> tuple[int, Any]:
        value = key_fn(record)
        try:
            return (0, datetime.fromisoformat(str(value).replace("Z", "+00:00")))
        except ValueError:
            try:
                return (1, float(value))
            except (TypeError, ValueError) as exc:
                raise SplitError(f"temporal_split key is not date/time or numeric: {value!r}") from exc
    ordered = sorted(records, key=sortable)
    test_count = max(1, round(len(ordered) * test_size)) if ordered else 0
    validation_count = max(1, round(len(ordered) * validation_size)) if len(ordered) - test_count >= 3 else 0
    train_end = len(ordered) - test_count - validation_count
    return DataSplit(SplitStrategy.TEMPORAL, tuple(ordered[:train_end]), tuple(ordered[train_end:train_end + validation_count]), tuple(ordered[train_end + validation_count:]), seed=seed)


def external_test(records: Sequence[T], *, external_records: Sequence[T] | None = None, key: Callable[[Any], Any] | None = None, validation_size: float = 0.1, seed: int = 42) -> DataSplit[T]:
    key_fn = key or (lambda record: record.get("is_external", False) or record.get("split") in {"external", "external_test"} if isinstance(record, dict) else False)
    external = list(external_records) if external_records is not None else [record for record in records if bool(key_fn(record))]
    external_ids = {id(record) for record in external}
    internal = [record for record in records if id(record) not in external_ids] if external_records is not None else [record for record in records if not bool(key_fn(record))]
    if not external:
        raise SplitError("external_test requires explicitly marked external records")
    internal_split = _three_way(internal, seed=seed, validation_size=validation_size, test_size=0.01 if len(internal) >= 3 else 0.001)
    return DataSplit(SplitStrategy.EXTERNAL_TEST, internal_split.train, internal_split.validation, tuple(external), seed=seed, metadata={"external_count": len(external)})


def split_records(records: Sequence[T], strategy: SplitStrategy | str, **kwargs: Any) -> DataSplit[T]:
    selected = _strategy(strategy)
    functions = {
        SplitStrategy.RANDOM: random_split,
        SplitStrategy.SCAFFOLD: scaffold_split,
        SplitStrategy.CLUSTER: cluster_split,
        SplitStrategy.SOURCE: source_split,
        SplitStrategy.TEMPORAL: temporal_split,
        SplitStrategy.GROUP: group_split,
        SplitStrategy.EXTERNAL_TEST: external_test,
    }
    return functions[selected](records, **kwargs)
