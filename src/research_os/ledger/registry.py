"""Transactional SQLite index for immutable Research OS bundles."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Iterable, Iterator, Mapping, Sequence
import uuid

from research_os.bundles import BundleVerificationStatus, verify_bundle
from research_os.core.hashing import sha256_json
from research_os.core.types import RunLineage
from research_os.observability import StructuredLogger
from research_os.ledger.schema import (
    ClaimIndexRecord,
    EvidenceIndexRecord,
    FirstDivergence,
    LedgerConflictError,
    LedgerError,
    LedgerGate,
    LedgerIntegrityError,
    LedgerOperationStatus,
    LedgerRegistration,
    LedgerSchemaError,
    LedgerVerificationResult,
    LineageCycleError,
    LineageGraph,
    RebuildReport,
    ReproducibilityStatus,
    RunDependency,
    RunIndexRecord,
    WorkflowComparison,
    WorkflowExecution,
    WorkflowRerunResult,
    WorkflowStepIndex,
)


SCHEMA_VERSION = 2
_RELATIONS = {"depends_on", "derived_from", "rerun_of", "supersedes", "consumes_output_of"}
_ORDER_COLUMNS = {
    "created_at": "r.created_at",
    "started_at": "r.started_at",
    "completed_at": "r.completed_at",
    "run_id": "r.run_id",
    "status": "r.status",
    "lab": "r.lab",
    "experiment": "r.experiment",
    "index_created_at": "r.index_created_at",
    "index_updated_at": "r.index_updated_at",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _string(value: Any) -> str | None:
    return None if value is None else str(value)


def _enum_value(value: Any) -> str | None:
    return value.value if hasattr(value, "value") else _string(value)


def _normalise(value: Any) -> Any:
    """Remove identity and wall-clock fields for value-level comparison."""
    if isinstance(value, Mapping):
        ignored = {"run_id", "evidence_id", "claim_id", "provenance_id", "evidence_ids", "produced_evidence_ids", "consumed_evidence_ids", "created_at", "started_at", "completed_at", "digest", "seal_hash"}
        return {str(key): _normalise(item) for key, item in sorted(value.items()) if key not in ignored}
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


def _first_loss(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    loss = payload.get("first_loss")
    if isinstance(loss, Mapping):
        return dict(loss)
    gates = payload.get("gates")
    if isinstance(gates, list):
        return next((dict(item) for item in gates if isinstance(item, Mapping) and _enum_value(item.get("status")) != "PASS"), None)
    return None


def _status(payload: Mapping[str, Any], *, workflow: bool = False) -> str:
    explicit = payload.get("run_status") or payload.get("status") or payload.get("lifecycle")
    if explicit:
        value = _enum_value(explicit)
        if value != "PENDING":
            return str(value)
    if workflow:
        steps = payload.get("steps")
        values = [str(item.get("status")) for item in (steps.values() if isinstance(steps, Mapping) else steps or ()) if isinstance(item, Mapping)]
        if values and all(value == "PASS" for value in values):
            return "PASS"
        loss = next((value for value in values if value not in {"PASS", "PENDING"}), None)
        return loss or "INDETERMINATE"
    return "INDETERMINATE" if _first_loss(payload) else "COMPLETED"


def _manifest_env(payload: Mapping[str, Any], outer: Mapping[str, Any]) -> Mapping[str, Any]:
    candidate = payload.get("environment_manifest")
    return candidate if isinstance(candidate, Mapping) else outer


def _ids(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value if item)
    return ()


def _engine_items(value: Any, output: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    output = output if output is not None else []
    if isinstance(value, Mapping):
        if "engine_id" in value and ("manifest_hash" in value or "configuration_hash" in value):
            output.append(dict(value))
        for item in value.values():
            _engine_items(item, output)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _engine_items(item, output)
    return output


def _engine_field(item: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if item.get(key) is not None:
            return item.get(key)
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    for key in keys:
        if metadata.get(key) is not None:
            return metadata.get(key)
    return None


class RunRegistry:
    """Persistent, reconstructible index over sealed Research OS bundles.

    The registry never treats a SQLite row as the scientific source of truth.
    ``register_run`` first verifies the bundle and stores only searchable
    metadata and identifiers; deleting the database can therefore be repaired
    with :meth:`rebuild_index`.
    """

    def __init__(self, root: str | Path = "research-ledger", *, db_path: str | Path | None = None, logger: StructuredLogger | None = None):
        candidate = Path(db_path) if db_path is not None else Path(root)
        if db_path is None and (candidate.exists() and candidate.is_file() or candidate.suffix.lower() in {".sqlite", ".db", ".sqlite3"}):
            self.db_path = candidate
            self.root = candidate.parent
        elif db_path is not None:
            self.db_path = candidate
            self.root = candidate.parent
        else:
            self.root = candidate
            self.db_path = candidate / "research_ledger.sqlite"
        self.root.mkdir(parents=True, exist_ok=True)
        self.logger = logger or StructuredLogger()
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(str(self.db_path), timeout=5.0, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._configure()
        self._ensure_schema()

    def _configure(self) -> None:
        with self._connection:
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA busy_timeout=5000")

    def _ensure_schema(self) -> None:
        with self._lock:
            version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise LedgerSchemaError(f"ledger schema {version} is newer than supported schema {SCHEMA_VERSION}")
            if version == 0:
                self._create_schema()
                self._connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                self._connection.commit()
            elif version == 1:
                self._migrate_v1_to_v2()
                self._connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                self._connection.commit()
            elif version != SCHEMA_VERSION:
                raise LedgerSchemaError(f"ledger schema {version} has no safe migration to {SCHEMA_VERSION}")
            required = {"runs", "run_dependencies", "run_claims", "run_evidence", "workflows", "workflow_steps", "saved_queries"}
            tables = {row[0] for row in self._connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not required.issubset(tables):
                raise LedgerSchemaError("ledger schema is missing required tables")
            self._ensure_engine_tables()

    def _ensure_engine_tables(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS run_engines (
                run_id TEXT NOT NULL,
                engine_id TEXT NOT NULL,
                version TEXT,
                status TEXT,
                readiness TEXT,
                manifest_hash TEXT,
                configuration_hash TEXT,
                protocol_id TEXT,
                mechanism_hash TEXT,
                database_hash TEXT,
                receptor_hash TEXT,
                grid_hash TEXT,
                manifest_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (run_id, engine_id, manifest_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_run_engines_id ON run_engines(engine_id, version);
            CREATE INDEX IF NOT EXISTS idx_run_engines_mechanism ON run_engines(mechanism_hash);
            CREATE INDEX IF NOT EXISTS idx_run_engines_database ON run_engines(database_hash);
            CREATE INDEX IF NOT EXISTS idx_run_engines_receptor ON run_engines(receptor_hash);
            CREATE INDEX IF NOT EXISTS idx_run_engines_grid ON run_engines(grid_hash);
            """
        )
        self._connection.commit()

    def _migrate_v1_to_v2(self) -> None:
        self._connection.execute("CREATE TABLE IF NOT EXISTS saved_queries(name TEXT PRIMARY KEY, query_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
        self._connection.execute("INSERT OR REPLACE INTO schema_meta(key,value) VALUES('schema_version','2')")

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                bundle_id TEXT NOT NULL,
                bundle_path TEXT NOT NULL,
                bundle_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                sealed INTEGER NOT NULL DEFAULT 0 CHECK (sealed IN (0,1)),
                lab TEXT,
                experiment TEXT,
                workflow_id TEXT,
                plan_id TEXT,
                created_at TEXT,
                started_at TEXT,
                completed_at TEXT,
                git_commit TEXT,
                environment_id TEXT,
                environment_hash TEXT,
                first_loss_rule_id TEXT,
                first_loss_status TEXT,
                parent_run_id TEXT,
                rerun_of TEXT,
                supersedes TEXT,
                inputs_json TEXT NOT NULL DEFAULT '{}',
                config_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}',
                index_created_at TEXT NOT NULL,
                index_updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS run_datasets (
                run_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                version TEXT,
                sha256 TEXT,
                artifact_path TEXT,
                PRIMARY KEY (run_id, dataset_id, version)
            );
            CREATE TABLE IF NOT EXISTS run_models (
                run_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                training_run_id TEXT,
                PRIMARY KEY (run_id, model_id)
            );
            CREATE TABLE IF NOT EXISTS run_claims (
                run_id TEXT NOT NULL,
                claim_id TEXT NOT NULL,
                statement TEXT NOT NULL DEFAULT '',
                status TEXT,
                minimum_evidence_level TEXT,
                evidence_ids_json TEXT NOT NULL DEFAULT '[]',
                conditions_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT,
                PRIMARY KEY (run_id, claim_id)
            );
            CREATE TABLE IF NOT EXISTS run_evidence (
                run_id TEXT NOT NULL,
                evidence_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                level TEXT NOT NULL,
                source TEXT,
                provenance_ids_json TEXT NOT NULL DEFAULT '[]',
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT,
                PRIMARY KEY (run_id, evidence_id)
            );
            CREATE TABLE IF NOT EXISTS run_tags (
                run_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (run_id, tag)
            );
            CREATE TABLE IF NOT EXISTS run_dependencies (
                downstream_run_id TEXT NOT NULL,
                upstream_run_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                created_at TEXT,
                PRIMARY KEY (downstream_run_id, upstream_run_id, relation)
            );
            CREATE TABLE IF NOT EXISTS workflows (
                workflow_run_id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                status TEXT NOT NULL,
                bundle_path TEXT NOT NULL,
                created_at TEXT,
                started_at TEXT,
                completed_at TEXT,
                first_loss_step_id TEXT,
                first_loss_rule_id TEXT,
                git_commit TEXT,
                environment_id TEXT,
                environment_hash TEXT,
                rerun_of TEXT,
                plan_json TEXT NOT NULL DEFAULT '{}',
                index_created_at TEXT NOT NULL,
                index_updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workflow_steps (
                workflow_run_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                run_id TEXT,
                status TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                first_loss_rule_id TEXT,
                first_loss_status TEXT,
                requires_json TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY (workflow_run_id, step_id)
            );
            CREATE TABLE IF NOT EXISTS workflow_comparisons (
                original_workflow_id TEXT NOT NULL,
                rerun_workflow_id TEXT NOT NULL,
                status TEXT NOT NULL,
                same_plan INTEGER,
                same_inputs INTEGER,
                same_config INTEGER,
                same_datasets INTEGER,
                same_code INTEGER,
                same_environment INTEGER,
                steps_compared_json TEXT NOT NULL DEFAULT '[]',
                first_divergence_step TEXT,
                first_divergence_rule_id TEXT,
                first_divergence_json TEXT,
                differences_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                PRIMARY KEY (original_workflow_id, rerun_workflow_id)
            );
            CREATE TABLE IF NOT EXISTS saved_queries (
                name TEXT PRIMARY KEY,
                query_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_runs_status_created ON runs(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_runs_lab_experiment ON runs(lab, experiment);
            CREATE INDEX IF NOT EXISTS idx_runs_workflow ON runs(workflow_id, plan_id);
            CREATE INDEX IF NOT EXISTS idx_runs_git_environment ON runs(git_commit, environment_hash);
            CREATE INDEX IF NOT EXISTS idx_runs_first_loss ON runs(first_loss_rule_id, first_loss_status);
            CREATE INDEX IF NOT EXISTS idx_datasets_id ON run_datasets(dataset_id, sha256);
            CREATE INDEX IF NOT EXISTS idx_claims_id_status ON run_claims(claim_id, status, minimum_evidence_level);
            CREATE INDEX IF NOT EXISTS idx_evidence_id_level_kind ON run_evidence(evidence_id, level, kind);
            CREATE INDEX IF NOT EXISTS idx_tags_tag ON run_tags(tag);
            CREATE INDEX IF NOT EXISTS idx_dependencies_upstream ON run_dependencies(upstream_run_id, relation);
            CREATE INDEX IF NOT EXISTS idx_dependencies_downstream ON run_dependencies(downstream_run_id, relation);
            CREATE INDEX IF NOT EXISTS idx_workflow_steps_run ON workflow_steps(run_id);
            INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', '2');
            """
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "RunRegistry":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _log(self, operation: str, *, run_id: str | None = None, workflow_id: str | None = None, status: str | None = None, message: str | None = None, fields: Mapping[str, Any] | None = None) -> None:
        self.logger.emit(f"ledger_{operation}", run_id=run_id, status=status, message=message, fields={"workflow_id": workflow_id, **dict(fields or {})})

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                self._connection.execute("BEGIN")
                yield self._connection
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def register_run(
        self,
        bundle: Any | None = None,
        bundle_path: str | Path | None = None,
        *,
        run: Any | None = None,
        tags: Iterable[str] = (),
        dependencies: Iterable[RunDependency | Mapping[str, Any] | tuple[str, str, str]] = (),
        model_ids: Iterable[str] = (),
        workflow_id: str | None = None,
        plan_id: str | None = None,
        rerun_of: str | None = None,
        supersedes: str | None = None,
    ) -> LedgerRegistration:
        source = run if run is not None else bundle
        if bundle_path is not None:
            root = Path(bundle_path)
        elif isinstance(source, (str, Path)):
            root = Path(source)
        elif isinstance(getattr(source, "root", None), (str, Path)):
            root = Path(getattr(source, "root"))
        else:
            root = None
        if root is None or root.is_file():
            if root is not None and root.is_file():
                root = root.parent
            else:
                raise ValueError("register_run requires a ResearchBundle or bundle_path")
        try:
            try:
                verification = verify_bundle(root)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                raise LedgerIntegrityError(f"bundle verification could not be completed: {root}", rule_id="BUNDLE-MANIFEST-001") from exc
            if verification.status == BundleVerificationStatus.FAIL:
                loss = verification.first_loss
                rule = loss.rule_id if loss else "LEDGER-BUNDLE-001"
                raise LedgerIntegrityError(f"bundle cannot be indexed: {root}", rule_id=rule)
            records, workflow = self._extract_bundle(root, tags=tags, model_ids=model_ids, workflow_id=workflow_id, plan_id=plan_id, rerun_of=rerun_of, supersedes=supersedes)
            if not records:
                raise LedgerIntegrityError(f"bundle has no indexable run: {root}")
            explicit_dependencies = tuple(self._dependency(value) for value in dependencies)
            with self._transaction() as connection:
                record_by_id = {row["run_id"]: row for row in records}
                existing = {row["run_id"]: row for row in connection.execute("SELECT run_id, bundle_hash FROM runs WHERE run_id IN (%s)" % ",".join("?" * len(records)), tuple(record_by_id))} if records else {}
                conflicts = [run_id for run_id, row in existing.items() if row["bundle_hash"] != record_by_id[run_id]["bundle_hash"]]
                if conflicts:
                    raise LedgerConflictError(f"run id is already indexed with a different bundle hash: {', '.join(sorted(conflicts))}")
                missing = [row for row in records if row["run_id"] not in existing]
                known = set(existing) | {row["run_id"] for row in records}
                for dependency in explicit_dependencies:
                    if dependency.downstream_run_id not in known or dependency.upstream_run_id not in known and not self._run_exists(connection, dependency.upstream_run_id):
                        raise LedgerIntegrityError("dependency references an unknown run", rule_id="LEDGER-LINEAGE-001")
                    if dependency.relation not in _RELATIONS:
                        raise LedgerIntegrityError(f"unsupported dependency relation: {dependency.relation}", rule_id="LEDGER-LINEAGE-001")
                for row in missing:
                    self._insert_row(connection, row)
                for dependency in self._lineage_dependencies(records):
                    self._insert_dependency(connection, dependency, check_cycle=False)
                for dependency in explicit_dependencies:
                    self._insert_dependency(connection, dependency, check_cycle=True)
                for dependency in self._workflow_dependencies(workflow):
                    self._insert_dependency(connection, dependency, check_cycle=True)
                if workflow is not None:
                    self._insert_workflow(connection, workflow, rerun_of=rerun_of)
            registered = tuple(row["run_id"] for row in records if row["run_id"] not in existing)
            primary = records[0]["run_id"]
            operation_status = LedgerOperationStatus.REGISTERED if registered else LedgerOperationStatus.ALREADY_REGISTERED
            self._log("register_run", run_id=primary, workflow_id=workflow.workflow_run_id if workflow else None, status=operation_status.value, fields={"bundle_id": records[0]["bundle_id"], "indexed_runs": len(registered), "verification": verification.status.value})
            return LedgerRegistration(primary, operation_status, records[0]["bundle_id"])
        except Exception as exc:
            self._log("register_run_failed", run_id=_string(getattr(source, "run_id", None)), status="FAIL", message=str(exc), fields={"rule_id": getattr(exc, "rule_id", "LEDGER-BUNDLE-001")})
            raise

    def _extract_bundle(self, root: Path, *, tags: Iterable[str], model_ids: Iterable[str], workflow_id: str | None, plan_id: str | None, rerun_of: str | None, supersedes: str | None) -> tuple[list[dict[str, Any]], WorkflowExecution | None]:
        bundle = _load(root / "bundle.json", {})
        manifest = _load(root / "manifest.json", {})
        environment = _load(root / "environment.json", {})
        datasets = _load(root / "datasets" / "manifests.json", [])
        evidence = _load(root / "evidence" / "evidence.json", [])
        claims = _load(root / "claims" / "claims.json", [])
        engines = _load(root / "engines" / "manifests.json", [])
        steps = _load(root / "steps" / "steps.json", [])
        if not isinstance(manifest, Mapping) or not isinstance(bundle, Mapping) or not bundle.get("bundle_id"):
            raise LedgerIntegrityError(f"bundle metadata is incomplete: {root}")
        is_workflow = isinstance(manifest.get("runs"), Mapping) and isinstance(manifest.get("steps"), Mapping)
        resolved_workflow_id = workflow_id or (str(manifest.get("plan_id")) if is_workflow else None)
        resolved_plan_id = plan_id or resolved_workflow_id
        payloads: list[tuple[str, Mapping[str, Any], str | None]] = []
        primary_id = str(manifest.get("plan_id") or manifest.get("run_id") or bundle.get("run_id") or "")
        if is_workflow:
            payloads.append((primary_id, manifest, "workflow"))
            for step_id, payload in manifest.get("runs", {}).items():
                if isinstance(payload, Mapping):
                    payloads.append((str(payload.get("run_id") or step_id), payload, str(step_id)))
        else:
            payloads.append((str(manifest.get("run_id") or bundle.get("run_id") or ""), manifest, None))
        records: list[dict[str, Any]] = []
        base_model_ids = set(str(value) for value in model_ids if value)
        for run_id, payload, step_id in payloads:
            if not run_id:
                continue
            env = _manifest_env(payload, environment)
            loss = _first_loss(payload)
            child_evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else evidence
            child_claims = [item for item in claims if isinstance(item, Mapping) and str(item.get("run_id") or primary_id) == run_id]
            if not child_claims and run_id == primary_id:
                child_claims = [item for item in claims if isinstance(item, Mapping)]
            child_datasets = payload.get("dataset_manifests") if isinstance(payload.get("dataset_manifests"), list) and payload.get("dataset_manifests") else datasets
            engine_items = _engine_items(engines) + _engine_items(payload)
            unique_engines = {(item.get("engine_id"), item.get("manifest_hash"), item.get("protocol_id")): item for item in engine_items if item.get("engine_id")}
            row_model_ids = set(base_model_ids)
            model_refs: dict[str, str | None] = {}
            for item in child_evidence:
                if isinstance(item, Mapping):
                    self._collect_model_ids(item, row_model_ids, model_refs)
            for item in child_claims:
                if isinstance(item, Mapping):
                    self._collect_model_ids(item, row_model_ids, model_refs)
            records.append({
                "run_id": run_id,
                "bundle_id": str(bundle.get("bundle_id")),
                "bundle_path": str(root.resolve()),
                "bundle_hash": str(bundle.get("bundle_hash") or ""),
                "status": _status(payload, workflow=step_id == "workflow"),
                "sealed": bool(payload.get("sealed", bundle.get("sealed", False)) or bundle.get("sealed", False)),
                "lab": "workflow" if step_id == "workflow" else _string(payload.get("lab")),
                "experiment": _string(payload.get("experiment") or (resolved_plan_id if step_id == "workflow" else None)),
                "workflow_id": resolved_workflow_id,
                "plan_id": resolved_plan_id,
                "created_at": _string(payload.get("created_at") or bundle.get("created_at")),
                "started_at": _string(payload.get("started_at")),
                "completed_at": _string(payload.get("completed_at")),
                "git_commit": _string((env.get("git") or {}).get("commit") if isinstance(env.get("git"), Mapping) else None),
                "environment_id": _string(env.get("environment_id")),
                "environment_hash": _string(env.get("environment_hash")),
                "first_loss_rule_id": _string(loss.get("rule_id") if loss else None),
                "first_loss_status": _enum_value(loss.get("status")) if loss else None,
                "parent_run_id": _string((payload.get("lineage") or {}).get("parent_run_id") if isinstance(payload.get("lineage"), Mapping) else None),
                "rerun_of": rerun_of or _string((payload.get("lineage") or {}).get("rerun_of") if isinstance(payload.get("lineage"), Mapping) else None),
                "supersedes": supersedes or _string((payload.get("lineage") or {}).get("supersedes") if isinstance(payload.get("lineage"), Mapping) else None),
                "inputs_json": _json(payload.get("inputs") or {}),
                "config_json": _json(payload.get("config") or {}),
                # The index stores searchable metadata and identifiers only;
                # result values remain in the bundle source of truth.
                "result_json": "{}",
                "tags": tuple(sorted(set(str(value) for value in tags if value))),
                "datasets": tuple(item for item in child_datasets if isinstance(item, Mapping)),
                "claims": tuple(item for item in child_claims if isinstance(item, Mapping)),
                "evidence": tuple(item for item in child_evidence if isinstance(item, Mapping)),
                "model_ids": tuple(sorted(row_model_ids)),
                "model_refs": model_refs,
                "engines": tuple(unique_engines.values()),
            })
        workflow = self._workflow_from_payload(manifest, records, steps, environment, root) if is_workflow and resolved_workflow_id else None
        return records, workflow

    @staticmethod
    def _collect_model_ids(value: Any, result: set[str], refs: dict[str, str | None] | None = None) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key in {"model_id", "model_ids"}:
                    found = _ids(item)
                    result.update(found)
                    for model_id in found:
                        training_run_id = value.get("training_run_id")
                        if refs is not None:
                            refs[model_id] = _string(training_run_id)
                else:
                    RunRegistry._collect_model_ids(item, result, refs)
        elif isinstance(value, (list, tuple)):
            for item in value:
                RunRegistry._collect_model_ids(item, result, refs)

    def _workflow_from_payload(self, manifest: Mapping[str, Any], records: Sequence[Mapping[str, Any]], steps: Any, environment: Mapping[str, Any], root: Path) -> WorkflowExecution:
        workflow_id = str(manifest.get("plan_id"))
        record_by_id = {row["run_id"]: row for row in records}
        step_items: list[WorkflowStepIndex] = []
        raw_steps = list(steps) if isinstance(steps, list) else [{"step_id": key, **value} for key, value in manifest.get("steps", {}).items() if isinstance(value, Mapping)]
        for ordinal, item in enumerate(raw_steps):
            if not isinstance(item, Mapping):
                continue
            step_id = str(item.get("step_id") or f"step-{ordinal}")
            run_id = _string(item.get("run_id"))
            if run_id is None:
                run_payload = manifest.get("runs", {}).get(step_id, {}) if isinstance(manifest.get("runs"), Mapping) else {}
                run_id = _string(run_payload.get("run_id")) if isinstance(run_payload, Mapping) else None
            row = record_by_id.get(run_id or "")
            loss = item.get("first_loss") if isinstance(item.get("first_loss"), Mapping) else (_first_loss(row) if row else None)
            step_items.append(WorkflowStepIndex(workflow_id, step_id, run_id, str(item.get("status") or (row or {}).get("status") or "SKIPPED"), ordinal, _string(loss.get("rule_id") if loss else None), _enum_value(loss.get("status")) if loss else None, _ids(item.get("requires"))))
        first = next((item for item in step_items if item.status != "PASS"), None)
        started_values = [item.get("started_at") for item in raw_steps if isinstance(item, Mapping) and item.get("started_at")]
        completed_values = [item.get("completed_at") for item in raw_steps if isinstance(item, Mapping) and item.get("completed_at")]
        env_git = environment.get("git") if isinstance(environment.get("git"), Mapping) else {}
        return WorkflowExecution(
            workflow_run_id=workflow_id,
            plan_id=workflow_id,
            status=_status(manifest, workflow=True),
            created_at=_string(manifest.get("created_at") or _load(root / "bundle.json", {}).get("created_at")),
            started_at=min(map(str, started_values)) if started_values else None,
            completed_at=max(map(str, completed_values)) if completed_values else None,
            first_loss_step_id=first.step_id if first else None,
            first_loss_rule_id=first.first_loss_rule_id if first else None,
            git_commit=_string(env_git.get("commit")),
            environment_id=_string(environment.get("environment_id")),
            environment_hash=_string(environment.get("environment_hash")),
            steps=tuple(step_items),
        )

    @staticmethod
    def _dependency(value: RunDependency | Mapping[str, Any] | tuple[str, str, str]) -> RunDependency:
        if isinstance(value, RunDependency):
            return value
        if isinstance(value, Mapping):
            downstream = value.get("downstream_run_id") or value.get("run_id")
            upstream = value.get("upstream_run_id") or value.get("depends_on")
            return RunDependency(str(downstream), str(upstream), str(value.get("relation", "depends_on")))
        downstream, upstream, *relation = value
        return RunDependency(str(downstream), str(upstream), str(relation[0] if relation else "depends_on"))

    @staticmethod
    def _run_exists(connection: sqlite3.Connection, run_id: str) -> bool:
        return connection.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone() is not None

    def _insert_row(self, connection: sqlite3.Connection, row: Mapping[str, Any]) -> None:
        now = _now()
        connection.execute(
            """INSERT INTO runs(run_id,bundle_id,bundle_path,bundle_hash,status,sealed,lab,experiment,workflow_id,plan_id,created_at,started_at,completed_at,git_commit,environment_id,environment_hash,first_loss_rule_id,first_loss_status,parent_run_id,rerun_of,supersedes,inputs_json,config_json,result_json,index_created_at,index_updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            tuple(row.get(name) for name in ("run_id", "bundle_id", "bundle_path", "bundle_hash", "status", "sealed", "lab", "experiment", "workflow_id", "plan_id", "created_at", "started_at", "completed_at", "git_commit", "environment_id", "environment_hash", "first_loss_rule_id", "first_loss_status", "parent_run_id", "rerun_of", "supersedes", "inputs_json", "config_json", "result_json")) + (now, now),
        )
        for tag in row.get("tags", ()):
            connection.execute("INSERT OR IGNORE INTO run_tags(run_id,tag) VALUES(?,?)", (row["run_id"], tag))
        for item in row.get("datasets", ()):
            connection.execute("INSERT OR IGNORE INTO run_datasets(run_id,dataset_id,version,sha256,artifact_path) VALUES(?,?,?,?,?)", (row["run_id"], item.get("dataset_id"), item.get("version"), item.get("sha256"), item.get("artifact_path")))
        for item in row.get("claims", ()):
            claim_id = str(item.get("claim_id") or "")
            if claim_id:
                connection.execute("INSERT OR IGNORE INTO run_claims(run_id,claim_id,statement,status,minimum_evidence_level,evidence_ids_json,conditions_json,created_at) VALUES(?,?,?,?,?,?,?,?)", (row["run_id"], claim_id, str(item.get("statement", "")), _enum_value(item.get("status")), _enum_value(item.get("minimum_evidence_level")), _json(item.get("evidence_ids", [])), _json(item.get("conditions", {})), item.get("created_at") or row.get("created_at")))
        for item in row.get("evidence", ()):
            evidence_id = str(item.get("evidence_id") or "")
            if evidence_id:
                connection.execute("INSERT OR IGNORE INTO run_evidence(run_id,evidence_id,kind,level,source,provenance_ids_json,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)", (row["run_id"], evidence_id, str(item.get("kind", "")), _enum_value(item.get("level")) or "UNKNOWN", item.get("source"), _json(item.get("provenance_ids", [])), _json(item.get("payload", {})), item.get("created_at") or row.get("created_at")))
        for model_id in row.get("model_ids", ()):
            connection.execute("INSERT OR IGNORE INTO run_models(run_id,model_id,training_run_id) VALUES(?,?,?)", (row["run_id"], model_id, (row.get("model_refs") or {}).get(model_id)))
        for item in row.get("engines", ()):
            connection.execute(
                """INSERT OR IGNORE INTO run_engines(run_id,engine_id,version,status,readiness,manifest_hash,configuration_hash,protocol_id,mechanism_hash,database_hash,receptor_hash,grid_hash,manifest_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (row["run_id"], item.get("engine_id"), item.get("version") or item.get("library_version"), item.get("status"), item.get("readiness"), item.get("manifest_hash"), item.get("configuration_hash"), item.get("protocol_id"), _engine_field(item, "mechanism_sha256", "mechanism_hash"), _engine_field(item, "database_sha256", "database_hash"), _engine_field(item, "receptor_sha256", "receptor_hash"), _engine_field(item, "grid_hash"), _json(item)),
            )

    def _lineage_dependencies(self, records: Sequence[Mapping[str, Any]]) -> tuple[RunDependency, ...]:
        result: list[RunDependency] = []
        for row in records:
            for field, relation in (("parent_run_id", "derived_from"), ("rerun_of", "rerun_of"), ("supersedes", "supersedes")):
                upstream = row.get(field)
                if upstream:
                    result.append(RunDependency(str(row["run_id"]), str(upstream), relation))
            lineage = row.get("lineage")
            for upstream in _ids(lineage.get("derived_from") if isinstance(lineage, Mapping) else None):
                result.append(RunDependency(str(row["run_id"]), upstream, "derived_from"))
        return tuple(result)

    @staticmethod
    def _workflow_dependencies(workflow: WorkflowExecution | None) -> tuple[RunDependency, ...]:
        if workflow is None:
            return ()
        run_by_step = {step.step_id: step.run_id for step in workflow.steps if step.run_id}
        return tuple(RunDependency(run_by_step[step.step_id], run_by_step[requires], "depends_on") for step in workflow.steps for requires in step.requires if step.step_id in run_by_step and requires in run_by_step)

    @staticmethod
    def _insert_dependency(connection: sqlite3.Connection, dependency: RunDependency, *, check_cycle: bool) -> None:
        if dependency.relation not in _RELATIONS:
            raise LedgerIntegrityError(f"unsupported dependency relation: {dependency.relation}", rule_id="LEDGER-LINEAGE-001")
        if check_cycle and RunRegistry._would_cycle(connection, dependency.downstream_run_id, dependency.upstream_run_id):
            raise LineageCycleError(f"dependency would create a lineage cycle: {dependency.downstream_run_id} -> {dependency.upstream_run_id}")
        connection.execute("INSERT OR IGNORE INTO run_dependencies(downstream_run_id,upstream_run_id,relation,created_at) VALUES(?,?,?,?)", (dependency.downstream_run_id, dependency.upstream_run_id, dependency.relation, dependency.created_at or _now()))

    @staticmethod
    def _would_cycle(connection: sqlite3.Connection, downstream: str, upstream: str) -> bool:
        if downstream == upstream:
            return True
        pending = [upstream]
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current == downstream:
                return True
            if current in visited:
                continue
            visited.add(current)
            pending.extend(row[0] for row in connection.execute("SELECT upstream_run_id FROM run_dependencies WHERE downstream_run_id=?", (current,)))
        return False

    def _insert_workflow(self, connection: sqlite3.Connection, workflow: WorkflowExecution, *, rerun_of: str | None = None) -> None:
        now = _now()
        connection.execute("INSERT OR IGNORE INTO workflows(workflow_run_id,plan_id,status,bundle_path,created_at,started_at,completed_at,first_loss_step_id,first_loss_rule_id,git_commit,environment_id,environment_hash,rerun_of,plan_json,index_created_at,index_updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (workflow.workflow_run_id, workflow.plan_id, workflow.status, self._bundle_path_for_run(connection, workflow.workflow_run_id), workflow.created_at, workflow.started_at, workflow.completed_at, workflow.first_loss_step_id, workflow.first_loss_rule_id, workflow.git_commit, workflow.environment_id, workflow.environment_hash, rerun_of, _json({"steps": [step.to_dict() for step in workflow.steps]}), now, now))
        for step in workflow.steps:
            connection.execute("INSERT OR IGNORE INTO workflow_steps(workflow_run_id,step_id,run_id,status,ordinal,first_loss_rule_id,first_loss_status,requires_json) VALUES(?,?,?,?,?,?,?,?)", (workflow.workflow_run_id, step.step_id, step.run_id, step.status, step.ordinal, step.first_loss_rule_id, step.first_loss_status, _json(step.requires)))

    @staticmethod
    def _bundle_path_for_run(connection: sqlite3.Connection, run_id: str) -> str:
        row = connection.execute("SELECT bundle_path FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return str(row[0]) if row else ""

    def get_run(self, run_id: str) -> RunIndexRecord:
        with self._lock:
            row = self._connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                self._log("run_get", run_id=run_id, status="NOT_FOUND")
                raise KeyError(f"run not indexed: {run_id}")
            record = self._record(row)
            self._log("run_get", run_id=run_id, status=record.status)
            return record

    def _record(self, row: sqlite3.Row) -> RunIndexRecord:
        run_id = str(row["run_id"])
        values = lambda table, column: tuple(str(item[0]) for item in self._connection.execute(f"SELECT {column} FROM {table} WHERE run_id=? ORDER BY {column}", (run_id,)))
        return RunIndexRecord(run_id=run_id, bundle_id=row["bundle_id"], bundle_path=row["bundle_path"], bundle_hash=row["bundle_hash"], status=row["status"], sealed=bool(row["sealed"]), lab=row["lab"], experiment=row["experiment"], workflow_id=row["workflow_id"], plan_id=row["plan_id"], created_at=row["created_at"], started_at=row["started_at"], completed_at=row["completed_at"], git_commit=row["git_commit"], environment_id=row["environment_id"], environment_hash=row["environment_hash"], first_loss_rule_id=row["first_loss_rule_id"], first_loss_status=row["first_loss_status"], parent_run_id=row["parent_run_id"], rerun_of=row["rerun_of"], supersedes=row["supersedes"], index_created_at=row["index_created_at"], index_updated_at=row["index_updated_at"], tags=values("run_tags", "tag"), dataset_ids=values("run_datasets", "dataset_id"), claim_ids=values("run_claims", "claim_id"), model_ids=values("run_models", "model_id"), evidence_ids=values("run_evidence", "evidence_id"), engine_ids=values("run_engines", "engine_id"))

    def list_runs(self, *, limit: int = 100, offset: int = 0, order_by: str = "created_at", descending: bool = True) -> list[RunIndexRecord]:
        column = _ORDER_COLUMNS.get(order_by)
        if column is None:
            raise ValueError(f"unsupported run order_by: {order_by}")
        with self._lock:
            rows = self._connection.execute(f"SELECT * FROM runs r ORDER BY {column} {'DESC' if descending else 'ASC'}, r.run_id LIMIT ? OFFSET ?", (max(0, int(limit)), max(0, int(offset)))).fetchall()
            result = [self._record(row) for row in rows]
        self._log("list_runs", status="PASS", fields={"count": len(result), "limit": limit, "offset": offset})
        return result

    def search_runs(self, *, status: str | Sequence[str] | None = None, lab: str | None = None, experiment: str | None = None, workflow: str | None = None, workflow_id: str | None = None, plan_id: str | None = None, dataset: str | None = None, dataset_id: str | None = None, claim: str | None = None, claim_id: str | None = None, model: str | None = None, model_id: str | None = None, rule_id: str | None = None, date_from: str | None = None, date_to: str | None = None, tag: str | None = None, git: str | None = None, git_commit: str | None = None, environment: str | None = None, environment_hash: str | None = None, limit: int = 100, offset: int = 0, order_by: str = "created_at", descending: bool = True) -> list[RunIndexRecord]:
        column = _ORDER_COLUMNS.get(order_by)
        if column is None:
            raise ValueError(f"unsupported run order_by: {order_by}")
        where: list[str] = []
        params: list[Any] = []
        if status is not None:
            values = [status] if isinstance(status, str) else list(status)
            where.append("r.status IN (%s)" % ",".join("?" * len(values)))
            params.extend(values)
        for field, value in (("r.lab", lab), ("r.experiment", experiment), ("r.workflow_id", workflow_id or workflow), ("r.plan_id", plan_id), ("r.first_loss_rule_id", rule_id), ("r.git_commit", git_commit or git), ("r.environment_hash", environment_hash or environment)):
            if value is not None:
                where.append(f"{field}=?")
                params.append(value)
        if date_from is not None:
            where.append("r.created_at>=?")
            params.append(date_from)
        if date_to is not None:
            where.append("r.created_at<=?")
            params.append(date_to)
        for table, column_name, value in (("run_datasets", "dataset_id", dataset_id or dataset), ("run_claims", "claim_id", claim_id or claim), ("run_models", "model_id", model_id or model), ("run_tags", "tag", tag)):
            if value is not None:
                where.append(f"EXISTS (SELECT 1 FROM {table} x WHERE x.run_id=r.run_id AND x.{column_name}=?)")
                params.append(value)
        query = "SELECT * FROM runs r" + (" WHERE " + " AND ".join(where) if where else "") + f" ORDER BY {column} {'DESC' if descending else 'ASC'}, r.run_id LIMIT ? OFFSET ?"
        params.extend((max(0, int(limit)), max(0, int(offset))))
        with self._lock:
            result = [self._record(row) for row in self._connection.execute(query, params).fetchall()]
        self._log("search_runs", status="PASS", fields={"count": len(result), "filters": {key: value for key, value in locals().items() if key in {"status", "lab", "experiment", "workflow_id", "dataset_id", "claim_id", "model_id", "rule_id", "tag"} and value is not None}})
        return result

    def save_query(self, name: str, filters: Mapping[str, Any]) -> dict[str, Any]:
        if not str(name).strip():
            raise ValueError("saved query name cannot be empty")
        payload = dict(filters)
        now = _now()
        with self._transaction() as connection:
            connection.execute("INSERT INTO saved_queries(name,query_json,created_at,updated_at) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET query_json=excluded.query_json,updated_at=excluded.updated_at", (name, _json(payload), now, now))
        self._log("save_query", status="PASS", fields={"name": name})
        return {"name": name, "filters": payload, "updated_at": now}

    def get_saved_query(self, name: str) -> dict[str, Any]:
        row = self._connection.execute("SELECT * FROM saved_queries WHERE name=?", (name,)).fetchone()
        if row is None:
            raise KeyError(f"saved query not found: {name}")
        return {"name": row["name"], "filters": json.loads(row["query_json"]), "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def list_saved_queries(self) -> list[dict[str, Any]]:
        return [self.get_saved_query(row[0]) for row in self._connection.execute("SELECT name FROM saved_queries ORDER BY name").fetchall()]

    def delete_saved_query(self, name: str) -> bool:
        with self._transaction() as connection:
            cursor = connection.execute("DELETE FROM saved_queries WHERE name=?", (name,))
        removed = cursor.rowcount > 0
        self._log("delete_query", status="REMOVED" if removed else "NOT_FOUND", fields={"name": name})
        return removed

    def run_saved_query(self, name: str, **overrides: Any) -> list[RunIndexRecord]:
        query = self.get_saved_query(name)
        filters = {**query["filters"], **overrides}
        return self.search_runs(**filters)

    def verify_run(self, run_id: str):
        record = self.get_run(run_id)
        result = verify_bundle(record.bundle_path)
        self._log("verify_run", run_id=run_id, status=result.status.value, fields={"rule_id": result.first_loss.rule_id if result.first_loss else None})
        return result

    def compare_runs(self, original: str, rerun: str):
        """Compare indexed run values, retaining the v1.4 comparison shape."""
        from research_os.reproducibility import RunComparison

        left_record = self.get_run(original)
        right_record = self.get_run(rerun)
        left = self._run_payload(left_record)
        right = self._run_payload(right_record)
        same_inputs = _normalise(left.get("inputs", {})) == _normalise(right.get("inputs", {}))
        same_config = _normalise(left.get("config", {})) == _normalise(right.get("config", {}))
        left_datasets = left.get("dataset_manifests", []) or _load(Path(left_record.bundle_path) / "datasets" / "manifests.json", [])
        right_datasets = right.get("dataset_manifests", []) or _load(Path(right_record.bundle_path) / "datasets" / "manifests.json", [])
        same_dataset_hashes = [item.get("sha256") for item in left_datasets if isinstance(item, Mapping)] == [item.get("sha256") for item in right_datasets if isinstance(item, Mapping)]
        same_code_commit = _optional_equal(left_record.git_commit, right_record.git_commit)
        same_environment = _optional_equal(left_record.environment_hash, right_record.environment_hash)
        same_evidence_values = _normalise({"evidence": left.get("evidence", []), "gates": left.get("gates", [])}) == _normalise({"evidence": right.get("evidence", []), "gates": right.get("gates", [])})
        same_claims = _normalise(left.get("claims", [])) == _normalise(right.get("claims", []))
        left_engines = _engine_items({"manifests": _load(Path(left_record.bundle_path) / "engines" / "manifests.json", []), "payload": left})
        right_engines = _engine_items({"manifests": _load(Path(right_record.bundle_path) / "engines" / "manifests.json", []), "payload": right})
        engine_differences = _engine_provenance_differences(left_engines, right_engines)
        differences = tuple(name for name, value in (("inputs", same_inputs), ("config", same_config), ("dataset_hashes", same_dataset_hashes), ("code_commit", same_code_commit), ("environment", same_environment), ("evidence_values", same_evidence_values), ("claims", same_claims)) if value is False) + engine_differences
        if not same_inputs or not same_config or not same_dataset_hashes or not same_evidence_values or not same_claims or engine_differences:
            status = ReproducibilityStatus.DIVERGED
        elif same_environment is False:
            status = ReproducibilityStatus.REPRODUCED_WITH_ENVIRONMENT_CHANGE
        elif same_code_commit is None or same_environment is None:
            status = ReproducibilityStatus.NOT_COMPARABLE
        else:
            status = ReproducibilityStatus.REPRODUCED
        first = {"category": engine_differences[0], "reason": "engine provenance changed"} if engine_differences else None
        result = RunComparison(original, rerun, status, same_inputs, same_config, same_dataset_hashes, same_code_commit, same_environment, same_evidence_values, same_claims, differences, engine_differences, first)
        self._log("compare_runs", run_id=rerun, status=status.value, fields={"original_run_id": original})
        return result

    @staticmethod
    def _run_payload(record: RunIndexRecord) -> Mapping[str, Any]:
        manifest = _load(Path(record.bundle_path) / "manifest.json", {})
        if isinstance(manifest.get("runs"), Mapping):
            for payload in manifest["runs"].values():
                if isinstance(payload, Mapping) and str(payload.get("run_id")) == record.run_id:
                    return payload
        return manifest

    def remove_index_entry(self, run_id: str) -> LedgerRegistration:
        with self._transaction() as connection:
            if not self._run_exists(connection, run_id):
                self._log("remove_index_entry", run_id=run_id, status=LedgerOperationStatus.NOT_FOUND.value)
                return LedgerRegistration(run_id, LedgerOperationStatus.NOT_FOUND)
            connection.execute("DELETE FROM workflow_comparisons WHERE original_workflow_id=? OR rerun_workflow_id=?", (run_id, run_id))
            connection.execute("DELETE FROM workflow_steps WHERE workflow_run_id=? OR run_id=?", (run_id, run_id))
            connection.execute("DELETE FROM workflows WHERE workflow_run_id=?", (run_id,))
            connection.execute("DELETE FROM run_dependencies WHERE downstream_run_id=? OR upstream_run_id=?", (run_id, run_id))
            for table in ("run_tags", "run_datasets", "run_models", "run_claims", "run_evidence", "run_engines"):
                connection.execute(f"DELETE FROM {table} WHERE run_id=?", (run_id,))
            connection.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
        self._log("remove_index_entry", run_id=run_id, status=LedgerOperationStatus.REMOVED.value)
        return LedgerRegistration(run_id, LedgerOperationStatus.REMOVED)

    def rebuild_index(self, bundle_root: str | Path) -> RebuildReport:
        indexed: list[str] = []
        already: list[str] = []
        skipped: list[str] = []
        failures: list[dict[str, Any]] = []
        root = Path(bundle_root)
        for metadata in sorted(root.rglob("bundle.json")) if root.exists() else ():
            bundle_dir = metadata.parent
            verification = verify_bundle(bundle_dir)
            if verification.status == BundleVerificationStatus.FAIL:
                failures.append({"path": str(bundle_dir), "status": verification.status.value, "rule_id": verification.first_loss.rule_id if verification.first_loss else "LEDGER-BUNDLE-001"})
                continue
            try:
                registration = self.register_run(bundle_dir)
                (already if registration.status == LedgerOperationStatus.ALREADY_REGISTERED else indexed).append(registration.run_id)
            except LedgerError as exc:
                failures.append({"path": str(bundle_dir), "status": "FAIL", "rule_id": getattr(exc, "rule_id", "LEDGER-BUNDLE-001"), "error": str(exc)})
            except (OSError, ValueError, TypeError, KeyError) as exc:
                failures.append({"path": str(bundle_dir), "status": "FAIL", "rule_id": "LEDGER-BUNDLE-001", "error": str(exc)})
        self._log("rebuild_index", status="PASS" if not failures else "INDETERMINATE", fields={"indexed": len(indexed), "already_registered": len(already), "failures": len(failures)})
        return RebuildReport(tuple(indexed), tuple(already), tuple(skipped), tuple(failures))

    def add_dependency(self, dependency: RunDependency | Mapping[str, Any] | tuple[str, str, str]) -> RunDependency:
        item = self._dependency(dependency)
        if item.relation not in _RELATIONS:
            raise LedgerIntegrityError(f"unsupported dependency relation: {item.relation}", rule_id="LEDGER-LINEAGE-001")
        with self._transaction() as connection:
            if not self._run_exists(connection, item.downstream_run_id) or not self._run_exists(connection, item.upstream_run_id):
                raise LedgerIntegrityError("dependency references an unknown run", rule_id="LEDGER-LINEAGE-001")
            self._insert_dependency(connection, item, check_cycle=True)
        self._log("add_dependency", run_id=item.downstream_run_id, status="PASS", fields={"upstream_run_id": item.upstream_run_id, "relation": item.relation})
        return item

    def _edge_rows(self) -> list[RunDependency]:
        rows = self._connection.execute("SELECT downstream_run_id,upstream_run_id,relation,created_at FROM run_dependencies ORDER BY downstream_run_id,upstream_run_id,relation").fetchall()
        return [RunDependency(row[0], row[1], row[2], row[3]) for row in rows]

    def _walk(self, run_id: str, *, upstream: bool) -> tuple[str, ...]:
        edges = self._edge_rows()
        adjacency: dict[str, list[str]] = {}
        for edge in edges:
            adjacency.setdefault(edge.downstream_run_id if upstream else edge.upstream_run_id, []).append(edge.upstream_run_id if upstream else edge.downstream_run_id)
        result: list[str] = []
        visited: set[str] = set()
        active: set[str] = set()

        def visit(current: str) -> None:
            if current in active:
                raise LineageCycleError(f"lineage cycle detected at {current}")
            if current in visited:
                return
            active.add(current)
            for neighbor in adjacency.get(current, ()):
                if neighbor == run_id or neighbor not in visited:
                    if neighbor not in result:
                        result.append(neighbor)
                    visit(neighbor)
            active.remove(current)
            visited.add(current)

        with self._lock:
            visit(run_id)
        return tuple(result)

    def get_ancestors(self, run_id: str) -> tuple[str, ...]:
        self.get_run(run_id)
        return self._walk(run_id, upstream=True)

    def get_descendants(self, run_id: str) -> tuple[str, ...]:
        self.get_run(run_id)
        return self._walk(run_id, upstream=False)

    def get_lineage(self, run_id: str) -> LineageGraph:
        ancestors = self.get_ancestors(run_id)
        descendants = self.get_descendants(run_id)
        dependencies = tuple(edge for edge in self._edge_rows() if edge.downstream_run_id == run_id or edge.upstream_run_id == run_id)
        graph = LineageGraph(run_id, ancestors, descendants, dependencies)
        self._log("lineage", run_id=run_id, status="PASS", fields={"ancestors": len(ancestors), "descendants": len(descendants)})
        return graph

    def get_claim(self, claim_id: str) -> ClaimIndexRecord:
        with self._lock:
            row = self._connection.execute("SELECT * FROM run_claims WHERE claim_id=? ORDER BY created_at LIMIT 1", (claim_id,)).fetchone()
            if row is None:
                raise KeyError(f"claim not indexed: {claim_id}")
            return ClaimIndexRecord(claim_id=row["claim_id"], run_id=row["run_id"], statement=row["statement"], status=row["status"], minimum_evidence_level=row["minimum_evidence_level"], evidence_ids=tuple(json.loads(row["evidence_ids_json"])), created_at=row["created_at"], conditions=dict(json.loads(row["conditions_json"])))

    def claims_from_run(self, run_id: str) -> list[ClaimIndexRecord]:
        rows = self._connection.execute("SELECT claim_id FROM run_claims WHERE run_id=? ORDER BY created_at,claim_id", (run_id,)).fetchall()
        return [self.get_claim(row[0]) for row in rows]

    def claims_by_status(self, status: str) -> list[ClaimIndexRecord]:
        ids = self._connection.execute("SELECT claim_id FROM run_claims WHERE status=? ORDER BY created_at,claim_id", (status,)).fetchall()
        return [self.get_claim(row[0]) for row in ids]

    def claims_by_evidence_level(self, level: str) -> list[ClaimIndexRecord]:
        ids = self._connection.execute("SELECT claim_id FROM run_claims WHERE minimum_evidence_level=? ORDER BY created_at,claim_id", (level,)).fetchall()
        return [self.get_claim(row[0]) for row in ids]

    def get_evidence(self, evidence_id: str) -> EvidenceIndexRecord:
        with self._lock:
            row = self._connection.execute("SELECT * FROM run_evidence WHERE evidence_id=? ORDER BY created_at LIMIT 1", (evidence_id,)).fetchone()
            if row is None:
                raise KeyError(f"evidence not indexed: {evidence_id}")
            return EvidenceIndexRecord(evidence_id=row["evidence_id"], run_id=row["run_id"], kind=row["kind"], level=row["level"], source=row["source"], provenance_ids=tuple(json.loads(row["provenance_ids_json"])), payload=dict(json.loads(row["payload_json"])), created_at=row["created_at"])

    def evidence_from_run(self, run_id: str) -> list[EvidenceIndexRecord]:
        ids = self._connection.execute("SELECT evidence_id FROM run_evidence WHERE run_id=? ORDER BY created_at,evidence_id", (run_id,)).fetchall()
        return [self.get_evidence(row[0]) for row in ids]

    def evidence_by_level(self, level: str) -> list[EvidenceIndexRecord]:
        ids = self._connection.execute("SELECT evidence_id FROM run_evidence WHERE level=? ORDER BY created_at,evidence_id", (level,)).fetchall()
        return [self.get_evidence(row[0]) for row in ids]

    def evidence_by_kind(self, kind: str) -> list[EvidenceIndexRecord]:
        ids = self._connection.execute("SELECT evidence_id FROM run_evidence WHERE kind=? ORDER BY created_at,evidence_id", (kind,)).fetchall()
        return [self.get_evidence(row[0]) for row in ids]

    def runs_using_dataset(self, dataset_id: str, *, version: str | None = None) -> list[RunIndexRecord]:
        query = "SELECT DISTINCT r.* FROM runs r JOIN run_datasets d ON d.run_id=r.run_id WHERE d.dataset_id=?" + (" AND d.version=?" if version else "") + " ORDER BY r.created_at,r.run_id"
        params = (dataset_id, version) if version else (dataset_id,)
        with self._lock:
            return [self._record(row) for row in self._connection.execute(query, params).fetchall()]

    def datasets_used_by_run(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(row) for row in self._connection.execute("SELECT dataset_id,version,sha256,artifact_path FROM run_datasets WHERE run_id=? ORDER BY dataset_id,version", (run_id,)).fetchall()]

    def runs_using_model(self, model_id: str) -> list[RunIndexRecord]:
        with self._lock:
            return [self._record(row) for row in self._connection.execute("SELECT r.* FROM runs r JOIN run_models m ON m.run_id=r.run_id WHERE m.model_id=? ORDER BY r.created_at,r.run_id", (model_id,)).fetchall()]

    def training_run_for_model(self, model_id: str) -> str | None:
        row = self._connection.execute("SELECT training_run_id FROM run_models WHERE model_id=? AND training_run_id IS NOT NULL LIMIT 1", (model_id,)).fetchone()
        return row[0] if row else None

    def trace_claim(self, claim_id: str) -> dict[str, Any]:
        claim = self.get_claim(claim_id)
        return {"claim": claim.to_dict(), "run": self.get_run(claim.run_id).to_dict(), "evidence": [self.get_evidence(item).to_dict() for item in claim.evidence_ids if self._evidence_exists(item)]}

    def trace_evidence(self, evidence_id: str) -> dict[str, Any]:
        evidence = self.get_evidence(evidence_id)
        run = self.get_run(evidence.run_id)
        sources = _load(Path(run.bundle_path) / "provenance" / "sources.json", [])
        provenance = [item for item in sources if isinstance(item, Mapping) and item.get("provenance_id") in evidence.provenance_ids]
        return {"evidence": evidence.to_dict(), "run": run.to_dict(), "provenance": provenance, "claims": [claim.to_dict() for claim in self._claims_for_evidence(evidence_id)]}

    def engine_manifests_for_run(self, run_id: str, engine_id: str | None = None) -> list[dict[str, Any]]:
        self.get_run(run_id)
        query = "SELECT manifest_json FROM run_engines WHERE run_id=?"
        params: list[Any] = [run_id]
        if engine_id is not None:
            query += " AND engine_id=?"
            params.append(engine_id)
        return [dict(json.loads(row[0])) for row in self._connection.execute(query, params)]

    def trace_engine_run(self, run_id: str, engine_id: str | None = None) -> dict[str, Any]:
        record = self.get_run(run_id)
        manifests = self.engine_manifests_for_run(run_id, engine_id)
        if not manifests:
            raise KeyError(f"engine manifest not indexed for run: {run_id}")
        return {"run": record.to_dict(), "engines": manifests, "environment": _load(Path(record.bundle_path) / "environment.json", {}), "evidence": _load(Path(record.bundle_path) / "evidence" / "evidence.json", [])}

    def runs_using_engine(self, engine_id: str) -> list[RunIndexRecord]:
        rows = self._connection.execute("SELECT DISTINCT run_id FROM run_engines WHERE engine_id=? ORDER BY run_id", (engine_id,)).fetchall()
        return [self.get_run(row[0]) for row in rows]

    def runs_using_engine_version(self, engine_id: str, version: str) -> list[RunIndexRecord]:
        rows = self._connection.execute("SELECT DISTINCT run_id FROM run_engines WHERE engine_id=? AND version=? ORDER BY run_id", (engine_id, version)).fetchall()
        return [self.get_run(row[0]) for row in rows]

    def _runs_using_engine_hash(self, column: str, value: str) -> list[RunIndexRecord]:
        if column not in {"mechanism_hash", "database_hash", "receptor_hash", "grid_hash"}:
            raise ValueError("unsupported engine provenance field")
        rows = self._connection.execute(f"SELECT DISTINCT run_id FROM run_engines WHERE {column}=? ORDER BY run_id", (value,)).fetchall()
        return [self.get_run(row[0]) for row in rows]

    def runs_using_mechanism(self, mechanism_hash: str) -> list[RunIndexRecord]: return self._runs_using_engine_hash("mechanism_hash", mechanism_hash)
    def runs_using_database(self, database_hash: str) -> list[RunIndexRecord]: return self._runs_using_engine_hash("database_hash", database_hash)
    def runs_using_receptor(self, receptor_hash: str) -> list[RunIndexRecord]: return self._runs_using_engine_hash("receptor_hash", receptor_hash)
    def runs_using_grid(self, grid_hash: str) -> list[RunIndexRecord]: return self._runs_using_engine_hash("grid_hash", grid_hash)

    def _evidence_exists(self, evidence_id: str) -> bool:
        return self._connection.execute("SELECT 1 FROM run_evidence WHERE evidence_id=?", (evidence_id,)).fetchone() is not None

    def _claims_for_evidence(self, evidence_id: str) -> list[ClaimIndexRecord]:
        rows = self._connection.execute("SELECT claim_id FROM run_claims WHERE EXISTS (SELECT 1 FROM json_each(run_claims.evidence_ids_json) WHERE value=?)", (evidence_id,)).fetchall()
        return [self.get_claim(row[0]) for row in rows]

    def get_workflow(self, workflow_id: str) -> WorkflowExecution:
        with self._lock:
            row = self._connection.execute("SELECT * FROM workflows WHERE workflow_run_id=?", (workflow_id,)).fetchone()
            if row is None:
                raise KeyError(f"workflow not indexed: {workflow_id}")
            steps = tuple(WorkflowStepIndex(workflow_id, item["step_id"], item["run_id"], item["status"], item["ordinal"], item["first_loss_rule_id"], item["first_loss_status"], tuple(json.loads(item["requires_json"]))) for item in self._connection.execute("SELECT * FROM workflow_steps WHERE workflow_run_id=? ORDER BY ordinal,step_id", (workflow_id,)).fetchall())
            return WorkflowExecution(workflow_id, row["plan_id"], row["status"], row["created_at"], row["started_at"], row["completed_at"], row["first_loss_step_id"], row["first_loss_rule_id"], row["git_commit"], row["environment_id"], row["environment_hash"], row["rerun_of"], steps)

    def list_workflows(self, *, limit: int = 100, offset: int = 0) -> list[WorkflowExecution]:
        with self._lock:
            ids = self._connection.execute("SELECT workflow_run_id FROM workflows ORDER BY created_at DESC,workflow_run_id LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            return [self.get_workflow(row[0]) for row in ids]

    def register_workflow(self, plan_run: Any, bundle: Any | None = None, **kwargs: Any) -> WorkflowExecution:
        if bundle is not None:
            self.register_run(bundle, **kwargs)
        workflow_id = str(getattr(plan_run, "plan_id", None) or getattr(plan_run, "workflow_run_id", ""))
        return self.get_workflow(workflow_id)

    def _workflow_snapshot(self, workflow_id: str) -> dict[str, Any]:
        workflow = self.get_workflow(workflow_id)
        path = self._connection.execute("SELECT bundle_path FROM workflows WHERE workflow_run_id=?", (workflow_id,)).fetchone()[0]
        manifest = _load(Path(path) / "manifest.json", {})
        runs = manifest.get("runs", {}) if isinstance(manifest, Mapping) else {}
        by_step = {step.step_id: runs.get(step.step_id, {}) if isinstance(runs, Mapping) else {} for step in workflow.steps}
        return {"workflow": workflow, "manifest": manifest, "runs": by_step, "bundle_path": path}

    def compare_workflows(self, original: str | WorkflowExecution, rerun: str | WorkflowExecution) -> WorkflowComparison:
        original_id = original.workflow_run_id if isinstance(original, WorkflowExecution) else str(original)
        rerun_id = rerun.workflow_run_id if isinstance(rerun, WorkflowExecution) else str(rerun)
        left = self._workflow_snapshot(original_id)
        right = self._workflow_snapshot(rerun_id)
        left_wf: WorkflowExecution = left["workflow"]
        right_wf: WorkflowExecution = right["workflow"]
        left_ids = [step.step_id for step in left_wf.steps]
        right_ids = [step.step_id for step in right_wf.steps]
        same_plan = _plan_signature(left["manifest"], left_wf) == _plan_signature(right["manifest"], right_wf)
        shared = tuple(step_id for step_id in left_ids if step_id in right_ids)
        flags: dict[str, bool | None] = {"same_inputs": True, "same_config": True, "same_datasets": True, "same_code": _optional_equal(left_wf.git_commit, right_wf.git_commit), "same_environment": _optional_equal(left_wf.environment_hash, right_wf.environment_hash)}
        first: FirstDivergence | None = None
        differences: list[str] = []
        engine_differences: list[str] = []
        if not same_plan:
            differences.append("plan")
            for left_step, right_step in zip(left_wf.steps, right_wf.steps):
                if left_step.step_id != right_step.step_id or left_step.requires != right_step.requires:
                    first = FirstDivergence(left_step.step_id, "LEDGER-WORKFLOW-PLAN-001", "workflow plan topology changed", left_step.to_dict(), right_step.to_dict())
                    break
        for step_id in shared:
            left_payload = left["runs"].get(step_id, {})
            right_payload = right["runs"].get(step_id, {})
            for key, flag in (("inputs", "same_inputs"), ("config", "same_config")):
                if _normalise(left_payload.get(key, {})) != _normalise(right_payload.get(key, {})):
                    flags[flag] = False
                    differences.append(key)
                    if first is None:
                        first = FirstDivergence(step_id, f"LEDGER-COMPARISON-{key.upper()}-001", f"{key} changed", left_payload.get(key), right_payload.get(key))
            left_data = left_payload.get("dataset_manifests", []) or []
            right_data = right_payload.get("dataset_manifests", []) or []
            if [item.get("sha256") for item in left_data if isinstance(item, Mapping)] != [item.get("sha256") for item in right_data if isinstance(item, Mapping)]:
                flags["same_datasets"] = False
                differences.append("datasets")
                if first is None:
                    first = FirstDivergence(step_id, "LEDGER-DATASET-001", "dataset hash changed", left_data, right_data)
            step_engine_differences = _engine_provenance_differences(_engine_items(left_payload), _engine_items(right_payload))
            for category in step_engine_differences:
                if category not in engine_differences:
                    engine_differences.append(category)
                if category not in differences:
                    differences.append(category)
                if first is None:
                    first = FirstDivergence(step_id, category, "engine provenance changed", left_payload.get("config"), right_payload.get("config"))
            if _normalise({"status": left_payload.get("status"), "gates": left_payload.get("gates", []), "evidence": left_payload.get("evidence", [])}) != _normalise({"status": right_payload.get("status"), "gates": right_payload.get("gates", []), "evidence": right_payload.get("evidence", [])}):
                differences.append("result")
                loss = _first_loss(right_payload) or _first_loss(left_payload)
                if first is None:
                    first = FirstDivergence(step_id, _string(loss.get("rule_id") if loss else "LEDGER-COMPARISON-VALUE-001"), "step result, gate or evidence value changed", left_payload.get("status"), right_payload.get("status"))
        for name, flag in flags.items():
            if flag is False and name not in differences:
                differences.append(name.removeprefix("same_"))
        status = _comparison_status(left_wf, right_wf, same_plan, flags, first)
        comparison = WorkflowComparison(original_id, rerun_id, status, same_plan, flags["same_inputs"], flags["same_config"], flags["same_datasets"], flags["same_code"], flags["same_environment"], shared, first.step_id if first else None, first.rule_id if first else None, tuple(dict.fromkeys(differences)), first, tuple(engine_differences))
        with self._transaction() as connection:
            connection.execute("INSERT OR REPLACE INTO workflow_comparisons(original_workflow_id,rerun_workflow_id,status,same_plan,same_inputs,same_config,same_datasets,same_code,same_environment,steps_compared_json,first_divergence_step,first_divergence_rule_id,first_divergence_json,differences_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (original_id, rerun_id, status.value, _bit(same_plan), _bit(flags["same_inputs"]), _bit(flags["same_config"]), _bit(flags["same_datasets"]), _bit(flags["same_code"]), _bit(flags["same_environment"]), _json(shared), comparison.first_divergence_step, comparison.first_divergence_rule_id, _json(first.to_dict()) if first else None, _json(comparison.differences), _now()))
        self._log("compare_workflows", workflow_id=rerun_id, status=status.value, fields={"original_workflow_id": original_id, "first_divergence_step": comparison.first_divergence_step})
        return comparison

    def get_workflow_comparison(self, original: str, rerun: str) -> WorkflowComparison:
        row = self._connection.execute("SELECT * FROM workflow_comparisons WHERE original_workflow_id=? AND rerun_workflow_id=?", (original, rerun)).fetchone()
        if row is None:
            return self.compare_workflows(original, rerun)
        first_raw = json.loads(row["first_divergence_json"]) if row["first_divergence_json"] else None
        first = FirstDivergence(**first_raw) if first_raw else None
        differences = tuple(json.loads(row["differences_json"]))
        categories = {"ENGINE_CHANGED", "ENGINE_VERSION_CHANGED", "MECHANISM_CHANGED", "DATABASE_CHANGED", "RECEPTOR_CHANGED", "GRID_CHANGED", "PROTOCOL_CHANGED"}
        return WorkflowComparison(original, rerun, ReproducibilityStatus(row["status"]), bool_or_none(row["same_plan"]), bool_or_none(row["same_inputs"]), bool_or_none(row["same_config"]), bool_or_none(row["same_datasets"]), bool_or_none(row["same_code"]), bool_or_none(row["same_environment"]), tuple(json.loads(row["steps_compared_json"])), row["first_divergence_step"], row["first_divergence_rule_id"], differences, first, tuple(item for item in differences if item in categories))

    def workflow_regressions(self, original: str, rerun: str):
        from research_os.ledger.regression import detect_regressions
        return detect_regressions(self.get_workflow_comparison(original, rerun))

    def rerun_workflow(self, workflow_id: str, runner: Any | None = None, *, output_root: str | Path | None = None, environment: Any | None = None) -> WorkflowRerunResult:
        from research_os.bundles import ResearchBundle
        from research_os.datasets import DatasetManifest
        from research_os.environment import capture_environment
        from research_os.orchestration import LabRegistry, ResearchOrchestrator, PlanStep, WorkflowPlan, default_registry

        snapshot = self._workflow_snapshot(workflow_id)
        original_bundle = Path(snapshot["bundle_path"])
        original_verification = verify_bundle(original_bundle)
        if original_verification.status == BundleVerificationStatus.FAIL:
            raise LedgerIntegrityError(f"cannot rerun invalid workflow bundle: {workflow_id}")
        manifest = snapshot["manifest"]
        plan_steps: list[PlanStep] = []
        for step in snapshot["workflow"].steps:
            payload = manifest.get("steps", {}).get(step.step_id, {}) if isinstance(manifest.get("steps"), Mapping) else {}
            plan_steps.append(PlanStep(step.step_id, str(payload.get("lab", "")), dict(payload.get("inputs", {})), str(payload.get("experiment", "default")), tuple(payload.get("requires", step.requires)), tuple(payload.get("consumed_evidence_ids", ()))))
        new_plan = WorkflowPlan(tuple(plan_steps), plan_id=f"PLAN-{uuid.uuid4().hex[:12].upper()}")
        executor = runner or ResearchOrchestrator(default_registry())
        new_plan_run = executor.run(new_plan) if hasattr(executor, "run") else executor(new_plan)
        if environment is None:
            environment = capture_environment()
        raw_datasets = _load(original_bundle / "datasets" / "manifests.json", [])
        dataset_manifests = []
        for item in raw_datasets if isinstance(raw_datasets, list) else ():
            try:
                dataset_manifests.append(DatasetManifest.from_mapping(item))
            except (TypeError, ValueError, KeyError):
                dataset_manifests.append(item)
        old_by_step = {step.step_id: step for step in snapshot["workflow"].steps}
        evidence_id_map: dict[str, str] = {}
        old_step_payloads = manifest.get("steps", {}) if isinstance(manifest.get("steps"), Mapping) else {}
        for step_id, old_payload in old_step_payloads.items():
            new_record = getattr(new_plan_run, "steps", {}).get(step_id)
            if not isinstance(old_payload, Mapping) or new_record is None:
                continue
            old_ids = _ids(old_payload.get("produced_evidence_ids"))
            new_ids = _ids(getattr(new_record, "produced_evidence_ids", ()))
            evidence_id_map.update(zip(old_ids, new_ids))
        for record in getattr(new_plan_run, "steps", {}).values():
            available_evidence_ids = {evidence.evidence_id for child in getattr(new_plan_run, "runs", {}).values() for evidence in child.evidence}
            record.consumed_evidence_ids = tuple(mapped for value in record.consumed_evidence_ids for mapped in (evidence_id_map.get(value, value),) if mapped in available_evidence_ids)
        for step_id, child in getattr(new_plan_run, "runs", {}).items():
            old = old_by_step.get(step_id)
            if old and old.run_id:
                object.__setattr__(child, "lineage", RunLineage(parent_run_id=old.run_id, rerun_of=old.run_id, derived_from=(old.run_id,)))
            for dataset in dataset_manifests:
                child.attach_dataset(dataset)
            child.attach_environment(environment)
            if child.lifecycle.value in {"COMPLETED", "FAILED", "INDETERMINATE"}:
                child.seal()
        destination = Path(output_root) if output_root is not None else self.root / "bundles"
        new_bundle = ResearchBundle.create(new_plan_run, destination, environment=environment, dataset_manifests=dataset_manifests)
        self.register_run(new_bundle, rerun_of=workflow_id)
        comparison = self.compare_workflows(workflow_id, new_plan_run.plan_id)
        self._log("rerun_workflow", workflow_id=new_plan_run.plan_id, status=comparison.status.value, fields={"rerun_of": workflow_id, "bundle_path": new_bundle.root})
        return WorkflowRerunResult(new_plan_run, new_bundle, comparison)

    def verify_ledger(self) -> LedgerVerificationResult:
        gates: list[LedgerGate] = []
        with self._lock:
            version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
            gates.append(LedgerGate("LEDGER-SCHEMA-001", "PASS" if version == SCHEMA_VERSION else "FAIL", "ledger schema version is supported" if version == SCHEMA_VERSION else f"unsupported schema version: {version}"))
            rows = self._connection.execute("SELECT * FROM runs ORDER BY run_id").fetchall()
            duplicate_ids = [row[0] for row in self._connection.execute("SELECT run_id FROM runs GROUP BY run_id HAVING COUNT(*)>1")]
        bundle_failures: list[dict[str, Any]] = []
        bundle_indeterminate: list[str] = []
        artifact_failures: list[dict[str, Any]] = []
        for row in rows:
            path = Path(row["bundle_path"])
            if not path.is_dir():
                bundle_failures.append({"run_id": row["run_id"], "reason": "bundle path is missing"})
                continue
            result = verify_bundle(path)
            artifact_gate = next((gate for gate in result.gates if gate.rule_id == "BUNDLE-ARTIFACT-001"), None)
            if artifact_gate is not None and artifact_gate.status == BundleVerificationStatus.FAIL:
                artifact_failures.append({"run_id": row["run_id"], "reason": artifact_gate.reason, "diagnostics": artifact_gate.diagnostics or {}})
            if result.status == BundleVerificationStatus.FAIL or result.bundle_hash != row["bundle_hash"]:
                bundle_failures.append({"run_id": row["run_id"], "reason": "bundle verification failed", "status": result.status.value})
            elif result.status == BundleVerificationStatus.INDETERMINATE:
                bundle_indeterminate.append(row["run_id"])
        gates.append(LedgerGate("LEDGER-RUN-001", "FAIL" if duplicate_ids else "PASS", "run IDs are unique" if not duplicate_ids else "duplicate run IDs exist", {"duplicates": duplicate_ids}))
        gates.append(LedgerGate("LEDGER-BUNDLE-001", "FAIL" if bundle_failures else "INDETERMINATE" if bundle_indeterminate else "PASS", "indexed bundles verify" if not bundle_failures and not bundle_indeterminate else "some indexed bundles need attention", {"failures": bundle_failures, "indeterminate": bundle_indeterminate}))
        cycle = self._find_cycle()
        missing_refs = self._missing_lineage_refs()
        gates.append(LedgerGate("LEDGER-LINEAGE-001", "FAIL" if cycle or missing_refs else "PASS", "lineage references and cycles are valid" if not cycle and not missing_refs else "lineage contains a cycle or missing reference", {"cycle": cycle, "missing": missing_refs}))
        claim_missing = self._claim_reference_problems()
        gates.append(LedgerGate("LEDGER-CLAIM-001", "FAIL" if claim_missing else "PASS", "claim and evidence references are valid" if not claim_missing else "claims reference missing evidence or runs", {"missing": claim_missing}))
        dataset_problems = self._dataset_reference_problems()
        gates.append(LedgerGate("LEDGER-DATASET-001", "INDETERMINATE" if dataset_problems else "PASS", "dataset references are available" if not dataset_problems else "some external dataset artifacts cannot be revalidated", {"indeterminate": dataset_problems}))
        gates.append(LedgerGate("LEDGER-ARTIFACT-001", "FAIL" if artifact_failures else "PASS", "bundle artifact indexes verify" if not artifact_failures else "artifact verification failed", {"failures": artifact_failures}))
        status = "FAIL" if any(gate.status == "FAIL" for gate in gates) else "INDETERMINATE" if any(gate.status == "INDETERMINATE" for gate in gates) else "PASS"
        result = LedgerVerificationResult(status, tuple(gates))
        self._log("verify_ledger", status=status, fields={"gate_count": len(gates)})
        return result

    def _find_cycle(self) -> list[str]:
        edges = self._edge_rows()
        adjacency: dict[str, list[str]] = {}
        for edge in edges:
            adjacency.setdefault(edge.downstream_run_id, []).append(edge.upstream_run_id)
        visited: set[str] = set()
        active: list[str] = []

        def visit(node: str) -> list[str] | None:
            if node in active:
                return active[active.index(node):] + [node]
            if node in visited:
                return None
            active.append(node)
            for neighbor in adjacency.get(node, ()):
                found = visit(neighbor)
                if found:
                    return found
            active.pop()
            visited.add(node)
            return None

        for node in adjacency:
            found = visit(node)
            if found:
                return found
        return []

    def _missing_lineage_refs(self) -> list[dict[str, str]]:
        result = [{"downstream": edge.downstream_run_id, "upstream": edge.upstream_run_id} for edge in self._edge_rows() if not self._run_exists(self._connection, edge.downstream_run_id) or not self._run_exists(self._connection, edge.upstream_run_id)]
        rows = self._connection.execute("SELECT run_id,parent_run_id,rerun_of,supersedes FROM runs").fetchall()
        for row in rows:
            for field in ("parent_run_id", "rerun_of", "supersedes"):
                if row[field] and not self._run_exists(self._connection, row[field]):
                    result.append({"downstream": row["run_id"], "upstream": row[field], "field": field})
        return result

    def _claim_reference_problems(self) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for row in self._connection.execute("SELECT run_id,claim_id,evidence_ids_json FROM run_claims"):
            for evidence_id in json.loads(row["evidence_ids_json"]):
                if not self._evidence_exists(evidence_id):
                    result.append({"claim_id": row["claim_id"], "evidence_id": evidence_id})
            if not self._run_exists(self._connection, row["run_id"]):
                result.append({"claim_id": row["claim_id"], "run_id": row["run_id"]})
        return result

    def _dataset_reference_problems(self) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for row in self._connection.execute("SELECT run_id,dataset_id,artifact_path,sha256 FROM run_datasets"):
            if row["artifact_path"]:
                path = Path(row["artifact_path"])
                if not path.is_file():
                    result.append({"run_id": row["run_id"], "dataset_id": row["dataset_id"], "reason": "artifact is missing"})
        return result


def _optional_equal(left: Any, right: Any) -> bool | None:
    if left is None or right is None or left == "" or right == "":
        return None
    return left == right


def _plan_signature(manifest: Mapping[str, Any], workflow: WorkflowExecution) -> list[Any]:
    raw_steps = manifest.get("steps", {}) if isinstance(manifest, Mapping) else {}
    result: list[Any] = []
    for step in workflow.steps:
        payload = raw_steps.get(step.step_id, {}) if isinstance(raw_steps, Mapping) else {}
        result.append((step.step_id, payload.get("lab"), payload.get("experiment"), step.requires))
    return result


def _comparison_status(workflow_left: WorkflowExecution, workflow_right: WorkflowExecution, same_plan: bool | None, flags: Mapping[str, bool | None], first: FirstDivergence | None) -> ReproducibilityStatus:
    if first or same_plan is False or any(value is False for value in (flags["same_inputs"], flags["same_config"], flags["same_datasets"])):
        return ReproducibilityStatus.DIVERGED
    if flags["same_environment"] is False and all(value is not False for key, value in flags.items() if key != "same_environment"):
        return ReproducibilityStatus.REPRODUCED_WITH_ENVIRONMENT_CHANGE
    if any(value is None for value in flags.values()) or same_plan is None:
        return ReproducibilityStatus.NOT_COMPARABLE
    if workflow_left.status == "INDETERMINATE" or workflow_right.status == "INDETERMINATE":
        return ReproducibilityStatus.INDETERMINATE
    return ReproducibilityStatus.REPRODUCED


def _bit(value: bool | None) -> int | None:
    return None if value is None else int(value)


def bool_or_none(value: Any) -> bool | None:
    return None if value is None else bool(value)


def _engine_provenance_differences(left_items: Sequence[Mapping[str, Any]], right_items: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    left = {str(item.get("engine_id")): item for item in left_items if item.get("engine_id")}
    right = {str(item.get("engine_id")): item for item in right_items if item.get("engine_id")}
    result: list[str] = []
    if set(left) != set(right):
        result.append("ENGINE_CHANGED")
    for engine_id in sorted(set(left) & set(right)):
        a, b = left[engine_id], right[engine_id]
        if (a.get("version") or a.get("library_version")) != (b.get("version") or b.get("library_version")):
            result.append("ENGINE_VERSION_CHANGED")
        if a.get("configuration_hash") is not None and b.get("configuration_hash") is not None and a.get("configuration_hash") != b.get("configuration_hash"):
            result.append("PROTOCOL_CHANGED")
        for keys, category in ((("mechanism_sha256", "mechanism_hash"), "MECHANISM_CHANGED"), (("database_sha256", "database_hash"), "DATABASE_CHANGED"), (("receptor_sha256", "receptor_hash"), "RECEPTOR_CHANGED"), (("grid_hash",), "GRID_CHANGED"), (("protocol_id",), "PROTOCOL_CHANGED")):
            av = _engine_field(a, *keys)
            bv = _engine_field(b, *keys)
            if av is not None and bv is not None and av != bv:
                result.append(category)
    return tuple(dict.fromkeys(result))


def rebuild_index(bundle_root: str | Path, registry: RunRegistry | None = None) -> RebuildReport:
    owned = registry is None
    current = registry or RunRegistry(Path(bundle_root).parent)
    try:
        return current.rebuild_index(bundle_root)
    finally:
        if owned:
            current.close()


def verify_ledger(registry: RunRegistry | str | Path) -> LedgerVerificationResult:
    owned = not isinstance(registry, RunRegistry)
    current = registry if isinstance(registry, RunRegistry) else RunRegistry(registry)
    try:
        return current.verify_ledger()
    finally:
        if owned:
            current.close()


def register_run(registry: RunRegistry, bundle: Any, **kwargs: Any) -> LedgerRegistration:
    return registry.register_run(bundle, **kwargs)


def get_run(registry: RunRegistry, run_id: str) -> RunIndexRecord:
    return registry.get_run(run_id)


def list_runs(registry: RunRegistry, **kwargs: Any) -> list[RunIndexRecord]:
    return registry.list_runs(**kwargs)


def search_runs(registry: RunRegistry, **kwargs: Any) -> list[RunIndexRecord]:
    return registry.search_runs(**kwargs)


def verify_run(registry: RunRegistry, run_id: str):
    return registry.verify_run(run_id)


def remove_index_entry(registry: RunRegistry, run_id: str) -> LedgerRegistration:
    return registry.remove_index_entry(run_id)


def runs_using_engine(registry: RunRegistry, engine_id: str) -> list[RunIndexRecord]:
    return registry.runs_using_engine(engine_id)


def runs_using_engine_version(registry: RunRegistry, engine_id: str, version: str) -> list[RunIndexRecord]:
    return registry.runs_using_engine_version(engine_id, version)


def runs_using_mechanism(registry: RunRegistry, mechanism_hash: str) -> list[RunIndexRecord]:
    return registry.runs_using_mechanism(mechanism_hash)


def runs_using_database(registry: RunRegistry, database_hash: str) -> list[RunIndexRecord]:
    return registry.runs_using_database(database_hash)


def runs_using_receptor(registry: RunRegistry, receptor_hash: str) -> list[RunIndexRecord]:
    return registry.runs_using_receptor(receptor_hash)


def runs_using_grid(registry: RunRegistry, grid_hash: str) -> list[RunIndexRecord]:
    return registry.runs_using_grid(grid_hash)


def trace_engine_run(registry: RunRegistry, run_id: str, engine_id: str | None = None) -> dict[str, Any]:
    return registry.trace_engine_run(run_id, engine_id)
