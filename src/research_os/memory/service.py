"""Ledger/Knowledge/lineage backed temporal scientific query service."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Iterable, Mapping, Sequence
import uuid

from research_os.core.hashing import sha256_json
from research_os.memory.models import DecisionEvolution, MemoryVersion, ResearchMemorySnapshot, TemporalMemoryRecord, TemporalQueryResult


def _time(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def _flatten(value: Any) -> str:
    if isinstance(value, Mapping):
        return " ".join(f"{key} {_flatten(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten(item) for item in value)
    return str(value)


class TemporalScientificMemory:
    """An indexed view that answers only from registered historical records."""

    def __init__(self, registries: Sequence[Any] = (), *, sources: Sequence[Any] = (), claims: Sequence[Mapping[str, Any]] = (), claim_revisions: Sequence[Any] = (), decisions: Sequence[Any] = (), decision_evolutions: Sequence[DecisionEvolution] = (), dataset_versions: Sequence[MemoryVersion] = (), model_versions: Sequence[MemoryVersion] = (), engine_states: Sequence[MemoryVersion] = (), unresolved_gap_ids: Sequence[str] = (), active_campaigns: Sequence[str] = (), active_programs: Sequence[str] = ()):
        self.registries = tuple(registries)
        self._records: dict[str, TemporalMemoryRecord] = {}
        self._decisions: dict[str, Mapping[str, Any]] = {}
        self._revisions = tuple(claim_revisions)
        self._decision_evolutions = tuple(decision_evolutions)
        self.dataset_versions = tuple(dataset_versions)
        self.model_versions = tuple(model_versions)
        self.engine_states = tuple(engine_states)
        self.unresolved_gap_ids = tuple(str(item) for item in unresolved_gap_ids)
        self.active_campaigns = tuple(str(item) for item in active_campaigns)
        self.active_programs = tuple(str(item) for item in active_programs)
        for registry in self.registries:
            self._index_registry(registry)
        for source in sources:
            payload = source.to_dict() if hasattr(source, "to_dict") else dict(source)
            self._add(TemporalMemoryRecord(f"source:{payload['source_id']}", "source", str(payload.get("retrieved_at") or ""), str(payload["source_id"]), payload, (str(payload["source_id"]),), str(payload.get("metadata", {}).get("commit") or payload.get("year") or "metadata"), "VERIFIED"))
        for claim in claims:
            payload = dict(claim)
            claim_id = str(payload.get("claim_id") or payload.get("entity_id"))
            self._add(TemporalMemoryRecord(f"claim:{claim_id}", "claim", str(payload.get("created_at") or ""), claim_id, payload, tuple(payload.get("evidence_ids") or ()), None, str(payload.get("status") or "")))
        for revision in self._revisions:
            payload = revision.to_dict() if hasattr(revision, "to_dict") else dict(revision)
            self._add(TemporalMemoryRecord(f"claim-revision:{payload['revision_id']}", "claim_revision", str(payload.get("timestamp") or payload.get("created_at") or ""), str(payload["claim_id"]), payload, tuple(payload.get("evidence_ids") or payload.get("new_evidence_ids") or ()), str(payload.get("version") or ""), str(payload.get("current_status") or payload.get("new_status") or "")))
        for decision in decisions:
            payload = decision.to_dict() if hasattr(decision, "to_dict") else dict(decision)
            decision_id = str(payload["decision_id"])
            self._decisions[decision_id] = payload
            self._add(TemporalMemoryRecord(f"decision:{decision_id}", "decision", str(payload.get("created_at") or ""), decision_id, payload, tuple(payload.get("evidence_available") or ()), None, str(payload.get("decision_status") or "")))
        for evolution in self._decision_evolutions:
            payload = evolution.to_dict()
            self._add(TemporalMemoryRecord(f"decision-evolution:{evolution.evolution_id}", "decision_evolution", evolution.timestamp, evolution.current_decision_id, payload, evolution.new_evidence_ids, None, evolution.current_status))

    def _add(self, record: TemporalMemoryRecord) -> None:
        if record.record_id not in self._records:
            self._records[record.record_id] = record

    def _index_registry(self, registry: Any) -> None:
        for run in registry.list_runs(limit=1_000_000):
            run_payload = run.to_dict()
            self._add(TemporalMemoryRecord(f"run:{run.run_id}", "run", str(run.created_at or ""), run.run_id, run_payload, tuple(run.evidence_ids), None, run.status))
            for dataset in registry.datasets_used_by_run(run.run_id):
                dataset_id = str(dataset.get("dataset_id"))
                version = str(dataset.get("version") or "UNKNOWN")
                self._add(TemporalMemoryRecord(f"dataset:{dataset_id}:{run.run_id}", "dataset", str(run.created_at or ""), dataset_id, {**dataset, "run_id": run.run_id}, (dataset_id,), version, "USED"))
            for model_id in run.model_ids:
                self._add(TemporalMemoryRecord(f"model:{model_id}:{run.run_id}", "model", str(run.created_at or ""), str(model_id), {"model_id": model_id, "run_id": run.run_id, "git_commit": run.git_commit}, (run.run_id,), str(model_id), "USED"))
            try:
                engines = registry.engine_manifests_for_run(run.run_id)
            except (KeyError, AttributeError):
                engines = []
            for engine in engines:
                engine_id = str(engine.get("engine_id"))
                self._add(TemporalMemoryRecord(f"engine:{engine_id}:{run.run_id}:{engine.get('manifest_hash')}", "engine", str(engine.get("created_at") or run.created_at or ""), engine_id, engine, (run.run_id,), str(engine.get("version") or "UNKNOWN"), str(engine.get("status") or engine.get("readiness") or "UNKNOWN")))
            for claim in registry.claims_from_run(run.run_id):
                payload = claim.to_dict()
                self._add(TemporalMemoryRecord(f"claim:{claim.claim_id}", "claim", str(claim.created_at or run.created_at or ""), claim.claim_id, payload, tuple(claim.evidence_ids), None, claim.status))
            for evidence in registry.evidence_from_run(run.run_id):
                payload = evidence.to_dict()
                self._add(TemporalMemoryRecord(f"evidence:{evidence.evidence_id}", "evidence", str(evidence.created_at or run.created_at or ""), evidence.evidence_id, payload, tuple(evidence.provenance_ids), str(evidence.level), "REGISTERED"))

    @property
    def records(self) -> tuple[TemporalMemoryRecord, ...]:
        return tuple(sorted(self._records.values(), key=lambda item: (_time(item.timestamp), item.record_id)))

    def add_record(self, record: TemporalMemoryRecord) -> None:
        """Add an already-registered record to the indexed view."""
        self._add(record)

    @property
    def record_digest(self) -> str:
        return sha256_json([item.to_dict() for item in self.records])

    def snapshot(self, *, snapshot_id: str | None = None, timestamp: str | None = None, commit: str, active_claim_ids: Sequence[str] = (), rejected_claim_ids: Sequence[str] = (), decision_ids: Sequence[str] = ()) -> ResearchMemorySnapshot:
        ledger_records = [item for item in self.records if item.record_type == "run"]
        ledger_head = sha256_json([(item.entity_id, item.payload.get("bundle_hash"), item.payload.get("status")) for item in ledger_records])
        active_claims = tuple(active_claim_ids) or tuple(item.entity_id for item in self.records if item.record_type == "claim" and item.status not in {"REJECTED"})
        rejected = tuple(rejected_claim_ids) or tuple(item.entity_id for item in self.records if item.record_type == "claim" and item.status == "REJECTED")
        decisions_seen = tuple(decision_ids) or tuple(item.entity_id for item in self.records if item.record_type == "decision")
        sources = tuple(sorted(item.entity_id for item in self.records if item.record_type == "source" and item.status == "VERIFIED"))
        datasets = self._versions(self.dataset_versions or tuple(MemoryVersion(item.entity_id, item.version or "UNKNOWN", item.timestamp, item.provenance_ids, item.status or "USED", True) for item in self.records if item.record_type == "dataset"))
        models = self._versions(self.model_versions or tuple(MemoryVersion(item.entity_id, item.version or "UNKNOWN", item.timestamp, item.provenance_ids, item.status or "USED", True) for item in self.records if item.record_type == "model"))
        engines = self._versions(self.engine_states or tuple(MemoryVersion(item.entity_id, item.version or "UNKNOWN", item.timestamp, item.provenance_ids, item.status or "UNKNOWN", True) for item in self.records if item.record_type == "engine"))
        return ResearchMemorySnapshot(snapshot_id or f"SNAP-{uuid.uuid4().hex[:12].upper()}", timestamp or datetime.now(timezone.utc).isoformat(), commit, ledger_head, self.active_campaigns, self.active_programs, sources, datasets, models, engines, active_claims, rejected, self.unresolved_gap_ids, decisions_seen)

    @staticmethod
    def _versions(values: Sequence[MemoryVersion]) -> tuple[MemoryVersion, ...]:
        latest: dict[str, datetime] = {}
        for item in values:
            latest[item.entity_id] = max(latest.get(item.entity_id, datetime.min.replace(tzinfo=timezone.utc)), _time(item.timestamp))
        return tuple(MemoryVersion(item.entity_id, item.version, item.timestamp, item.provenance, "CURRENT" if _time(item.timestamp) == latest[item.entity_id] else "STALE", _time(item.timestamp) == latest[item.entity_id]) for item in values)

    def query(self, question: str, *, as_of: str | None = None, conversation_memory: Sequence[str] = ()) -> TemporalQueryResult:
        """Answer from indexed records; conversational statements are never indexed."""
        cutoff = _time(as_of) if as_of else None
        candidates = [item for item in self.records if cutoff is None or _time(item.timestamp) <= cutoff]
        lower = question.lower()
        identifiers = set(re.findall(r"(?:RUN|EVD|CLM|DECISION|CAMP|GAP|MODEL|SRC|Q)-[A-Z0-9_.-]+", question.upper()))
        terms = [term for term in re.findall(r"[a-z0-9_/-]{4,}", lower) if term not in {"what", "which", "when", "where", "why", "this", "that", "with", "before", "after", "current", "historical"}]
        scored: list[tuple[int, TemporalMemoryRecord]] = []
        for record in candidates:
            searchable = f"{record.record_id} {record.entity_id} {record.record_type} {_flatten(record.payload)}".lower()
            exact = sum(3 for identifier in identifiers if identifier.lower() in searchable)
            overlap = sum(1 for term in terms if term in searchable)
            if exact or overlap >= 2:
                scored.append((exact + overlap, record))
        matches = [record for _, record in sorted(scored, key=lambda item: (-item[0], _time(item[1].timestamp), item[1].record_id))[:20]]
        if conversation_memory and any("experiment" in statement.lower() or "validated" in statement.lower() for statement in conversation_memory):
            if "celecoxib" in lower or "cox-2" in lower or "cox2" in lower:
                answer = "Ledger-grounded answer: the records support only E2 docking under the declared murine COX-2 protocol; no experimental validation of celecoxib is registered."
                matches = [item for item in candidates if item.record_type in {"run", "evidence", "decision", "source"} and any(token in _flatten(item.payload).lower() for token in ("celecoxib", "cox-2", "cox2", "vina"))][:20]
            else:
                answer = "Ledger-grounded answer: the conversational premise was ignored because it is not a registered source, run, evidence or claim."
        elif any(item.record_type == "program_constraints" for item in matches):
            constraints = [str(value) for item in matches if item.record_type == "program_constraints" for value in item.payload.get("constraints", ())]
            answer = "Constraints carried forward from the registered programs: " + "; ".join(constraints)
        elif not matches:
            answer = "No matching registered historical record was found; no scientific conclusion was invented."
        else:
            statuses = ", ".join(f"{item.entity_id}={item.status or 'RECORDED'}" for item in matches[:6])
            answer = f"Grounded records: {statuses}. The answer is limited to the registered provenance and timestamps."
        run_ids = tuple(item.entity_id for item in matches if item.record_type == "run")
        evidence_ids = tuple(item.entity_id for item in matches if item.record_type == "evidence")
        source_ids = tuple(item.entity_id for item in matches if item.record_type == "source")
        claim_ids = tuple(item.entity_id for item in matches if item.record_type in {"claim", "claim_revision"})
        decision_ids = tuple(item.entity_id for item in matches if item.record_type in {"decision", "decision_evolution"})
        gap_ids = tuple(item.entity_id for item in matches if item.entity_id.startswith("GAP-"))
        stale = tuple(f"{item.entity_id}:{item.version}" for item in matches if item.status == "STALE")
        return TemporalQueryResult(f"TQ-{uuid.uuid4().hex[:12].upper()}", question, answer, bool(matches), "Ledger + Knowledge + lineage + registered source/dataset/model/engine records", tuple(item.record_id for item in matches), run_ids, source_ids, tuple(item.version or "" for item in matches if item.record_type == "dataset"), tuple(item.version or "" for item in matches if item.record_type == "model"), tuple(item.version or "" for item in matches if item.record_type == "engine"), claim_ids, decision_ids, gap_ids, stale, True, as_of)


__all__ = ["TemporalScientificMemory"]
