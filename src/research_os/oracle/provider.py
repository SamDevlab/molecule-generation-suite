"""Provider-neutral structured LLM boundary and audit records."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
from typing import Any, Protocol


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def redact_secrets(value: Any) -> Any:
    """Remove common secret-shaped fields before recording an LLM audit."""
    if isinstance(value, dict):
        return {str(key): "[REDACTED]" if re.search(r"token|secret|password|api[_-]?key", str(key), re.I) else redact_secrets(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_secrets(item) for item in value]
    return value


@dataclass(frozen=True)
class LLMCallAudit:
    provider: str
    model: str
    model_version: str | None
    operation: str
    prompt_template: str
    prompt_hash: str
    response_hash: str
    planning_run_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LLMProvider(Protocol):
    provider_id: str
    model: str
    model_version: str | None

    def interpret_question(self, text: str) -> dict[str, Any]: ...
    def generate_plan(self, question: dict[str, Any], memory: list[dict[str, Any]] | None = None) -> dict[str, Any]: ...
    def repair_plan(self, plan: dict[str, Any], issues: list[dict[str, Any]]) -> dict[str, Any]: ...
    def summarize_results(self, results: dict[str, Any]) -> dict[str, Any]: ...
    def propose_followup(self, gaps: list[dict[str, Any]]) -> dict[str, Any]: ...


class StructuredOutputError(ValueError):
    pass


class RuleBasedLLMProvider:
    """Deterministic test provider implementing the same structured contract.

    It is a planner test double, not scientific evidence and not a substitute
    for a language model.
    """

    provider_id = "rule-based-test-provider"
    model = "rules"
    model_version = "1"

    def interpret_question(self, text: str) -> dict[str, Any]:
        lower = text.lower()
        domain = "pharma" if any(token in lower for token in ("docking", "alzheimer", "receptor", "ligand")) else "aerospace" if any(token in lower for token in ("fuel", "combust", "propellant", "isp", "propuls")) else "general"
        return {"text": text, "domain": domain, "objective": text, "constraints": {"no_clinical_overclaim": True}, "required_evidence_level": "E2_COMPUTATIONAL", "allowed_tools": [], "forbidden_tools": []}

    def generate_plan(self, question: dict[str, Any], memory: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        domain = question.get("domain")
        if domain == "aerospace":
            steps = [
                {"step_id": "fuel", "lab": "FuelLab", "experiment": "fuel_catalog", "inputs": {"fuel": question.get("objective", "")}, "produces": ["fuel"], "minimum_evidence_level": "E0_HEURISTIC"},
                {"step_id": "combustion", "lab": "CombustionLab", "experiment": "adiabatic_equilibrium_hp", "inputs": {"fuel": question.get("objective", ""), "mechanism": "gri30.yaml", "temperature": {"value": 300, "unit": "K"}, "pressure": {"value": 1, "unit": "atm"}}, "requires": ["fuel"], "produces": ["combustion"], "minimum_evidence_level": "E3_PHYSICS"},
                {"step_id": "propulsion", "lab": "PropulsionLab", "experiment": "ideal_nozzle_from_combustion", "inputs": {"combustion": "combustion", "chamber_temperature": {"value": 300, "unit": "K"}, "gamma": 1.2, "molecular_weight": 20.0}, "requires": ["combustion"], "produces": ["propulsion"], "minimum_evidence_level": "E3_PHYSICS"},
            ]
        elif domain == "pharma":
            steps = [{"step_id": "docking", "lab": "DockingLab", "experiment": "vina_docking", "inputs": {"receptor": "REQUIRED", "ligand": "REQUIRED", "grid": "REQUIRED"}, "produces": ["docking"], "minimum_evidence_level": "E2_COMPUTATIONAL"}]
        else:
            steps = [{"step_id": "molecule", "lab": "MoleculeLab", "experiment": "deterministic_properties", "inputs": {"smiles": "REQUIRED"}, "produces": ["properties"], "minimum_evidence_level": "E2_COMPUTATIONAL"}]
        return {"question_id": question["question_id"], "steps": steps, "assumptions": [], "required_sources": [], "expected_outputs": ["evidence", "claims"], "risk_flags": [], "claim_targets": []}

    def repair_plan(self, plan: dict[str, Any], issues: list[dict[str, Any]]) -> dict[str, Any]:
        return dict(plan)

    def summarize_results(self, results: dict[str, Any]) -> dict[str, Any]:
        return {"summary": "structured result summary requires recorded evidence", "status": results.get("status", "INDETERMINATE")}

    def propose_followup(self, gaps: list[dict[str, Any]]) -> dict[str, Any]:
        return {"gaps": gaps, "next_steps": [step for gap in gaps for step in gap.get("recommended_next_steps", [])]}


def parse_structured_output(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise StructuredOutputError("LLM output is not valid JSON") from exc
    if not isinstance(value, dict):
        raise StructuredOutputError("LLM output must be a JSON object")
    return redact_secrets(value)


def audit_llm_call(provider: LLMProvider, operation: str, prompt: Any, response: Any, planning_run_id: str, *, prompt_template: str = "structured-json-v1") -> LLMCallAudit:
    return LLMCallAudit(provider.provider_id, provider.model, provider.model_version, operation, prompt_template, _hash(redact_secrets(prompt)), _hash(redact_secrets(response)), planning_run_id)

