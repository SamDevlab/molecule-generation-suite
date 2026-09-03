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
            # A concrete, harmless fixture keeps the provider contract
            # executable while making it clear that the provider supplies no
            # scientific result itself.
            steps = [{"step_id": "molecule", "lab": "MoleculeLab", "experiment": "deterministic_properties", "inputs": {"smiles": "CCO"}, "produces": ["properties"], "minimum_evidence_level": "E2_COMPUTATIONAL"}]
        return {"question_id": question["question_id"], "steps": steps, "assumptions": [], "required_sources": [], "expected_outputs": ["evidence", "claims"], "risk_flags": [], "claim_targets": []}

    def repair_plan(self, plan: dict[str, Any], issues: list[dict[str, Any]]) -> dict[str, Any]:
        return dict(plan)

    def summarize_results(self, results: dict[str, Any]) -> dict[str, Any]:
        return {"summary": "structured result summary requires recorded evidence", "status": results.get("status", "INDETERMINATE")}

    def propose_followup(self, gaps: list[dict[str, Any]]) -> dict[str, Any]:
        return {"gaps": gaps, "next_steps": [step for gap in gaps for step in gap.get("recommended_next_steps", [])]}


class CodexTestProvider:
    """Local structured provider used to exercise the Oracle E2E boundary.

    This provider deliberately has no network client.  It models the structured
    responses supplied by the current Codex turn, while all scientific values
    still have to be produced by registered Labs.  It is therefore an
    integration-test provider, never an evidence provider or a production LLM.
    """

    provider_id = "CODEX_TEST"
    provider = provider_id
    model = "codex-test"
    model_version = "1"
    mode = "INTEGRATION_TEST"
    external_api = False
    scientific_evidence_provider = False
    production_llm = False

    _ALLOWED_LABS = {"MoleculeLab", "FuelLab", "CombustionLab", "ThermalLab", "PropulsionLab", "DockingLab"}

    def __init__(self) -> None:
        self._counter = 0

    def _id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter:04d}"

    @property
    def audit_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.provider_id,
            "mode": self.mode,
            "external_api": self.external_api,
            "scientific_evidence_provider": self.scientific_evidence_provider,
            "production_llm": self.production_llm,
        }

    def audit(self) -> dict[str, Any]:
        """Return the explicit test-provider boundary for reports and CI."""
        return {**self.audit_metadata, "status": "VALIDATED_WITH_CODEX_TEST_PROVIDER", "external_status": "NOT_CONFIGURED"}

    def interpret_question(self, text: str) -> dict[str, Any]:
        normalized = str(text).strip()
        lower = normalized.lower()
        if any(term in lower for term in ("ignore previous", "ignore previous instructions", "ignore as regras", "execute shell", "execute comando")):
            domain = "security"
            objective = "Use only the allowlisted molecular analysis fixture; reject prompt-injected commands."
            allowed_tools = ["MoleculeLab"]
        elif any(term in lower for term in ("cura", "cure", "alzheimer", "clinical", "clínica")) and any(term in lower for term in ("docking", "dock")):
            domain = "pharma"
            objective = normalized
            allowed_tools = ["DockingLab"]
        elif any(term in lower for term in ("aqsoldb", "out-of-domain", "out of domain", "fora do domínio")):
            domain = "solubility"
            objective = normalized
            allowed_tools = ["MoleculeLab"]
        elif any(term in lower for term in ("e4", "evidence", "evidência", "experimental")):
            domain = "evidence_policy"
            objective = normalized
            allowed_tools = []
        elif any(term in lower for term in ("fuel", "combust", "combustível", "propulsion", "propulsão")):
            domain = "aerospace"
            objective = normalized
            allowed_tools = []
        else:
            domain = "molecule"
            objective = normalized
            allowed_tools = []

        required = "E2_COMPUTATIONAL"
        if "e5" in lower or "validated experimental" in lower:
            required = "E5_VALIDATED_EXPERIMENTAL"
        elif "e4" in lower or "curated experimental" in lower:
            required = "E4_CURATED_EXPERIMENTAL"
        return {
            "question_id": self._id("Q"),
            "text": normalized,
            "domain": domain,
            "objective": objective,
            "constraints": {"no_clinical_overclaim": True, "provider": self.provider_id},
            "required_evidence_level": required,
            "allowed_tools": allowed_tools,
            "forbidden_tools": ["shell", "arbitrary_command", "clinical_claim"],
        }

    def generate_plan(self, question: dict[str, Any], memory: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        domain = str(question.get("domain", "molecule"))
        objective = str(question.get("objective", question.get("text", "")))
        if domain == "aerospace":
            steps = [
                {
                    "step_id": "fuel",
                    "lab": "FuelLab",
                    "experiment": "fuel_catalog",
                    "inputs": {"components": [{"name": "fuel-A", "smiles": "C", "fraction": 1.0}]},
                    "produces": ["fuel"],
                    "minimum_evidence_level": "E2_COMPUTATIONAL",
                },
                {
                    "step_id": "combustion",
                    "lab": "CombustionLab",
                    "experiment": "adiabatic_equilibrium_hp",
                    "inputs": {
                        "fuel": "CH4:1",
                        "mechanism": "gri30.yaml",
                        "temperature": {"value": 300, "unit": "K"},
                        "pressure": {"value": 1, "unit": "atm"},
                        "temperature_k": 300.0,
                        "pressure_pa": 101325.0,
                    },
                    "requires": ["fuel"],
                    "produces": ["combustion"],
                    "minimum_evidence_level": "E3_PHYSICS",
                },
                {
                    "step_id": "thermal",
                    "lab": "ThermalLab",
                    "experiment": "steady_planar_conduction",
                    "inputs": {"hot_temperature_k": 500.0, "cold_temperature_k": 300.0, "conductivity_w_mk": 10.0, "thickness_m": 0.01, "area_m2": 1.0},
                    "requires": ["combustion"],
                    "produces": ["thermal"],
                    "minimum_evidence_level": "E2_COMPUTATIONAL",
                },
                {
                    "step_id": "propulsion",
                    "lab": "PropulsionLab",
                    "experiment": "ideal_nozzle_from_combustion",
                    "inputs": {
                        "combustion": {"fuel": "CH4:1", "mechanism": "gri30.yaml", "temperature_k": 300.0, "pressure_pa": 101325.0},
                        "chamber_temperature": {"value": 300, "unit": "K"},
                        "gamma": 1.2,
                        "molecular_weight": 20.0,
                    },
                    "requires": ["thermal"],
                    "produces": ["propulsion"],
                    "minimum_evidence_level": "E3_PHYSICS",
                },
            ]
        elif domain == "pharma":
            # The planner records the requested docking scope, but the Oracle
            # claim gate decides whether it may be executed.
            steps = [{
                "step_id": "docking",
                "lab": "DockingLab",
                "experiment": "vina_docking",
                "inputs": {"receptor_path": "REQUIRED", "ligand_path": "REQUIRED", "grid": {"center_x": 0, "center_y": 0, "center_z": 0, "size_x": 20, "size_y": 20, "size_z": 20}},
                "produces": ["docking"],
                "minimum_evidence_level": "E2_COMPUTATIONAL",
            }]
        else:
            smiles = dict(question.get("constraints") or {}).get("smiles") or "CCO"
            steps = [{
                "step_id": "molecule",
                "lab": "MoleculeLab",
                "experiment": "deterministic_properties",
                "inputs": {"smiles": str(smiles), "name": "codex-test-fixture"},
                "produces": ["molecular_properties"],
                "minimum_evidence_level": "E2_COMPUTATIONAL",
            }]
        return {
            "question_id": question.get("question_id"),
            "steps": steps,
            "assumptions": ["Only registered Labs may produce scientific evidence."],
            "required_sources": [],
            "expected_outputs": ["evidence", "claims"],
            "risk_flags": ["CODEX_TEST_PROVIDER", "NO_LLM_EVIDENCE"],
            "claim_targets": [{"statement": objective, "required_evidence_level": "E4_CURATED_EXPERIMENTAL"}] if domain == "pharma" and any(term in objective.lower() for term in ("cura", "cure", "clinical", "clínica", "alzheimer")) else [],
            "metadata": {**self.audit_metadata, "memory_records": len(memory or [])},
        }

    def repair_plan(self, plan: dict[str, Any], issues: list[dict[str, Any]]) -> dict[str, Any]:
        """Make at most a conservative structural repair; never add evidence."""
        repaired = dict(plan)
        repaired["steps"] = []
        for raw in plan.get("steps") or []:
            step = dict(raw)
            lab = str(step.get("lab", ""))
            if lab not in self._ALLOWED_LABS:
                continue
            inputs = dict(step.get("inputs") or {})
            if lab == "MoleculeLab" and inputs.get("smiles") in (None, "", "REQUIRED"):
                inputs["smiles"] = "CCO"
            step["inputs"] = inputs
            step["requires"] = [dep for dep in step.get("requires") or () if dep in {str(item.get("step_id")) for item in plan.get("steps") or ()}]
            repaired["steps"].append(step)
        repaired["risk_flags"] = [*(plan.get("risk_flags") or ()), "LIMITED_REPAIR"]
        return repaired

    def summarize_results(self, results: dict[str, Any]) -> dict[str, Any]:
        steps = results.get("steps") or {}
        evidence = results.get("evidence") or []
        if not evidence and isinstance(results.get("runs"), dict):
            evidence = [item for run in results["runs"].values() for item in (run.get("evidence") or [])]
        statuses = [str(item.get("status")) for item in steps.values() if isinstance(item, dict)] if isinstance(steps, dict) else []
        status = str(results.get("status") or ("SUPPORTED" if statuses and all(value == "PASS" for value in statuses) else "INDETERMINATE"))
        return {
            "summary": f"Codex test summary is grounded in {len(evidence)} recorded evidence item(s) and {len(steps)} workflow step(s).",
            "status": status,
            "evidence_count": len(evidence),
            "grounded": True,
            "metadata": self.audit_metadata,
        }

    def propose_followup(self, gaps: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "text": "Continue the research using only the recorded evidence gaps.",
            "domain": "continuation",
            "objective": "Resolve recorded evidence gaps",
            "constraints": {"gap_count": len(gaps)},
            "required_evidence_level": "E2_COMPUTATIONAL",
            "gaps": list(gaps),
        }


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
    metadata = getattr(provider, "audit_metadata", {})
    return LLMCallAudit(provider.provider_id, provider.model, provider.model_version, operation, prompt_template, _hash(redact_secrets(prompt)), _hash(redact_secrets(response)), planning_run_id, dict(metadata) if isinstance(metadata, dict) else {})
