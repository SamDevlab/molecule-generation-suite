from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any
import uuid

from research_os.core.hashing import canonical_json, sha256_json
from research_os.core.provenance import ProvenanceRecord


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INDETERMINATE = "INDETERMINATE"
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    SKIPPED = "SKIPPED"


class EvidenceLevel(str, Enum):
    E0_HEURISTIC = "E0_HEURISTIC"
    E1_ML = "E1_ML"
    E2_COMPUTATIONAL = "E2_COMPUTATIONAL"
    E3_PHYSICS = "E3_PHYSICS"
    E4_CURATED_EXPERIMENTAL = "E4_CURATED_EXPERIMENTAL"
    E5_VALIDATED_EXPERIMENTAL = "E5_VALIDATED_EXPERIMENTAL"
    TEST_SYNTHETIC = "TEST_SYNTHETIC"
    E_TEST_SYNTHETIC = "TEST_SYNTHETIC"


class RunLifecycle(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INDETERMINATE = "INDETERMINATE"
    SEALED = "SEALED"


class RunMutationError(RuntimeError):
    """Raised when a sealed run or one of its guarded fields is modified."""


_MISSING = object()


class _GuardedDict(dict[str, Any]):
    def __init__(self, owner: "RunManifest", values: dict[str, Any] | None = None):
        self._owner = owner
        super().__init__(values or {})

    def _check(self) -> None:
        self._owner._ensure_mutable()

    def __setitem__(self, key: str, value: Any) -> None:
        self._check()
        super().__setitem__(key, value)

    def __delitem__(self, key: str) -> None:
        self._check()
        super().__delitem__(key)

    def clear(self) -> None:
        self._check()
        super().clear()

    def pop(self, key: str, default: Any = _MISSING) -> Any:
        self._check()
        return super().pop(key) if default is _MISSING else super().pop(key, default)

    def popitem(self) -> tuple[str, Any]:
        self._check()
        return super().popitem()

    def setdefault(self, key: str, default: Any = None) -> Any:
        self._check()
        return super().setdefault(key, default)

    def update(self, *args: Any, **kwargs: Any) -> None:
        self._check()
        super().update(*args, **kwargs)


class _GuardedList(list[Any]):
    def __init__(self, owner: "RunManifest", values: list[Any] | None = None):
        self._owner = owner
        super().__init__(values or [])

    def _check(self) -> None:
        self._owner._ensure_mutable()

    def append(self, value: Any) -> None:
        self._check()
        super().append(value)
        self._owner._observe_gate(value)

    def extend(self, values: Any) -> None:
        self._check()
        values = list(values)
        super().extend(values)
        for value in values:
            self._owner._observe_gate(value)

    def insert(self, index: int, value: Any) -> None:
        self._check()
        super().insert(index, value)
        self._owner._observe_gate(value)

    def __setitem__(self, index: Any, value: Any) -> None:
        self._check()
        super().__setitem__(index, value)
        if isinstance(index, int):
            self._owner._observe_gate(value)

    def __delitem__(self, index: Any) -> None:
        self._check()
        super().__delitem__(index)

    def clear(self) -> None:
        self._check()
        super().clear()

    def pop(self, index: int = -1) -> Any:
        self._check()
        return super().pop(index)

    def remove(self, value: Any) -> None:
        self._check()
        super().remove(value)

    def reverse(self) -> None:
        self._check()
        super().reverse()

    def sort(self, *args: Any, **kwargs: Any) -> None:
        self._check()
        super().sort(*args, **kwargs)


class _SealedTuple(tuple[Any, ...]):
    def _blocked(self, *args: Any, **kwargs: Any) -> None:
        raise RunMutationError("sealed run data is immutable")

    append = extend = insert = remove = pop = clear = reverse = sort = _blocked


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    kind: str
    level: EvidenceLevel
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    provenance_ids: tuple[str, ...] = ()
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    rule_id: str
    status: GateStatus
    reason: str
    evidence_ids: tuple[str, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunLineage:
    parent_run_id: str | None = None
    rerun_of: str | None = None
    derived_from: tuple[str, ...] = ()
    supersedes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _FrozenDict(dict[str, Any]):
    def _blocked(self, *args: Any, **kwargs: Any) -> None:
        raise RunMutationError("sealed run data is immutable")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = _blocked
    __ior__ = _blocked


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


@dataclass
class RunManifest:
    lab: str
    experiment: str
    inputs: dict[str, Any]
    config: dict[str, Any] = field(default_factory=dict)
    run_id: str = field(default_factory=lambda: f"RUN-{uuid.uuid4().hex[:12].upper()}")
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence: list[Evidence] = field(default_factory=list)
    provenance: list[ProvenanceRecord] = field(default_factory=list)
    gates: list[GateResult] = field(default_factory=list)
    lifecycle: RunLifecycle = RunLifecycle.CREATED
    lineage: RunLineage = field(default_factory=RunLineage)
    dataset_manifests: list[Any] = field(default_factory=list)
    environment_manifest: Any | None = None
    claims: list[Any] = field(default_factory=list)
    sealed: bool = False
    seal_hash: str | None = None

    def __setattr__(self, name: str, value: Any) -> None:
        if name not in {"sealed", "seal_hash"} and getattr(self, "sealed", False):
            raise RunMutationError(f"run {getattr(self, 'run_id', '<unknown>')} is sealed and immutable")
        if name in {"sealed", "seal_hash"} and getattr(self, "sealed", False) and value != getattr(self, name, None):
            raise RunMutationError(f"run {getattr(self, 'run_id', '<unknown>')} is sealed and immutable")
        object.__setattr__(self, name, value)

    def __post_init__(self) -> None:
        object.__setattr__(self, "lifecycle", _as_lifecycle(self.lifecycle))
        object.__setattr__(self, "inputs", _GuardedDict(self, self.inputs))
        object.__setattr__(self, "config", _GuardedDict(self, self.config))
        object.__setattr__(self, "evidence", _GuardedList(self, self.evidence))
        object.__setattr__(self, "provenance", _GuardedList(self, self.provenance))
        object.__setattr__(self, "gates", _GuardedList(self, self.gates))
        object.__setattr__(self, "dataset_manifests", _GuardedList(self, self.dataset_manifests))
        object.__setattr__(self, "claims", _GuardedList(self, self.claims))
        for gate in self.gates:
            self._observe_gate(gate)

    def _ensure_mutable(self) -> None:
        if self.sealed or self.lifecycle == RunLifecycle.SEALED:
            raise RunMutationError(f"run {self.run_id} is sealed and immutable")

    def _observe_gate(self, value: Any) -> None:
        if not isinstance(value, GateResult) or value.status == GateStatus.PASS:
            return
        if self.lifecycle == RunLifecycle.CREATED:
            object.__setattr__(self, "lifecycle", RunLifecycle.RUNNING)
        if value.status in {GateStatus.INDETERMINATE, GateStatus.INSUFFICIENT_EVIDENCE, GateStatus.OUT_OF_DOMAIN, GateStatus.SKIPPED}:
            if self.lifecycle in {RunLifecycle.RUNNING, RunLifecycle.COMPLETED}:
                object.__setattr__(self, "lifecycle", RunLifecycle.INDETERMINATE)
        elif self.lifecycle in {RunLifecycle.RUNNING, RunLifecycle.COMPLETED}:
            object.__setattr__(self, "lifecycle", RunLifecycle.FAILED)

    @property
    def input_hash(self) -> str:
        return sha256_json(self.inputs)

    @property
    def status(self) -> str:
        return self.lifecycle.value

    @property
    def parent_run_id(self) -> str | None:
        return self.lineage.parent_run_id

    @property
    def rerun_of(self) -> str | None:
        return self.lineage.rerun_of

    @property
    def derived_from(self) -> tuple[str, ...]:
        return self.lineage.derived_from

    @property
    def first_loss(self) -> GateResult | None:
        return next((gate for gate in self.gates if gate.status != GateStatus.PASS), None)

    @property
    def passed(self) -> bool:
        return self.lifecycle in {RunLifecycle.COMPLETED, RunLifecycle.SEALED} and bool(self.gates) and self.first_loss is None

    @property
    def first_loss_rule_id(self) -> str | None:
        loss = self.first_loss
        return loss.rule_id if loss else None

    def transition(self, target: RunLifecycle | str) -> "RunManifest":
        self._ensure_mutable()
        target = _as_lifecycle(target)
        allowed = {
            RunLifecycle.CREATED: {RunLifecycle.RUNNING},
            RunLifecycle.RUNNING: {RunLifecycle.COMPLETED, RunLifecycle.FAILED, RunLifecycle.INDETERMINATE},
            RunLifecycle.COMPLETED: {RunLifecycle.FAILED, RunLifecycle.INDETERMINATE, RunLifecycle.SEALED},
            RunLifecycle.FAILED: {RunLifecycle.SEALED},
            RunLifecycle.INDETERMINATE: {RunLifecycle.SEALED},
            RunLifecycle.SEALED: set(),
        }
        if target not in allowed[self.lifecycle]:
            raise RunMutationError(f"invalid run lifecycle transition: {self.lifecycle.value} -> {target.value}")
        object.__setattr__(self, "lifecycle", target)
        if target == RunLifecycle.SEALED:
            self._seal_contents()
        return self

    def start(self) -> "RunManifest":
        return self.transition(RunLifecycle.RUNNING)

    def complete(self) -> "RunManifest":
        if self.lifecycle == RunLifecycle.CREATED:
            self.start()
        if self.first_loss is not None:
            raise RunMutationError("a run with FIRST_LOSS cannot be completed")
        return self.transition(RunLifecycle.COMPLETED) if self.lifecycle == RunLifecycle.RUNNING else self

    def fail(self) -> "RunManifest":
        if self.lifecycle == RunLifecycle.CREATED:
            self.start()
        return self.transition(RunLifecycle.FAILED) if self.lifecycle == RunLifecycle.RUNNING else self

    def mark_indeterminate(self) -> "RunManifest":
        if self.lifecycle == RunLifecycle.CREATED:
            self.start()
        return self.transition(RunLifecycle.INDETERMINATE) if self.lifecycle == RunLifecycle.RUNNING else self

    def add_claim(self, claim: Any) -> None:
        self.claims.append(claim)

    def attach_dataset(self, manifest: Any) -> None:
        self.dataset_manifests.append(manifest)

    def attach_environment(self, manifest: Any) -> None:
        self._ensure_mutable()
        object.__setattr__(self, "environment_manifest", manifest)

    def _serializable(self, *, include_seal: bool = True) -> dict[str, Any]:
        data = asdict(self)
        data["lifecycle"] = self.lifecycle.value
        data["lineage"] = self.lineage.to_dict()
        if self.environment_manifest is not None and hasattr(self.environment_manifest, "to_dict"):
            data["environment_manifest"] = self.environment_manifest.to_dict()
        data["dataset_manifests"] = [item.to_dict() if hasattr(item, "to_dict") else item for item in self.dataset_manifests]
        data["claims"] = [item.to_dict() if hasattr(item, "to_dict") else item for item in self.claims]
        for item in data.get("evidence", []):
            if hasattr(item.get("level"), "value"):
                item["level"] = item["level"].value
        for item in data.get("gates", []):
            if hasattr(item.get("status"), "value"):
                item["status"] = item["status"].value
        data.pop("sealed", None)
        if not include_seal:
            data.pop("seal_hash", None)
        return data

    def _seal_contents(self) -> None:
        for evidence in self.evidence:
            object.__setattr__(evidence, "payload", _freeze(evidence.payload))
        for provenance in self.provenance:
            object.__setattr__(provenance, "conditions", _freeze(provenance.conditions))
        for gate in self.gates:
            object.__setattr__(gate, "diagnostics", _freeze(gate.diagnostics))
        for claim in self.claims:
            if hasattr(claim, "conditions"):
                object.__setattr__(claim, "conditions", _freeze(getattr(claim, "conditions")))
        object.__setattr__(self, "inputs", _freeze(dict(self.inputs)))
        object.__setattr__(self, "config", _freeze(dict(self.config)))
        object.__setattr__(self, "evidence", _SealedTuple(self.evidence))
        object.__setattr__(self, "provenance", _SealedTuple(self.provenance))
        object.__setattr__(self, "gates", _SealedTuple(self.gates))
        object.__setattr__(self, "dataset_manifests", _SealedTuple(self.dataset_manifests))
        object.__setattr__(self, "claims", _SealedTuple(self.claims))
        object.__setattr__(self, "sealed", True)
        object.__setattr__(self, "seal_hash", sha256_json(self._serializable(include_seal=False)))

    def seal(self) -> "RunManifest":
        if self.lifecycle not in {RunLifecycle.COMPLETED, RunLifecycle.FAILED, RunLifecycle.INDETERMINATE}:
            raise RunMutationError("only completed, failed or indeterminate runs can be sealed")
        return self.transition(RunLifecycle.SEALED)

    def digest(self) -> str:
        return hashlib.sha256(canonical_json(self._serializable()).encode("utf-8")).hexdigest()


def _as_lifecycle(value: RunLifecycle | str) -> RunLifecycle:
    if isinstance(value, RunLifecycle):
        return value
    try:
        return RunLifecycle(str(value))
    except ValueError as exc:
        raise ValueError(f"unknown run lifecycle: {value}") from exc
