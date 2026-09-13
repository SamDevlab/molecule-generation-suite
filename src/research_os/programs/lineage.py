"""Durable Research Program lineage over declarative Campaign executions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping
import uuid

import yaml

from research_os.campaigns.declarative import (
    CampaignProtocolError,
    DeclarativeCampaignRunner,
    _canonical_json,
    _safe_protocol_ref,
    load_campaign_protocol,
    verify_campaign_execution,
)
from research_os.core.hashing import sha256_file, sha256_json
from research_os.programs.models import KnowledgeGainAssessment, ResearchProgram, ResearchProgramStatus
from research_os.programs.runner import ResearchProgramController
from research_os.programs.store import ResearchProgramStore


PROGRAM_PROTOCOL_ID = "research-os.program.protocol.v1"
PROGRAM_SCHEMA_VERSION = "research-os.program.v1"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TERMINAL = {"COMPLETED", "FAILED", "BLOCKED", "SKIPPED_DEPENDENCY"}


class ProgramProtocolError(ValueError):
    def __init__(self, message: str, *, first_loss: str = "PROGRAM_PROTOCOL_INVALID") -> None:
        super().__init__(message)
        self.first_loss = first_loss


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _s(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProgramProtocolError(f"{name} must be a non-empty string")
    return value.strip()


def _i(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ProgramProtocolError(f"{name} must be an integer >= {minimum}")
    return value


def _m(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProgramProtocolError(f"{name} must be a mapping")
    return value


def _strict(value: Mapping[str, Any], allowed: set[str], required: set[str], name: str) -> None:
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        raise ProgramProtocolError(f"{name} has unknown keys: {', '.join(unknown)}")
    if missing:
        raise ProgramProtocolError(f"{name} is missing required keys: {', '.join(missing)}")


@dataclass(frozen=True)
class ProgramCampaignRef:
    local_id: str
    protocol_path: str
    depends_on: tuple[str, ...] = ()
    role: str = "COMPLEMENTARY"
    campaign_protocol_id: str | None = None

    def __post_init__(self) -> None:
        if not _SAFE_ID.fullmatch(self.local_id):
            raise ProgramProtocolError("campaign local_id must be a safe identifier")
        if not self.protocol_path.strip():
            raise ProgramProtocolError("campaign protocol_path is required")
        if any(not _SAFE_ID.fullmatch(item) for item in self.depends_on):
            raise ProgramProtocolError("campaign dependencies must be safe identifiers")
        if self.local_id in self.depends_on:
            raise ProgramProtocolError("campaign cannot depend on itself", first_loss="PROGRAM_DEPENDENCY_CYCLE")
        if self.role not in {"PRIMARY", "COMPLEMENTARY", "EXPLORATORY"}:
            raise ProgramProtocolError("campaign role must be PRIMARY, COMPLEMENTARY or EXPLORATORY")
        if self.campaign_protocol_id is not None and not self.campaign_protocol_id.strip():
            raise ProgramProtocolError("campaign_protocol_id cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        payload = {"local_id": self.local_id, "protocol_path": self.protocol_path, "depends_on": list(self.depends_on), "role": self.role}
        if self.campaign_protocol_id is not None:
            payload["campaign_protocol_id"] = self.campaign_protocol_id
        return payload


@dataclass(frozen=True)
class ResearchProgramProtocol:
    program_id: str
    title: str
    domain: str
    objective: str
    motivation: str
    initial_problem: str
    research_questions: tuple[Mapping[str, Any], ...]
    campaigns: tuple[ProgramCampaignRef, ...]
    max_campaigns: int
    max_runs: int
    max_failures: int
    failure_policy: str
    retry_count: int
    evidence_target: str | None
    synthesis: Mapping[str, Any]
    source_path: Path
    schema_version: str = PROGRAM_SCHEMA_VERSION
    mode: str = "STATIC_PREDECLARED"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], *, source_path: str | Path) -> "ResearchProgramProtocol":
        _strict(raw, {"schema_version", "program", "limits", "execution", "campaigns", "synthesis"}, {"program", "limits", "execution", "campaigns", "synthesis"}, "program protocol")
        schema = str(raw.get("schema_version", PROGRAM_SCHEMA_VERSION))
        if schema != PROGRAM_SCHEMA_VERSION:
            raise ProgramProtocolError(f"unsupported program schema: {schema}")
        program = _m(raw["program"], "program")
        _strict(program, {"program_id", "title", "domain", "objective", "motivation", "initial_problem", "research_questions", "evidence_target"}, {"program_id", "title", "domain", "objective", "motivation", "initial_problem"}, "program")
        questions_raw = program.get("research_questions", [])
        if not isinstance(questions_raw, list):
            raise ProgramProtocolError("program.research_questions must be a list")
        questions = tuple(dict(_m(item, "research_questions[]")) for item in questions_raw)
        for item in questions:
            if not str(item.get("gap_it_attempts_to_resolve") or "").strip():
                raise ProgramProtocolError("each research question must declare gap_it_attempts_to_resolve")
        limits = _m(raw["limits"], "limits")
        _strict(limits, {"max_campaigns", "max_runs", "max_failures"}, {"max_campaigns", "max_runs", "max_failures"}, "limits")
        execution = _m(raw["execution"], "execution")
        _strict(execution, {"mode", "retry_count", "failure_policy"}, {"mode", "retry_count", "failure_policy"}, "execution")
        mode = _s(execution["mode"], "execution.mode")
        if mode != "STATIC_PREDECLARED":
            raise ProgramProtocolError("program v1 requires STATIC_PREDECLARED mode")
        retry_count = _i(execution["retry_count"], "execution.retry_count")
        if retry_count != 0:
            raise ProgramProtocolError("program v1 does not permit implicit retries")
        failure_policy = _s(execution["failure_policy"], "execution.failure_policy")
        if failure_policy not in {"continue_independent", "stop_on_failure"}:
            raise ProgramProtocolError("unsupported program failure_policy")
        campaigns_raw = raw["campaigns"]
        if not isinstance(campaigns_raw, list) or not campaigns_raw:
            raise ProgramProtocolError("campaigns must be a non-empty list")
        campaigns: list[ProgramCampaignRef] = []
        for index, item in enumerate(campaigns_raw):
            value = _m(item, f"campaigns[{index}]")
            _strict(value, {"local_id", "protocol_path", "depends_on", "role", "campaign_protocol_id"}, {"local_id", "protocol_path"}, f"campaigns[{index}]")
            dependencies = value.get("depends_on", [])
            if isinstance(dependencies, str) or not isinstance(dependencies, (list, tuple)):
                raise ProgramProtocolError(f"campaigns[{index}].depends_on must be a list")
            protocol_ref = _s(value["protocol_path"], f"campaigns[{index}].protocol_path")
            if Path(protocol_ref).is_absolute():
                raise ProgramProtocolError("campaign protocol paths must be relative to the Program Protocol", first_loss="PROGRAM_PROTOCOL_INVALID")
            if len(set(dependencies)) != len(dependencies):
                raise ProgramProtocolError(f"campaigns[{index}].depends_on contains duplicates", first_loss="PROGRAM_PROTOCOL_INVALID")
            campaigns.append(ProgramCampaignRef(_s(value["local_id"], f"campaigns[{index}].local_id"), protocol_ref, tuple(str(item) for item in dependencies), str(value.get("role", "COMPLEMENTARY")), str(value["campaign_protocol_id"]) if value.get("campaign_protocol_id") is not None else None))
        ids = [item.local_id for item in campaigns]
        if len(ids) != len(set(ids)):
            raise ProgramProtocolError("campaign local_ids must be unique")
        synthesis = _m(raw["synthesis"], "synthesis")
        _strict(synthesis, {"mode", "primary_campaigns", "complementary_campaigns", "knowledge_gain_summary"}, {"mode", "primary_campaigns", "complementary_campaigns"}, "synthesis")
        synthesis_payload = dict(synthesis)
        synthesis_payload["primary_campaigns"] = list(synthesis_payload.get("primary_campaigns", []))
        synthesis_payload["complementary_campaigns"] = list(synthesis_payload.get("complementary_campaigns", []))
        if synthesis_payload.get("mode") not in {"STRUCTURAL_ONLY", "DESCRIPTIVE_ONLY"}:
            raise ProgramProtocolError("synthesis.mode must be STRUCTURAL_ONLY or DESCRIPTIVE_ONLY")
        if any(item not in ids for item in synthesis_payload["primary_campaigns"] + synthesis_payload["complementary_campaigns"]):
            raise ProgramProtocolError("synthesis references an undeclared campaign")
        return cls(_s(program["program_id"], "program.program_id"), _s(program["title"], "program.title"), _s(program["domain"], "program.domain"), _s(program["objective"], "program.objective"), _s(program["motivation"], "program.motivation"), _s(program["initial_problem"], "program.initial_problem"), questions, tuple(campaigns), _i(limits["max_campaigns"], "limits.max_campaigns", 1), _i(limits["max_runs"], "limits.max_runs", 1), _i(limits["max_failures"], "limits.max_failures"), failure_policy, retry_count, str(program["evidence_target"]) if program.get("evidence_target") is not None else None, synthesis_payload, Path(source_path).resolve(), schema, mode)

    def scientific_payload(self, resolved_campaigns: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
        campaigns = []
        for item in sorted(self.campaigns, key=lambda value: value.local_id):
            resolved = resolved_campaigns.get(item.local_id, {}) if resolved_campaigns else {}
            campaigns.append({"local_id": item.local_id, "campaign_protocol_id": resolved.get("campaign_protocol_id", item.campaign_protocol_id), "campaign_protocol_hash": resolved.get("campaign_protocol_hash"), "depends_on": sorted(item.depends_on), "role": item.role})
        return {
            "protocol": PROGRAM_PROTOCOL_ID,
            "schema_version": self.schema_version,
            "program": {"title": self.title, "domain": self.domain, "objective": self.objective, "motivation": self.motivation, "initial_problem": self.initial_problem, "research_questions": [dict(item) for item in self.research_questions], "evidence_target": self.evidence_target},
            "limits": {"max_campaigns": self.max_campaigns, "max_runs": self.max_runs, "max_failures": self.max_failures},
            "execution": {"mode": self.mode, "retry_count": self.retry_count, "failure_policy": self.failure_policy},
            "campaigns": campaigns,
            "synthesis": dict(self.synthesis),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "program": {"program_id": self.program_id, "title": self.title, "domain": self.domain, "objective": self.objective, "motivation": self.motivation, "initial_problem": self.initial_problem, "research_questions": [dict(item) for item in self.research_questions], "evidence_target": self.evidence_target},
            "limits": {"max_campaigns": self.max_campaigns, "max_runs": self.max_runs, "max_failures": self.max_failures},
            "execution": {"mode": self.mode, "retry_count": self.retry_count, "failure_policy": self.failure_policy},
            "campaigns": [item.to_dict() for item in self.campaigns],
            "synthesis": dict(self.synthesis),
        }


def load_program_protocol(path: str | Path) -> ResearchProgramProtocol:
    source = Path(path).resolve()
    return ResearchProgramProtocol.from_mapping(_canonical_json(source), source_path=source)


def _topological_order(campaigns: tuple[ProgramCampaignRef, ...]) -> tuple[str, ...]:
    known = {item.local_id for item in campaigns}
    remaining = {item.local_id: set(item.depends_on) for item in campaigns}
    for item in campaigns:
        if any(dep not in known for dep in item.depends_on):
            raise ProgramProtocolError(f"missing campaign dependency for {item.local_id}", first_loss="PROGRAM_DEPENDENCY_MISSING")
    ordered: list[str] = []
    while remaining:
        ready = sorted(key for key, deps in remaining.items() if not deps)
        if not ready:
            raise ProgramProtocolError("campaign dependency graph contains a cycle", first_loss="PROGRAM_DEPENDENCY_CYCLE")
        ordered.extend(ready)
        for key in ready:
            remaining.pop(key)
        for deps in remaining.values():
            deps.difference_update(ready)
    return tuple(ordered)


@dataclass(frozen=True)
class ResearchProgramExecutionPlan:
    program_protocol_id: str
    program_protocol_hash: str
    campaigns: Mapping[str, Mapping[str, Any]]
    execution_order: tuple[str, ...]
    max_campaigns: int
    max_runs: int
    max_failures: int
    retry_count: int
    failure_policy: str
    synthesis: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "program_protocol_id": self.program_protocol_id,
            "program_protocol_hash": self.program_protocol_hash,
            "campaigns": [dict(self.campaigns[key]) for key in self.execution_order],
            "execution_order": list(self.execution_order),
            "max_campaigns": self.max_campaigns,
            "max_runs": self.max_runs,
            "max_failures": self.max_failures,
            "retry_count": self.retry_count,
            "failure_policy": self.failure_policy,
            "synthesis": dict(self.synthesis),
        }
        payload["plan_hash"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class ProgramVerification:
    status: str
    root: str
    first_loss: str | None
    gates: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "root": self.root, "first_loss": self.first_loss, "gates": [dict(item) for item in self.gates]}


@dataclass(frozen=True)
class ResearchProgramBundle:
    program_id: str
    bundle_id: str
    program_protocol_id: str
    program_execution_id: str
    campaign_protocol_ids: tuple[str, ...]
    campaign_execution_ids: tuple[str, ...]
    campaign_bundle_ids: tuple[str, ...]
    run_ids: tuple[str, ...]
    dataset_refs: tuple[Mapping[str, Any], ...]
    model_refs: tuple[Mapping[str, Any], ...]
    evidence_refs: tuple[Mapping[str, Any], ...]
    knowledge_gain: Mapping[str, Any]
    unresolved_uncertainties: tuple[str, ...]
    bundle_hash: str
    sealed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "research-os.program-bundle.v1",
            "program_id": self.program_id,
            "bundle_id": self.bundle_id,
            "program_protocol_id": self.program_protocol_id,
            "program_execution_id": self.program_execution_id,
            "campaign_protocol_ids": list(self.campaign_protocol_ids),
            "campaign_execution_ids": list(self.campaign_execution_ids),
            "campaign_bundle_ids": list(self.campaign_bundle_ids),
            "run_ids": list(self.run_ids),
            "dataset_refs": [dict(item) for item in self.dataset_refs],
            "model_refs": [dict(item) for item in self.model_refs],
            "evidence_refs": [dict(item) for item in self.evidence_refs],
            "knowledge_gain": dict(self.knowledge_gain),
            "unresolved_uncertainties": list(self.unresolved_uncertainties),
            "bundle_hash": self.bundle_hash,
            "sealed": self.sealed,
        }


def _first_loss(exc: Exception, fallback: str) -> str:
    return str(getattr(exc, "first_loss", None) or getattr(exc, "rule_id", None) or fallback)


class DeclarativeProgramRunner:
    """Static Program coordinator that delegates every Campaign execution."""

    def __init__(self, *, campaign_runner: DeclarativeCampaignRunner | None = None) -> None:
        self.campaign_runner = campaign_runner or DeclarativeCampaignRunner()

    def plan(self, protocol_path: str | Path) -> ResearchProgramExecutionPlan:
        protocol = load_program_protocol(protocol_path)
        if len(protocol.campaigns) > protocol.max_campaigns:
            raise ProgramProtocolError("declared campaigns exceed max_campaigns", first_loss="PROGRAM_CAMPAIGN_LIMIT_EXCEEDED")
        order = _topological_order(protocol.campaigns)
        by_id = {item.local_id: item for item in protocol.campaigns}
        resolved: dict[str, Mapping[str, Any]] = {}
        estimated_runs = 0
        for local_id in order:
            ref = by_id[local_id]
            campaign_path = _safe_protocol_ref(protocol.source_path.parent, ref.protocol_path)
            campaign_plan = self.campaign_runner.plan(campaign_path)
            if ref.campaign_protocol_id is not None and ref.campaign_protocol_id != campaign_plan.campaign_protocol_id:
                raise ProgramProtocolError(f"campaign protocol identity mismatch for {local_id}", first_loss="PROGRAM_CAMPAIGN_PROTOCOL_MISMATCH")
            estimated_runs += campaign_plan.max_runs
            resolved[local_id] = {
                "local_id": local_id,
                "campaign_protocol_id": campaign_plan.campaign_protocol_id,
                "campaign_protocol_hash": campaign_plan.campaign_protocol_hash,
                "protocol_path": str(campaign_path),
                "depends_on": list(ref.depends_on),
                "role": ref.role,
                "max_runs": campaign_plan.max_runs,
                "declared_child_count": len(campaign_plan.execution_order),
            }
        if estimated_runs > protocol.max_runs:
            raise ProgramProtocolError("declared campaign capacity exceeds program max_runs", first_loss="PROGRAM_RUN_LIMIT_EXCEEDED")
        payload = protocol.scientific_payload(resolved)
        protocol_hash = sha256_json(payload)
        return ResearchProgramExecutionPlan(f"research-os.program.protocol.v1+{protocol_hash[:16]}", protocol_hash, resolved, order, protocol.max_campaigns, protocol.max_runs, protocol.max_failures, protocol.retry_count, protocol.failure_policy, protocol.synthesis)

    def run(self, protocol_path: str | Path, output_root: str | Path) -> dict[str, Any]:
        plan = self.plan(protocol_path)
        protocol = load_program_protocol(protocol_path)
        root = Path(output_root).resolve()
        if root.exists():
            raise ProgramProtocolError(f"program output already exists: {root}", first_loss="PROGRAM_OUTPUT_EXISTS")
        root.mkdir(parents=True, exist_ok=False)
        (root / "campaigns").mkdir()
        (root / "protocols").mkdir()
        execution_id = f"research-os.program.execution.v1+{uuid.uuid4().hex}"
        store = ResearchProgramStore(root / "program-store.sqlite3")
        program = ResearchProgram(protocol.program_id, protocol.title, protocol.domain, protocol.objective, protocol.motivation, protocol.initial_problem, protocol.research_questions, tuple(item.local_id for item in protocol.campaigns), max_campaigns=protocol.max_campaigns, max_iterations=max(1, len(protocol.research_questions) or 1), max_runs=protocol.max_runs, max_failures=protocol.max_failures, status=ResearchProgramStatus.RUNNING)
        store.save(program)
        store.save_protocol(plan.program_protocol_id, plan.program_protocol_hash, protocol.to_dict(), _now())
        campaigns = {local_id: {"local_id": local_id, "campaign_protocol_id": plan.campaigns[local_id]["campaign_protocol_id"], "campaign_protocol_hash": plan.campaigns[local_id]["campaign_protocol_hash"], "depends_on": list(plan.campaigns[local_id]["depends_on"]), "role": plan.campaigns[local_id]["role"], "status": "PLANNED", "attempts": 0, "campaign_execution_id": None, "campaign_bundle_id": None, "root": None, "run_ids": [], "dataset_refs": [], "model_refs": [], "evidence_refs": [], "first_loss": None} for local_id in plan.execution_order}
        record_seed = {"program_id": protocol.program_id, "protocol_id": plan.program_protocol_id, "execution_id": execution_id}
        program_record_id = f"research-os.program-record.v1+{sha256_json(record_seed)[:16]}"
        manifest: dict[str, Any] = {"schema_version": "research-os.program-execution.v1", "program_id": protocol.program_id, "program_record_id": program_record_id, "program_protocol_id": plan.program_protocol_id, "program_protocol_hash": plan.program_protocol_hash, "program_execution_id": execution_id, "program_execution_started": False, "status": "PLANNED", "scientific_status": "UNASSESSED", "evidence_level": "E2_COMPUTATIONAL", "created_at": _now(), "updated_at": _now(), "source_path": str(Path(protocol_path).resolve()), "max_campaigns": plan.max_campaigns, "max_runs": plan.max_runs, "max_failures": plan.max_failures, "retry_count": 0, "failure_policy": plan.failure_policy, "execution_order": list(plan.execution_order), "campaigns": campaigns, "run_count": 0, "failure_count": 0, "knowledge_gain": None, "bundle": None}
        self._write_snapshot(root, manifest, plan, protocol, store)
        manifest["program_execution_started"] = True
        manifest["status"] = "RUNNING"
        manifest["updated_at"] = _now()
        self._write_snapshot(root, manifest, plan, protocol, store)
        for local_id in plan.execution_order:
            child = campaigns[local_id]
            if any(campaigns[dependency]["status"] != "COMPLETED" for dependency in child["depends_on"]):
                child.update(status="SKIPPED_DEPENDENCY", first_loss="PROGRAM_DEPENDENCY_FAILED")
                self._write_snapshot(root, manifest, plan, protocol, store, campaign_event=(local_id, child["status"], 0, child, _now()))
                continue
            if manifest["failure_count"] > 0 and manifest["failure_count"] >= plan.max_failures and plan.failure_policy == "continue_independent":
                child.update(status="BLOCKED", first_loss="PROGRAM_FAILURE_LIMIT_EXCEEDED")
                self._write_snapshot(root, manifest, plan, protocol, store, campaign_event=(local_id, child["status"], 0, child, _now()))
                continue
            campaign_protocol_source = Path(plan.campaigns[local_id]["protocol_path"])
            try:
                current_campaign_plan = self.campaign_runner.plan(campaign_protocol_source)
                campaign_protocol_matches = current_campaign_plan.campaign_protocol_id == child["campaign_protocol_id"] and current_campaign_plan.campaign_protocol_hash == child["campaign_protocol_hash"]
                campaign_protocol_loss = "PROGRAM_CAMPAIGN_PROTOCOL_MISMATCH"
            except Exception as exc:
                campaign_protocol_matches = False
                campaign_protocol_loss = _first_loss(exc, "PROGRAM_CAMPAIGN_PROTOCOL_MISMATCH")
            if not campaign_protocol_matches:
                child.update(status="BLOCKED", first_loss=campaign_protocol_loss)
                self._write_snapshot(root, manifest, plan, protocol, store, campaign_event=(local_id, child["status"], 0, child, _now()))
                continue
            child["status"] = "RUNNING"
            child["attempts"] = 1
            self._write_snapshot(root, manifest, plan, protocol, store, campaign_event=(local_id, child["status"], 1, child, _now()))
            campaign_root = root / "campaigns" / local_id
            frozen_campaign_path = root / "protocols" / f"{local_id}.json"
            campaign_protocol = load_campaign_protocol(campaign_protocol_source)
            frozen_payload = campaign_protocol.to_dict()
            for experiment in frozen_payload["experiments"]:
                experiment["protocol"] = str(_safe_protocol_ref(campaign_protocol_source.parent, experiment["protocol"]))
            frozen_campaign_path.write_text(json.dumps(frozen_payload, indent=2, sort_keys=True), encoding="utf-8")
            try:
                campaign_manifest = self.campaign_runner.run(frozen_campaign_path, campaign_root)
                if campaign_manifest.get("campaign_protocol_id") != child["campaign_protocol_id"]:
                    raise ProgramProtocolError(f"campaign protocol identity changed during execution for {local_id}", first_loss="PROGRAM_CAMPAIGN_PROTOCOL_MISMATCH")
                if campaign_manifest.get("campaign_protocol_hash") != child["campaign_protocol_hash"]:
                    raise ProgramProtocolError(f"campaign protocol hash changed during execution for {local_id}", first_loss="PROGRAM_CAMPAIGN_PROTOCOL_MISMATCH")
                child.update(status="COMPLETED" if campaign_manifest["status"] == "COMPLETED" else "FAILED", root=str(campaign_root.resolve()), campaign_execution_id=campaign_manifest.get("campaign_execution_id"), campaign_bundle_id=(campaign_manifest.get("bundle") or {}).get("bundle_id"), run_ids=[value.get("run_id") for value in campaign_manifest.get("children", {}).values() if value.get("run_id")], dataset_refs=[value["dataset_registry"] for value in campaign_manifest.get("children", {}).values() if value.get("dataset_registry")], model_refs=[value["model_registry"] for value in campaign_manifest.get("children", {}).values() if value.get("model_registry")], evidence_refs=[ref for value in campaign_manifest.get("children", {}).values() for ref in value.get("evidence_refs", [])], first_loss=None if campaign_manifest["status"] == "COMPLETED" else "CHILD_CAMPAIGN_FAILED")
                if child["status"] == "FAILED":
                    manifest["failure_count"] += 1
            except Exception as exc:
                manifest["failure_count"] += 1
                child.update(status="FAILED", root=str(campaign_root.resolve()), first_loss=_first_loss(exc, "PROGRAM_CAMPAIGN_EXECUTION_FAILED"), error=str(exc))
            manifest["run_count"] = sum(len(value.get("run_ids", [])) for value in campaigns.values())
            manifest["updated_at"] = _now()
            self._write_snapshot(root, manifest, plan, protocol, store, campaign_event=(local_id, child["status"], 1, child, _now()))
            if child["status"] == "FAILED" and plan.failure_policy == "stop_on_failure":
                for remaining in plan.execution_order[plan.execution_order.index(local_id) + 1:]:
                    if campaigns[remaining]["status"] == "PLANNED":
                        campaigns[remaining].update(status="BLOCKED", first_loss="PROGRAM_CAMPAIGN_EXECUTION_FAILED")
                        store.append_campaign(execution_id, remaining, campaigns[remaining]["status"], 0, campaigns[remaining], _now())
                break
        manifest["status"] = "COMPLETED" if all(value["status"] == "COMPLETED" for value in campaigns.values()) else ("FAILED" if all(value["status"] == "FAILED" for value in campaigns.values()) else "PARTIAL")
        controller = ResearchProgramController(program).record_iteration(runs=manifest["run_count"], failures=manifest["failure_count"])
        gain = KnowledgeGainAssessment(protocol.program_id, unresolved_uncertainty=("Program synthesis is structural only; scientific support remains unassessed.",), summary="No automatic scientific claim was promoted by Program aggregation.")
        final_status = controller.program.status if controller.program.status in {ResearchProgramStatus.NO_PROGRESS, ResearchProgramStatus.INDETERMINATE} else (ResearchProgramStatus.COMPLETED if manifest["status"] == "COMPLETED" else ResearchProgramStatus.INDETERMINATE)
        final_program = controller.program.with_status(final_status)
        store.save(final_program)
        manifest["controller_state"] = {"program_digest": final_program.digest, "iteration_count": controller.iteration_count, "run_count": controller.run_count, "failure_count": controller.failure_count, "consecutive_no_progress": controller.consecutive_no_progress, "status": final_program.status.value, "stop_reason": final_program.stop_reason}
        manifest["knowledge_gain"] = gain.to_dict()
        manifest["bundle"] = _make_program_bundle(manifest, root)
        manifest["updated_at"] = _now()
        self._write_snapshot(root, manifest, plan, protocol, store)
        store.append_event(execution_id, "PROGRAM_COMPLETED", {"status": manifest["status"], "failure_count": manifest["failure_count"]}, manifest["updated_at"])
        store.close()
        return manifest

    @staticmethod
    def _write_snapshot(root: Path, manifest: dict[str, Any], plan: ResearchProgramExecutionPlan, protocol: ResearchProgramProtocol, store: ResearchProgramStore, campaign_event: tuple[str, str, int, dict[str, Any], str] | None = None) -> None:
        plan_path = root / "execution-plan.json"
        if not plan_path.exists():
            plan_path.write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        protocol_path = root / "program-protocol.json"
        if not protocol_path.exists():
            protocol_path.write_text(json.dumps(protocol.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        manifest["program_protocol_document_hash"] = sha256_file(protocol_path)
        manifest["execution_plan_hash"] = json.loads(plan_path.read_text(encoding="utf-8"))["plan_hash"]
        payload = {key: value for key, value in manifest.items() if key != "record_hash"}
        manifest["record_hash"] = sha256_json(payload)
        (root / "program-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        if campaign_event is None:
            store.save_execution(manifest)
        else:
            local_id, status, attempt, payload, created_at = campaign_event
            store.save_execution_with_campaign(manifest, local_id=local_id, status=status, attempt=attempt, payload=payload, created_at=created_at)


def _make_program_bundle(manifest: Mapping[str, Any], root: Path) -> dict[str, Any]:
    bundle_seed = {"execution": manifest["program_execution_id"], "campaigns": manifest["execution_order"]}
    bundle_id = f"research-os.program.bundle.v1+{sha256_json(bundle_seed)[:16]}"
    bundle = {"schema_version": "research-os.program-bundle.v1", "program_id": manifest["program_id"], "bundle_id": bundle_id, "program_protocol_id": manifest["program_protocol_id"], "program_execution_id": manifest["program_execution_id"], "campaign_protocol_ids": [value["campaign_protocol_id"] for value in manifest["campaigns"].values()], "campaign_execution_ids": [value["campaign_execution_id"] for value in manifest["campaigns"].values() if value.get("campaign_execution_id")], "campaign_bundle_ids": [value["campaign_bundle_id"] for value in manifest["campaigns"].values() if value.get("campaign_bundle_id")], "run_ids": [run_id for value in manifest["campaigns"].values() for run_id in value.get("run_ids", [])], "dataset_refs": [ref for value in manifest["campaigns"].values() for ref in value.get("dataset_refs", [])], "model_refs": [ref for value in manifest["campaigns"].values() for ref in value.get("model_refs", [])], "evidence_refs": [ref for value in manifest["campaigns"].values() for ref in value.get("evidence_refs", [])], "knowledge_gain": manifest["knowledge_gain"], "scientific_status": manifest["scientific_status"], "evidence_level": manifest["evidence_level"], "sealed": True}
    bundle["bundle_hash"] = sha256_json({key: value for key, value in bundle.items() if key != "bundle_hash"})
    (root / "program-bundle.json").write_text(json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return bundle


def verify_program_execution(root: str | Path) -> ProgramVerification:
    target = Path(root).resolve()
    gates: list[dict[str, Any]] = []
    try:
        manifest_path = target / "program-manifest.json"
        plan_path = target / "execution-plan.json"
        protocol_path = target / "program-protocol.json"
        if not target.is_dir() or not manifest_path.is_file() or not plan_path.is_file() or not protocol_path.is_file():
            raise ProgramProtocolError("program execution package is incomplete", first_loss="PROGRAM_RECORD_MISSING")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if sha256_json({key: value for key, value in plan.items() if key != "plan_hash"}) != plan.get("plan_hash"):
            raise ProgramProtocolError("program execution plan hash mismatch", first_loss="PROGRAM_RECORD_HASH_MISMATCH")
        if sha256_file(protocol_path) != manifest.get("program_protocol_document_hash"):
            raise ProgramProtocolError("program protocol document hash mismatch", first_loss="PROGRAM_PROTOCOL_IDENTITY_MISMATCH")
        ResearchProgramProtocol.from_mapping(json.loads(protocol_path.read_text(encoding="utf-8")), source_path=protocol_path)
        if sha256_json({key: value for key, value in manifest.items() if key != "record_hash"}) != manifest.get("record_hash"):
            raise ProgramProtocolError("program record hash mismatch", first_loss="PROGRAM_RECORD_HASH_MISMATCH")
        if manifest.get("execution_plan_hash") != plan.get("plan_hash") or manifest.get("program_protocol_id") != plan.get("program_protocol_id"):
            raise ProgramProtocolError("program execution identity differs from plan", first_loss="PROGRAM_PROTOCOL_IDENTITY_MISMATCH")
        declared = set(plan.get("execution_order", []))
        campaigns = manifest.get("campaigns")
        if not isinstance(campaigns, Mapping) or set(campaigns) != declared:
            raise ProgramProtocolError("declared and observed campaigns differ", first_loss="PROGRAM_UNDECLARED_CAMPAIGN")
        campaigns_root = target / "campaigns"
        actual_dirs = {item.name for item in campaigns_root.iterdir()} if campaigns_root.is_dir() else set()
        if actual_dirs - declared:
            raise ProgramProtocolError("undeclared campaign execution exists", first_loss="PROGRAM_UNDECLARED_CAMPAIGN")
        if manifest.get("program_execution_started") is not True:
            raise ProgramProtocolError("program execution was never started")
        for local_id, child in campaigns.items():
            if child.get("status") not in _TERMINAL:
                raise ProgramProtocolError(f"campaign {local_id} has no terminal status", first_loss="PROGRAM_LINEAGE_INCOMPLETE")
            if int(child.get("attempts", 0)) > 1:
                raise ProgramProtocolError(f"campaign {local_id} was implicitly retried", first_loss="PROGRAM_RETRY_NOT_ALLOWED")
            if child.get("status") == "COMPLETED":
                result = verify_campaign_execution(child["root"])
                if result.status != "PASS":
                    raise ProgramProtocolError(f"campaign verification failed for {local_id}: {result.first_loss}", first_loss="PROGRAM_CAMPAIGN_VERIFY_FAILED")
                campaign_manifest = json.loads((Path(child["root"]) / "campaign-manifest.json").read_text(encoding="utf-8"))
                if campaign_manifest.get("campaign_protocol_id") != child.get("campaign_protocol_id") or campaign_manifest.get("campaign_protocol_hash") != child.get("campaign_protocol_hash") or campaign_manifest.get("campaign_execution_id") != child.get("campaign_execution_id"):
                    raise ProgramProtocolError(f"campaign lineage mismatch for {local_id}", first_loss="PROGRAM_CAMPAIGN_PROTOCOL_MISMATCH")
                if campaign_manifest.get("bundle", {}).get("bundle_id") != child.get("campaign_bundle_id"):
                    raise ProgramProtocolError(f"campaign bundle mismatch for {local_id}", first_loss="PROGRAM_LINEAGE_INCOMPLETE")
                gates.append({"rule_id": "PROGRAM-CAMPAIGN-VERIFIED", "status": "PASS", "campaign": local_id})
            for dependency in child.get("depends_on", []):
                if child.get("status") == "COMPLETED" and campaigns.get(dependency, {}).get("status") != "COMPLETED":
                    raise ProgramProtocolError(f"campaign {local_id} completed despite failed dependency", first_loss="PROGRAM_DEPENDENCY_FAILED")
        if int(manifest.get("run_count", 0)) > int(manifest.get("max_runs", 0)):
            raise ProgramProtocolError("program run limit exceeded", first_loss="PROGRAM_RUN_LIMIT_EXCEEDED")
        if int(manifest.get("failure_count", 0)) > int(manifest.get("max_failures", 0)):
            raise ProgramProtocolError("program failure limit exceeded", first_loss="PROGRAM_FAILURE_LIMIT_EXCEEDED")
        if manifest.get("evidence_level") != "E2_COMPUTATIONAL" or manifest.get("scientific_status") != "UNASSESSED":
            raise ProgramProtocolError("program aggregation attempted an evidence or scientific status promotion")
        bundle_path = target / "program-bundle.json"
        if not bundle_path.is_file() or json.loads(bundle_path.read_text(encoding="utf-8")) != manifest.get("bundle"):
            raise ProgramProtocolError("program bundle is missing or inconsistent", first_loss="PROGRAM_BUNDLE_MISMATCH")
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        if sha256_json({key: value for key, value in bundle.items() if key != "bundle_hash"}) != bundle.get("bundle_hash"):
            raise ProgramProtocolError("program bundle hash mismatch", first_loss="PROGRAM_BUNDLE_MISMATCH")
        store = ResearchProgramStore(target / "program-store.sqlite3")
        snapshot = store.get_execution(str(manifest["program_execution_id"]))
        program_snapshot = store.get(str(manifest["program_id"]))
        store.close()
        if sha256_json({key: value for key, value in snapshot.items() if key != "record_hash"}) != snapshot.get("record_hash"):
            raise ProgramProtocolError("durable execution snapshot hash mismatch", first_loss="PROGRAM_RECORD_HASH_MISMATCH")
        if snapshot.get("record_hash") != manifest.get("record_hash"):
            raise ProgramProtocolError("durable program snapshot differs from manifest", first_loss="PROGRAM_RECORD_HASH_MISMATCH")
        if not program_snapshot.valid:
            raise ProgramProtocolError("durable ResearchProgram snapshot integrity failed", first_loss="PROGRAM_SNAPSHOT_DIGEST_MISMATCH")
        if set(program_snapshot.campaign_ids) != set(manifest.get("execution_order", ())) or program_snapshot.max_campaigns != manifest.get("max_campaigns") or program_snapshot.max_runs != manifest.get("max_runs") or program_snapshot.max_failures != manifest.get("max_failures"):
            raise ProgramProtocolError("durable ResearchProgram snapshot differs from the frozen execution limits", first_loss="PROGRAM_LINEAGE_INCOMPLETE")
        gates.extend([
            {"rule_id": "PROGRAM-PLAN-FROZEN", "status": "PASS", "reason": "program protocol and declared campaign set are frozen"},
            {"rule_id": "PROGRAM-NO-UNDECLARED-CAMPAIGNS", "status": "PASS", "reason": "observed campaign roots match the static plan"},
            {"rule_id": "PROGRAM-EVIDENCE-BOUNDARY", "status": "PASS", "reason": "program remains E2_COMPUTATIONAL and scientifically unassessed"},
        ])
        return ProgramVerification("PASS", str(target), None, tuple(gates))
    except (OSError, KeyError, TypeError, sqlite3.DatabaseError, json.JSONDecodeError, CampaignProtocolError, ProgramProtocolError) as exc:
        return ProgramVerification("FAIL", str(target), _first_loss(exc, "PROGRAM_VERIFICATION_FAILED"), tuple(gates))


def inspect_program_execution(root: str | Path) -> dict[str, Any]:
    verification = verify_program_execution(root)
    target = Path(root).resolve()
    manifest = json.loads((target / "program-manifest.json").read_text(encoding="utf-8"))
    return {"verification": verification.to_dict(), "program_id": manifest.get("program_id"), "program_protocol_id": manifest.get("program_protocol_id"), "program_execution_id": manifest.get("program_execution_id"), "status": manifest.get("status"), "scientific_status": manifest.get("scientific_status"), "evidence_level": manifest.get("evidence_level"), "execution_order": manifest.get("execution_order"), "campaigns": manifest.get("campaigns"), "knowledge_gain": manifest.get("knowledge_gain"), "bundle": manifest.get("bundle")}


__all__ = ["PROGRAM_PROTOCOL_ID", "PROGRAM_SCHEMA_VERSION", "ProgramCampaignRef", "ProgramProtocolError", "ProgramVerification", "ResearchProgramBundle", "ResearchProgramExecutionPlan", "ResearchProgramProtocol", "DeclarativeProgramRunner", "inspect_program_execution", "load_program_protocol", "verify_program_execution"]
