"""Small dependency-free web application for the operational Oracle.

The HTTP layer exposes only transport-safe service payloads.  It never imports
or executes Labs from a request and it never treats conversation text as
scientific evidence.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse
from typing import Any
import os
import uuid

from research_os.core.types import EvidenceLevel
from research_os.combustion import CombustionLab
from research_os.bundles import ResearchBundle
from research_os.candidates import CandidateEvaluation, CandidateRanking
from research_os.environment import capture_environment
from research_os.engines import EngineRegistry, run_cantera_reference_case
from research_os.knowledge import KnowledgeIngestionPipeline, KnowledgeRetriever, ReviewStatus, SourceLocator, SourceRecord, SourceRegistry, SourceType, Zettel, ZettelType, write_zettel
from research_os.oracle import CodexLiveProvider, CodexTestProvider, OraclePlanner, PlanValidator
from research_os.service import OracleService, ResearchStore
from research_os.ledger import RunRegistry
from research_os.campaigns import CampaignManager, CampaignStore
from research_os.decision import DecisionStore


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _jsonable(value.to_dict())
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


class OracleWebApplication:
    """Dispatches web requests against one long-lived OracleService."""

    def __init__(self, service: OracleService, *, data_root: str | Path, static_root: str | Path | None = None, campaigns: CampaignManager | None = None, decisions: DecisionStore | None = None):
        self.service = service
        self.campaigns = campaigns
        self.data_root = Path(data_root).resolve()
        self.decisions = decisions or DecisionStore(self.data_root / "decisions.sqlite")
        self.static_root = Path(static_root or Path(__file__).resolve().parents[3] / "web").resolve()
        self.knowledge_root = self.data_root / "knowledge"
        self.review_path = self.knowledge_root / "review-queue.json"
        self.reference_path = self.data_root / "engine-references.json"
        self._review_items: list[dict[str, Any]] = self._load_json_list(self.review_path)
        self._reference_cases: list[dict[str, Any]] = self._load_json_list(self.reference_path)

    def close(self) -> None:
        """Release local SQLite handles so reload/shutdown is clean on Windows."""
        store = getattr(self.service, "store", None)
        if store is not None:
            store.close()
        ledger = getattr(self.service, "ledger", None)
        if ledger is not None and hasattr(ledger, "close"):
            ledger.close()
        retriever = getattr(self.service, "knowledge_retriever", None)
        connection = getattr(retriever, "connection", None)
        if connection is not None:
            connection.close()
        campaign_store = getattr(self.campaigns, "store", None)
        if campaign_store is not None:
            campaign_store.close()
        resolution_store = getattr(self.campaigns, "resolution_store", None)
        if resolution_store is not None and resolution_store is not campaign_store and hasattr(resolution_store, "close"):
            resolution_store.close()
        if self.decisions is not None:
            self.decisions.close()

    def dispatch(self, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        """Return an HTTP-like `(status, JSON payload)` tuple for tests and handlers."""
        parsed = urlparse(path)
        route = unquote(parsed.path)
        query = parse_qs(parsed.query)
        body = body or {}
        try:
            if method == "GET" and route == "/api/health":
                provider = self.service.planner.provider
                return 200, {"status": "ok", "service": "Research OS 3.12", "provider": dict(getattr(provider, "audit_metadata", {}) or {}), "oracle": self.oracle_status(), "ledger_source_of_truth": True}
            if method == "GET" and route == "/api/oracle/audit":
                return 200, self.oracle_status()
            if method == "GET" and route == "/api/capabilities":
                return 200, {"capabilities": [item.to_dict() for item in self.service.planner.validator.capabilities.values()]}
            if method == "GET" and route == "/api/engines":
                return 200, {"engines": self.engine_status()}
            if method == "GET" and route == "/api/campaigns":
                if self.campaigns is None:
                    return 200, {"campaigns": []}
                return 200, {"campaigns": self.campaigns.list()}
            if method == "GET" and route == "/api/decisions":
                return 200, self.decision_index(campaign_id=str(query.get("campaign_id", [""])[0]) or None, limit=int(query.get("limit", [100])[0]))
            if method == "GET" and route.startswith("/api/decisions/"):
                decision = self.decisions.get(route.rsplit("/", 1)[1])
                return 200, {"decision": decision.to_dict(), "evidence_matrix": self.evidence_matrix((decision,)), "timeline": self.decision_timeline((decision,))}
            if method == "GET" and route.startswith("/api/campaigns/") and route.endswith("/decisions"):
                campaign_id = route.split("/")[3]
                decisions = self.decisions.list(campaign_id=campaign_id)
                return 200, {"decisions": [item.to_dict() for item in decisions], "evidence_matrix": self.evidence_matrix(decisions), "timeline": self.decision_timeline(decisions)}
            if method == "GET" and route == "/api/campaigns/memory":
                if self.campaigns is None:
                    return 404, {"error": {"code": "CAMPAIGNS_UNAVAILABLE", "message": "campaign manager is not configured"}}
                return 200, self.campaigns.cross_campaign_memory(str(query.get("q", [""])[0]) or None)
            if method == "GET" and route.startswith("/api/resolutions/"):
                if self.campaigns is None:
                    return 404, {"error": {"code": "CAMPAIGNS_UNAVAILABLE", "message": "campaign manager is not configured"}}
                return 200, self.campaigns.get_resolution(route.rsplit("/", 1)[1])
            if method == "GET" and route.startswith("/api/campaigns/") and route.endswith("/resolutions"):
                if self.campaigns is None:
                    return 404, {"error": {"code": "CAMPAIGNS_UNAVAILABLE", "message": "campaign manager is not configured"}}
                return 200, {"resolutions": self.campaigns.list_resolutions(campaign_id=route.split("/")[3])}
            if method == "GET" and route.startswith("/api/campaigns/") and route.count("/") == 3:
                if self.campaigns is None:
                    return 404, {"error": {"code": "CAMPAIGNS_UNAVAILABLE", "message": "campaign manager is not configured"}}
                return 200, self.campaigns.get(route.rsplit("/", 1)[1])
            if method == "POST" and route == "/api/campaigns/discover":
                if self.campaigns is None:
                    return 404, {"error": {"code": "CAMPAIGNS_UNAVAILABLE", "message": "campaign manager is not configured"}}
                return 200, self.campaigns.discover().to_dict()
            if method == "POST" and route == "/api/campaigns/start":
                if self.campaigns is None:
                    return 404, {"error": {"code": "CAMPAIGNS_UNAVAILABLE", "message": "campaign manager is not configured"}}
                problem_id = str(body.get("problem_id") or "").strip()
                if not problem_id:
                    return 400, {"error": {"code": "PROBLEM_ID_REQUIRED", "message": "problem_id is required"}}
                return 201, self.campaigns.start(problem_id, campaign_id=body.get("campaign_id")).to_dict()
            if method == "POST" and route.startswith("/api/campaigns/") and route.endswith("/continue"):
                if self.campaigns is None:
                    return 404, {"error": {"code": "CAMPAIGNS_UNAVAILABLE", "message": "campaign manager is not configured"}}
                return 200, self.campaigns.continue_campaign(route.split("/")[3]).to_dict()
            if method == "POST" and route.startswith("/api/campaigns/") and route.endswith("/close"):
                if self.campaigns is None:
                    return 404, {"error": {"code": "CAMPAIGNS_UNAVAILABLE", "message": "campaign manager is not configured"}}
                return 200, self.campaigns.close(route.split("/")[3]).to_dict()
            if method == "POST" and route.startswith("/api/campaigns/") and route.endswith("/resolve") and "/gaps/" in route:
                if self.campaigns is None:
                    return 404, {"error": {"code": "CAMPAIGNS_UNAVAILABLE", "message": "campaign manager is not configured"}}
                parts = route.split("/")
                return 201, self.campaigns.resolve_gap(parts[3], parts[5], strategy=body.get("strategy"), provider_plan=dict(body.get("resolution_plan") or {})).to_dict()
            if method == "POST" and route == "/api/campaigns/researcher":
                if self.campaigns is None:
                    return 404, {"error": {"code": "CAMPAIGNS_UNAVAILABLE", "message": "campaign manager is not configured"}}
                return 200, self.campaigns.final_researcher_prompt()
            if method == "POST" and route == "/api/campaigns/resolution-challenge":
                if self.campaigns is None:
                    return 404, {"error": {"code": "CAMPAIGNS_UNAVAILABLE", "message": "campaign manager is not configured"}}
                challenge = self.campaigns.final_resolution_challenge()
                if body.get("execute"):
                    challenge["resolution"] = self.campaigns.resolve_from_challenge(challenge).to_dict()
                return 200, challenge
            if method == "POST" and route == "/api/campaigns/unresolvable-challenge":
                if self.campaigns is None:
                    return 404, {"error": {"code": "CAMPAIGNS_UNAVAILABLE", "message": "campaign manager is not configured"}}
                return 200, self.campaigns.final_unresolvable_challenge()
            if method == "POST" and route == "/api/engines/reference":
                return 200, {"reference": self.run_cantera_reference() , "engines": self.engine_status()}
            if method == "GET" and route == "/api/sessions":
                return 200, {"sessions": self.service.list_sessions(limit=int(query.get("limit", [100])[0]))}
            if method == "POST" and route == "/api/sessions":
                return 201, self.service.create_session(str(body.get("title") or "New research"), tags=list(body.get("tags") or [])).to_dict()
            if method == "GET" and route.startswith("/api/sessions/"):
                session_id = route.split("/", 3)[3]
                if route.endswith("/jobs"):
                    session_id = route.split("/")[3]
                    return 200, {"jobs": self.service.list_jobs(session_id)}
                return 200, self.service.get_session(session_id)
            if method == "GET" and route == "/api/knowledge/sources":
                return 200, {"sources": [item.to_dict() for item in self.service.source_registry.list()] if self.service.source_registry is not None else []}
            if method == "GET" and route.startswith("/api/knowledge/sources/"):
                return 200, self.source_view(route.rsplit("/", 1)[1])
            if method == "GET" and route == "/api/knowledge/review-queue":
                return 200, {"status": "AWAITING_USER_CORPUS" if not self._review_items else "REVIEW_REQUIRED", "items": list(self._review_items)}
            if method == "POST" and route == "/api/knowledge/import":
                return 201, self.import_material(body)
            if method == "POST" and route.startswith("/api/knowledge/review/"):
                return 200, self.review_item(route.rsplit("/", 1)[1], body)
            if method == "POST" and route == "/api/chat":
                message = str(body.get("message") or "").strip()
                if not message:
                    return 400, {"error": {"code": "MESSAGE_REQUIRED", "message": "message is required"}}
                response = self.service.ask(message, session_id=body.get("session_id"))
                return 200, {"session_id": response.job.session_id, "response": response.to_dict()}
            if method == "POST" and route.startswith("/api/jobs/") and route.endswith("/continue"):
                job_id = route.split("/")[3]
                response = self.service.continue_research(job_id)
                return 200, {"session_id": response.job.session_id, "response": response.to_dict()}
            if method == "POST" and route.startswith("/api/jobs/") and route.endswith("/reproduce"):
                job_id = route.split("/")[3]
                response = self.service.continue_research(job_id)
                return 200, {"session_id": response.job.session_id, "response": response.to_dict()}
            if method == "GET" and route.startswith("/api/runs/"):
                return 200, self.run_view(route.rsplit("/", 1)[1])
            if method == "GET" and route == "/api/compare":
                original = str(query.get("original_run_id", [""])[0])
                rerun = str(query.get("rerun_run_id", [""])[0])
                if not original or not rerun:
                    return 400, {"error": {"code": "RUN_IDS_REQUIRED", "message": "original_run_id and rerun_run_id are required"}}
                return 200, self.service.compare_runs(original, rerun)
            if method == "GET" and route.startswith("/api/jobs/"):
                return self.job_view(route.split("/")[3], route.rsplit("/", 1)[-1], query)
            if method == "POST" and route == "/api/explain":
                ranking_raw = body.get("ranking")
                if not isinstance(ranking_raw, dict):
                    return 200, {"status": "INSUFFICIENT_EVIDENCE", "reason": "No recorded CandidateEvaluation payload was supplied; the Oracle will not invent a ranking explanation."}
                evaluations = [CandidateEvaluation(str(item["candidate_id"]), str(item["metric"]), item.get("value"), str(item["direction"]), str(item["evidence"]), str(item["status"]), bool(item.get("ood", False)), item.get("uncertainty"), dict(item.get("conditions") or {}), item.get("run_id"), item.get("protocol_id"), item.get("explanation")) for item in ranking_raw.get("evaluations") or ()]
                if self.service.ledger is None or any(not item.run_id or not self.service._ledger_has_run(item.run_id) for item in evaluations):
                    return 200, {"status": "INSUFFICIENT_EVIDENCE", "reason": "Each ranking evaluation must reference a run indexed in the Ledger."}
                ranking = CandidateRanking.rank(evaluations, metric=str(ranking_raw.get("metric", "")), direction=str(ranking_raw.get("direction", "max")))
                return 200, self.service.explain_ranking(ranking, str(body.get("candidate_a", "")), str(body.get("candidate_b", "")))
            if method == "GET" and not route.startswith("/api/"):
                return self.static_response(route)
            return 404, {"error": {"code": "NOT_FOUND", "message": "resource not found"}}
        except KeyError as exc:
            return 404, {"error": {"code": "NOT_FOUND", "message": f"resource not found: {exc.args[0] if exc.args else 'unknown'}"}}
        except ValueError as exc:
            return 400, {"error": {"code": "INVALID_REQUEST", "message": str(exc)}}
        except Exception:
            # Deliberately keep stack traces in server logs, not in the normal
            # user response.
            return 500, {"error": {"code": "INTERNAL_ERROR", "message": "The research service could not complete this request."}}

    def job_view(self, job_id: str, leaf: str, query: dict[str, list[str]] | None = None) -> tuple[int, dict[str, Any]]:
        if leaf == job_id:
            return 200, self.service.get_response(job_id)
        if leaf == "plan":
            return 200, self.service.get_plan(job_id)
        if leaf == "results":
            return 200, self.service.get_results(job_id)
        if leaf == "evidence":
            minimum = (query or {}).get("minimum", [None])[0]
            if minimum:
                return 200, self.service.filter_evidence(job_id, minimum)
            return 200, {"evidence": self.service.get_evidence(job_id)}
        if leaf == "sources":
            return 200, {"sources": self.service.get_source_records(job_id)}
        if leaf == "runs":
            return 200, {"runs": self.run_records(job_id)}
        if leaf == "lineage":
            return 200, self.service.get_lineage(job_id)
        return 404, {"error": {"code": "NOT_FOUND", "message": "job view not found"}}

    def run_records(self, job_id: str) -> list[dict[str, Any]]:
        if self.service.ledger is None:
            return [{"run_id": run_id} for run_id in self.service.get_runs(job_id)]
        records = []
        for run_id in self.service.get_runs(job_id):
            try:
                records.append(self.service.ledger.get_run(run_id).to_dict())
            except KeyError:
                records.append({"run_id": run_id})
        return records

    def run_view(self, run_id: str) -> dict[str, Any]:
        if self.service.ledger is None:
            return {"run_id": run_id}
        try:
            record = self.service.ledger.get_run(run_id)
            return {"run": record.to_dict(), "lineage": self.service.ledger.get_lineage(run_id).to_dict()}
        except KeyError:
            raise

    def source_view(self, source_id: str) -> dict[str, Any]:
        source = self.service.source_registry.get(source_id) if self.service.source_registry is not None else None
        related_jobs: list[str] = []
        related_runs: list[str] = []
        related_claims: list[dict[str, Any]] = []
        for session in self.service.list_sessions():
            for job in self.service.list_jobs(session["session_id"]):
                try:
                    answer = self.service.get_results(job["job_id"])
                except KeyError:
                    continue
                if source_id in answer.get("sources", []):
                    related_jobs.append(job["job_id"])
                    related_runs.extend(answer.get("run_ids") or [])
                    related_claims.extend(answer.get("claims") or [])
        return {"source": source.to_dict() if source is not None else {"source_id": source_id}, "related_jobs": list(dict.fromkeys(related_jobs)), "related_runs": list(dict.fromkeys(related_runs)), "claims": related_claims}

    def decision_index(self, *, campaign_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        decisions = self.decisions.list(campaign_id=campaign_id, limit=max(1, min(limit, 500)))
        return {"decisions": [item.to_dict() for item in decisions], "evidence_matrix": self.evidence_matrix(decisions), "timeline": self.decision_timeline(decisions)}

    @staticmethod
    def evidence_matrix(decisions: tuple[Any, ...] | list[Any]) -> list[dict[str, Any]]:
        matrix: list[dict[str, Any]] = []
        for decision in decisions:
            evidence = set(decision.evidence_available)
            for criterion in decision.criteria:
                matrix.append({"decision_id": decision.decision_id, "question_id": decision.question_id, "criterion_id": criterion.criterion_id, "metric": criterion.metric, "required": criterion.required, "minimum_evidence_level": criterion.minimum_evidence_level, "OOD_policy": criterion.OOD_policy, "comparison_protocol": criterion.comparison_protocol, "evidence_ids": sorted(evidence & set(decision.required_evidence)) or sorted(evidence), "status": decision.decision_status})
        return matrix

    @staticmethod
    def decision_timeline(decisions: tuple[Any, ...] | list[Any]) -> list[dict[str, Any]]:
        return [{"timestamp": decision.created_at, "decision_id": decision.decision_id, "campaign_id": decision.campaign_id, "question_id": decision.question_id, "status": decision.decision_status, "selected_option": decision.selected_option} for decision in sorted(decisions, key=lambda item: item.created_at)]

    def engine_status(self) -> list[dict[str, Any]]:
        references = {str(item.get("engine_id")): item for item in self._reference_cases}
        result = []
        for item in self.service.get_engine_status():
            engine_id = str(item.get("engine_id"))
            reference = references.get(engine_id, {})
            reference_validated = bool(reference.get("result_status") in {"SUPPORTED_AND_EXECUTED", "REFERENCE_VALIDATED"})
            executed = bool(item.get("status") in {"SUPPORTED_AND_EXECUTED", "EXECUTED"}) or reference_validated
            result.append({**item, "boundary": "IMPLEMENTED", "available": item.get("availability") == "AVAILABLE", "configured": item.get("readiness") in {"CONFIGURED", "PROTOCOL_READY", "REFERENCE_VALIDATED"}, "executed": executed, "reference_validated": reference_validated, "reference_case": reference or None})
        return result

    def oracle_status(self) -> dict[str, Any]:
        provider = self.service.planner.provider
        metadata = dict(getattr(provider, "audit_metadata", {}) or {})
        audit = provider.audit() if hasattr(provider, "audit") else {**metadata, "status": "DETERMINISTIC_TEST_ONLY"}
        return {
            "oracle_llm": "CODEX LIVE" if getattr(provider, "mode", None) == "LIVE_ORACLE" else "CODEX TEST",
            "mode": getattr(provider, "mode", "TEST"),
            "live_oracle_validation": "PASS" if getattr(provider, "mode", None) == "LIVE_ORACLE" and bool(getattr(provider, "available", lambda: True)()) else "NOT_VALIDATED",
            "scientific_evidence_provider": False,
            "external_api": "NOT_REQUIRED_FOR_THIS_MILESTONE",
            "standalone_web_llm": "STANDALONE_LLM_BRIDGE_NOT_IMPLEMENTED",
            "planner": "ACTIVE",
            "narrator": "ACTIVE",
            "plan_validator": "ENFORCED",
            "grounding": "ENFORCED",
            "provider_audit": audit,
        }

    def run_cantera_reference(self) -> dict[str, Any]:
        case = run_cantera_reference_case()
        if case.result_status == "SUPPORTED_AND_EXECUTED":
            # Materialize the same safe reference through the existing Lab
            # boundary so its E3 Evidence, environment and mechanism hashes
            # receive a normal bundle and Ledger index entry.
            run = CombustionLab().run({"fuel": "CH4:1", "oxidizer": "O2:0.21,N2:0.79", "equivalence_ratio": 1.0, "temperature_k": 300.0, "pressure_pa": 101325.0, "basis": "mole", "mechanism": "gri30.yaml"}, experiment="cantera_reference_case")
            if run.passed:
                environment = capture_environment()
                run.attach_environment(environment)
                run.seal()
                bundle = ResearchBundle.create(run, self.data_root / "bundles", environment=environment)
                if self.service.ledger is not None:
                    self.service.ledger.register_run(bundle)
                case = replace(case, run_id=run.run_id, bundle_id=bundle.bundle_id, environment_id=environment.environment_id)
        payload = case.to_dict()
        self._reference_cases = [item for item in self._reference_cases if item.get("engine_id") != "cantera"]
        self._reference_cases.append(payload)
        self._write_json(self.reference_path, self._reference_cases)
        return payload

    def import_material(self, body: dict[str, Any]) -> dict[str, Any]:
        text = str(body.get("text") or body.get("content") or "").strip()
        if not text:
            raise ValueError("text is required for material import")
        if self.service.source_registry is None or self.service.knowledge_retriever is None:
            raise ValueError("Knowledge OS is not configured")
        title = str(body.get("title") or "User material")
        source_id = str(body.get("source_id") or f"SRC-USER-{uuid.uuid4().hex[:10].upper()}")
        source = SourceRecord(source_id, title, authors=tuple(body.get("authors") or ()), year=body.get("year"), doi=body.get("doi"), url=body.get("url"), license=body.get("license") or "USER_PROVIDED", source_type=body.get("source_type", SourceType.WEB), metadata={"user_provided": True})
        self.service.source_registry.register(source)
        result = KnowledgeIngestionPipeline().ingest(source, text)
        for zettel in result.zettels:
            write_zettel(zettel, self.knowledge_root / "zettels")
            self.service.knowledge_retriever.index(zettel)
        items = [item.to_dict() for item in result.review_queue]
        self._review_items.extend(items)
        self._write_json(self.review_path, self._review_items)
        return result.to_dict()

    def review_item(self, item_id: str, body: dict[str, Any]) -> dict[str, Any]:
        requested = str(body.get("status") or "").upper()
        mapping = {"VERIFY": "VERIFIED", "VERIFIED": "VERIFIED", "REJECT": "REJECTED", "REJECTED": "REJECTED", "EDIT": "REVIEW_REQUIRED", "REVIEW_REQUIRED": "REVIEW_REQUIRED"}
        if requested not in mapping:
            raise ValueError("status must be VERIFY, REJECT or EDIT")
        for item in self._review_items:
            if item.get("review_id") == item_id or item.get("item_id") == item_id:
                item["status"] = mapping[requested]
                self._write_json(self.review_path, self._review_items)
                return {"status": "UPDATED", "item": item}
        raise KeyError(item_id)

    def static_response(self, route: str) -> tuple[int, dict[str, Any]]:
        relative = "index.html" if route in {"", "/"} else route.lstrip("/")
        if relative not in {"index.html", "app.js", "styles.css"} or Path(relative).is_absolute() or ".." in Path(relative).parts:
            return 404, {"error": {"code": "NOT_FOUND", "message": "static resource not found"}}
        path = (self.static_root / relative).resolve()
        if not path.is_file() or self.static_root not in path.parents:
            return 404, {"error": {"code": "NOT_FOUND", "message": "static resource not found"}}
        return 200, {"__static_path": str(path)}

    @staticmethod
    def _load_json_list(path: Path) -> list[dict[str, Any]]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return list(raw) if isinstance(raw, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_jsonable(value), indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    def serve(self, host: str = "127.0.0.1", port: int = 8000) -> None:
        application = self

        class Handler(BaseHTTPRequestHandler):
            def _respond(self, status: int, payload: dict[str, Any], *, content_type: str = "application/json") -> None:
                if "__static_path" in payload:
                    path = Path(payload["__static_path"])
                    data = path.read_bytes()
                    content_type = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}.get(path.suffix, "application/octet-stream")
                else:
                    data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store" if content_type.startswith("application/json") else "no-cache")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                status, payload = application.dispatch("GET", self.path)
                self._respond(status, payload)

            def do_POST(self) -> None:  # noqa: N802
                try:
                    length = min(int(self.headers.get("Content-Length", "0")), 2_000_000)
                    raw = self.rfile.read(length) if length else b"{}"
                    body = json.loads(raw.decode("utf-8"))
                    if not isinstance(body, dict):
                        raise ValueError("request body must be a JSON object")
                except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
                    self._respond(400, {"error": {"code": "INVALID_JSON", "message": "request body must be a JSON object"}})
                    return
                status, payload = application.dispatch("POST", self.path, body)
                self._respond(status, payload)

            def log_message(self, format: str, *args: Any) -> None:
                return

        server = ThreadingHTTPServer((host, port), Handler)
        print(f"Research OS 3.12 listening at http://{host}:{port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            self.close()


def build_default_application(data_root: str | Path | None = None, *, oracle_mode: str | None = None, codex_executable: str | Path | None = None) -> OracleWebApplication:
    root = Path(data_root or os.environ.get("RESEARCH_OS_DATA", Path.cwd() / ".research-os")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    ledger = RunRegistry(root / "ledger")
    store = ResearchStore(root / "experience.sqlite")
    store.recover_interrupted_jobs()
    engine_configuration = {}
    if os.environ.get("RESEARCH_OS_VINA_EXECUTABLE"):
        engine_configuration["autodock-vina"] = {"executable": os.environ["RESEARCH_OS_VINA_EXECUTABLE"]}
    if os.environ.get("RESEARCH_OS_OPENBABEL_EXECUTABLE"):
        engine_configuration["openbabel"] = {"executable": os.environ["RESEARCH_OS_OPENBABEL_EXECUTABLE"]}
    engine_registry = EngineRegistry(root / "engines", configuration=engine_configuration)
    source_registry = SourceRegistry(root / "knowledge")
    retriever = KnowledgeRetriever(sqlite3.connect(root / "knowledge" / "retrieval.sqlite", check_same_thread=False))
    _bootstrap_knowledge(source_registry, retriever)
    selected_mode = str(oracle_mode or os.environ.get("RESEARCH_OS_ORACLE_MODE", "test")).strip().lower()
    if selected_mode in {"live", "codex_live", "live_oracle"}:
        provider = CodexLiveProvider(executable=codex_executable, workdir=Path.cwd())
    elif selected_mode in {"test", "codex_test", "deterministic"}:
        provider = CodexTestProvider()
    else:
        raise ValueError("oracle_mode must be test or live")
    service = OracleService(OraclePlanner(provider, validator=PlanValidator(engine_registry=engine_registry)), ledger=ledger, store=store, bundle_root=root / "bundles", knowledge_retriever=retriever, source_registry=source_registry, engine_registry=engine_registry)
    campaign_store = CampaignStore(root / "campaigns.sqlite")
    campaigns = CampaignManager(service, campaign_store, source_registry=source_registry, retriever=retriever, data_root=root)
    application = OracleWebApplication(service, data_root=root, campaigns=campaigns, decisions=DecisionStore(root / "decisions.sqlite"))
    if not application._reference_cases:
        application.run_cantera_reference()
    return application


def _bootstrap_knowledge(source_registry: SourceRegistry, retriever: KnowledgeRetriever) -> None:
    source_id = "SRC-SQLITE-FTS5-DOCS"
    try:
        source_registry.get(source_id)
    except KeyError:
        source_registry.register(SourceRecord(source_id, "SQLite FTS5 Extension Documentation", authors=("SQLite Consortium",), year=2024, url="https://sqlite.org/fts5.html", license="SQLite documentation; public project terms", source_type=SourceType.MANUAL, metadata={"real_public_source": True, "review_status": "VERIFIED"}))
    zettel = Zettel(title="Full-text retrieval", summary="SQLite FTS5 provides a full-text search virtual table for indexed documents. This note is citation context only and does not promote an evidence level.", zettel_type=ZettelType.METHOD, domain="knowledge", evidence_level=EvidenceLevel.E0_HEURISTIC, review_status=ReviewStatus.VERIFIED, sources=(SourceLocator(source_id, url="https://sqlite.org/fts5.html", section="Overview"),))
    retriever.index(zettel)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Research OS 3.12 operational Oracle web app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--oracle-mode", choices=("test", "live"), default=None)
    args = parser.parse_args(argv)
    build_default_application(args.data_root, oracle_mode=args.oracle_mode).serve(args.host, args.port)
    return 0
