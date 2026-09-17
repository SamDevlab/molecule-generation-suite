"""Claim-level synthesis of already verified Campaign evidence.

This module consumes sealed Campaign packages and a predeclared Program
synthesis plan.  It never runs a Campaign or Experiment and never promotes
Evidence Level by aggregation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any, Mapping

from research_os.core.hashing import sha256_file, sha256_json
from research_os.core.types import EvidenceLevel
from research_os.evidence.synthesis import EvidenceAgreementAssessment, EvidenceAgreementStatus
from research_os.knowledge.claims import ClaimRevision, ClaimStatus, ScientificClaim
from research_os.programs.models import KnowledgeGainAssessment
from research_os.programs.store import ResearchProgramStore


SYNTHESIS_ENGINE_ID = "research-os.program.synthesis.v1+claim-level"
SYNTHESIS_SCHEMA_VERSION = "research-os.program-synthesis.v1"
SYNTHESIS_INPUT_SCHEMA_VERSION = "research-os.program-synthesis-input.v1"
_LEVEL_ORDER = {
    EvidenceLevel.TEST_SYNTHETIC.value: -1,
    EvidenceLevel.E0_HEURISTIC.value: 0,
    EvidenceLevel.E1_ML.value: 1,
    EvidenceLevel.E2_COMPUTATIONAL.value: 2,
    EvidenceLevel.E3_PHYSICS.value: 3,
    EvidenceLevel.E4_CURATED_EXPERIMENTAL.value: 4,
    EvidenceLevel.E5_VALIDATED_EXPERIMENTAL.value: 5,
}
_CONTRIBUTIONS = {"SUPPORTS", "CONTRADICTS", "NEUTRAL", "INDETERMINATE", "NOT_COMPARABLE", "UNAVAILABLE"}
_OBSERVATION_STATUSES = {"AVAILABLE", "INDETERMINATE", "NOT_COMPARABLE", "UNAVAILABLE"}


class ProgramSynthesisError(ValueError):
    def __init__(self, message: str, *, first_loss: str = "PROGRAM_SYNTHESIS_INVALID") -> None:
        super().__init__(message)
        self.first_loss = first_loss


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first_loss(exc: Exception, fallback: str) -> str:
    return str(getattr(exc, "first_loss", None) or fallback)


def _level(value: Any) -> str:
    if isinstance(value, EvidenceLevel):
        return value.value
    try:
        normalized = EvidenceLevel(str(value)).value
    except ValueError as exc:
        raise ProgramSynthesisError(f"unsupported Evidence Level: {value}", first_loss="PROGRAM_SYNTHESIS_INVALID") from exc
    return normalized


def _safe_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProgramSynthesisError(f"{name} must be a non-empty string")
    return value.strip()


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProgramSynthesisError(f"{name} must be a mapping")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProgramSynthesisError(f"cannot load synthesis input: {path}", first_loss="PROGRAM_SYNTHESIS_INPUT_MISSING") from exc
    if not isinstance(value, dict):
        raise ProgramSynthesisError("synthesis document must be an object")
    return value


def _bundle_evidence_ids(bundle: Mapping[str, Any]) -> set[str]:
    identifiers: set[str] = set()
    for ref in bundle.get("child_evidence_refs", ()):
        if isinstance(ref, str):
            identifiers.add(ref)
        elif isinstance(ref, Mapping):
            for key in ("evidence_id", "id", "sha256"):
                value = ref.get(key)
                if isinstance(value, str) and value:
                    identifiers.add(value)
    return identifiers


def _load_context(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = _load_json(root / "program-manifest.json")
    plan = _load_json(root / "execution-plan.json")
    protocol = _load_json(root / "program-protocol.json")
    synthesis_input_path = root / "synthesis-input.json"
    synthesis_input = _load_json(synthesis_input_path)
    if synthesis_input.get("schema_version") != SYNTHESIS_INPUT_SCHEMA_VERSION:
        raise ProgramSynthesisError("unsupported synthesis input schema", first_loss="PROGRAM_SYNTHESIS_INVALID")
    if synthesis_input.get("program_execution_id") != manifest.get("program_execution_id"):
        raise ProgramSynthesisError("synthesis input belongs to another Program execution", first_loss="PROGRAM_SYNTHESIS_INPUT_MISSING")
    return manifest, plan, protocol, synthesis_input


def _validate_inputs(root: Path, manifest: Mapping[str, Any], synthesis_input: Mapping[str, Any], claims: Mapping[str, Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    entries = synthesis_input.get("campaigns")
    if not isinstance(entries, list):
        raise ProgramSynthesisError("synthesis input campaigns must be a list", first_loss="PROGRAM_SYNTHESIS_INPUT_MISSING")
    declared = set(manifest.get("execution_order", ()))
    observed = [entry.get("local_id") for entry in entries if isinstance(entry, Mapping)]
    if set(observed) != declared or len(observed) != len(set(observed)):
        raise ProgramSynthesisError("synthesis input Campaign set differs from Program execution", first_loss="PROGRAM_SYNTHESIS_UNDECLARED_CAMPAIGN")
    by_campaign: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        item = _mapping(entry, "synthesis-input.campaigns[]")
        local_id = _safe_id(item.get("local_id"), "campaign local_id")
        child = _mapping(manifest["campaigns"].get(local_id), f"manifest campaign {local_id}")
        if item.get("campaign_execution_id") != child.get("campaign_execution_id") or item.get("campaign_bundle_id") != child.get("campaign_bundle_id"):
            raise ProgramSynthesisError(f"Campaign execution linkage mismatch for {local_id}", first_loss="PROGRAM_SYNTHESIS_EVIDENCE_MISMATCH")
        campaign_evidence = item.get("evidence", [])
        if not isinstance(campaign_evidence, list):
            raise ProgramSynthesisError(f"evidence must be a list for {local_id}", first_loss="PROGRAM_SYNTHESIS_INPUT_MISSING")
        bundle: dict[str, Any] = {}
        if child.get("status") == "COMPLETED":
            bundle_path = Path(str(child["root"])) / "campaign-bundle.json"
            if not bundle_path.is_file() or not child.get("campaign_bundle_id"):
                raise ProgramSynthesisError(f"verified Campaign bundle missing for {local_id}", first_loss="PROGRAM_SYNTHESIS_INPUT_MISSING")
            if item.get("bundle_sha256") != sha256_file(bundle_path):
                raise ProgramSynthesisError(f"Campaign bundle hash mismatch for {local_id}", first_loss="PROGRAM_SYNTHESIS_EVIDENCE_MISMATCH")
            bundle = _load_json(bundle_path)
            if bundle.get("bundle_id") != child.get("campaign_bundle_id"):
                raise ProgramSynthesisError(f"Campaign bundle identity mismatch for {local_id}", first_loss="PROGRAM_SYNTHESIS_EVIDENCE_MISMATCH")
        allowed_evidence_ids = _bundle_evidence_ids(bundle)
        normalized: list[dict[str, Any]] = []
        for raw in campaign_evidence:
            record = dict(_mapping(raw, f"evidence for {local_id}"))
            claim_local_id = _safe_id(record.get("claim_local_id"), "evidence claim_local_id")
            if claim_local_id not in claims:
                raise ProgramSynthesisError(f"evidence references undeclared claim {claim_local_id}", first_loss="PROGRAM_SYNTHESIS_UNDECLARED_CLAIM")
            status = str(record.get("status", "AVAILABLE"))
            contribution = str(record.get("contribution", "INDETERMINATE"))
            if status not in _OBSERVATION_STATUSES or contribution not in _CONTRIBUTIONS:
                raise ProgramSynthesisError(f"invalid evidence contribution for {local_id}", first_loss="PROGRAM_SYNTHESIS_INVALID")
            evidence_id = record.get("evidence_id")
            if status == "AVAILABLE":
                if not isinstance(evidence_id, str) or not evidence_id or evidence_id not in allowed_evidence_ids:
                    raise ProgramSynthesisError(f"evidence is not present in verified Campaign bundle for {local_id}", first_loss="PROGRAM_SYNTHESIS_EVIDENCE_MISMATCH")
                if child.get("status") != "COMPLETED":
                    raise ProgramSynthesisError(f"failed Campaign cannot contribute available evidence: {local_id}", first_loss="PROGRAM_SYNTHESIS_EVIDENCE_MISMATCH")
                record["level"] = _level(record.get("level"))
            elif evidence_id is not None:
                raise ProgramSynthesisError(f"non-available evidence cannot carry an evidence ID for {local_id}", first_loss="PROGRAM_SYNTHESIS_INVALID")
            dimensions = record.get("dimensions", {})
            if not isinstance(dimensions, Mapping):
                raise ProgramSynthesisError(f"evidence dimensions must be a mapping for {local_id}")
            record["dimensions"] = dict(dimensions)
            record["status"] = status
            record["contribution"] = contribution
            record["negative_result"] = bool(record.get("negative_result", False))
            record["limitations"] = [str(item) for item in record.get("limitations", [])]
            record["_bundle_sha256"] = item.get("bundle_sha256")
            normalized.append(record)
        by_campaign[local_id] = normalized
    for claim_local_id, target in claims.items():
        for campaign_id in target["campaigns"]:
            if not any(item.get("claim_local_id") == claim_local_id for item in by_campaign[campaign_id]):
                raise ProgramSynthesisError(f"Campaign {campaign_id} is missing a contribution for {claim_local_id}", first_loss="PROGRAM_SYNTHESIS_EVIDENCE_MISSING")
    return by_campaign


def _canonical_synthesis_input(manifest: Mapping[str, Any], by_campaign: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, Any]:
    """Return the scientific input projection used for synthesis identity.

    The source JSON is an operational transport document.  Its formatting,
    object-key order, and list order are intentionally excluded from the
    identity; the verified Campaign/evidence content is retained instead.
    """
    campaigns: list[dict[str, Any]] = []
    for local_id in sorted(by_campaign):
        rows = []
        for row in by_campaign[local_id]:
            rows.append({
                "claim_local_id": row["claim_local_id"],
                "evidence_id": row.get("evidence_id"),
                "level": row.get("level"),
                "contribution": row["contribution"],
                "status": row["status"],
                "dimensions": dict(row["dimensions"]),
                "negative_result": row["negative_result"],
                "limitations": sorted(row["limitations"]),
            })
        rows.sort(key=lambda value: (
            value["claim_local_id"],
            value["evidence_id"] or "",
            value["status"],
            value["contribution"],
        ))
        campaigns.append({
            "local_id": local_id,
            "campaign_execution_id": manifest["campaigns"][local_id]["campaign_execution_id"],
            "campaign_bundle_id": manifest["campaigns"][local_id]["campaign_bundle_id"],
            "bundle_sha256": by_campaign[local_id][0].get("_bundle_sha256") if by_campaign[local_id] else None,
            "evidence": rows,
        })
    return {"program_execution_id": manifest["program_execution_id"], "campaigns": campaigns}


def _agreement_for(target: Mapping[str, Any], rows: list[dict[str, Any]]) -> tuple[EvidenceAgreementStatus, str | None, list[str], list[str]]:
    required = list(target["comparability"]["required_dimensions"])
    available = [row for row in rows if row["status"] == "AVAILABLE"]
    if not available:
        return EvidenceAgreementStatus.INSUFFICIENT_EVIDENCE, None, [], ["No available evidence was supplied."]
    if any(row["status"] == "NOT_COMPARABLE" or row["contribution"] == "NOT_COMPARABLE" for row in rows):
        return EvidenceAgreementStatus.NOT_COMPARABLE, None, [], ["At least one declared contribution is not comparable."]
    if any(any(dimension not in row["dimensions"] for dimension in required) for row in available):
        return EvidenceAgreementStatus.NOT_COMPARABLE, None, [], ["A required comparability dimension is missing."]
    signatures = {sha256_json({dimension: row["dimensions"][dimension] for dimension in required}) for row in available}
    if len(signatures) > 1:
        return EvidenceAgreementStatus.NOT_COMPARABLE, None, [], ["Declared comparability dimensions differ across Campaigns."]
    levels = [row["level"] for row in available]
    strongest = max(levels, key=lambda value: _LEVEL_ORDER[value])
    directions = {row["contribution"] for row in available}
    conflicts = sorted(str(row.get("evidence_id")) for row in available if row["contribution"] in {"SUPPORTS", "CONTRADICTS"}) if {"SUPPORTS", "CONTRADICTS"}.issubset(directions) else []
    incomplete = any(row["status"] in {"UNAVAILABLE", "INDETERMINATE"} or row["contribution"] in {"UNAVAILABLE", "INDETERMINATE"} for row in rows)
    if "SUPPORTS" in directions and "CONTRADICTS" in directions:
        return EvidenceAgreementStatus.CONFLICTING, strongest, conflicts, ["Comparable evidence supports incompatible directions."]
    if directions <= {"SUPPORTS"} or directions <= {"CONTRADICTS"}:
        return (EvidenceAgreementStatus.PARTIALLY_CONSISTENT if incomplete else EvidenceAgreementStatus.CONSISTENT), strongest, conflicts, (["Some declared Campaign contributions were unavailable or indeterminate."] if incomplete else [])
    return EvidenceAgreementStatus.INSUFFICIENT_EVIDENCE, strongest, conflicts, ["No directional support or contradiction was available."]


def _claim_outcome(target: Mapping[str, Any], rows: list[dict[str, Any]], agreement: EvidenceAgreementStatus, strongest: str | None) -> ClaimStatus:
    minimum = _level(target["minimum_evidence_level"])
    available = [row for row in rows if row["status"] == "AVAILABLE"]
    qualified = [row for row in available if _LEVEL_ORDER[row["level"]] >= _LEVEL_ORDER[minimum]]
    complete = len(qualified) == len(available) == len(rows) and bool(rows)
    directions = {row["contribution"] for row in qualified}
    if not complete or strongest is None or _LEVEL_ORDER[strongest] < _LEVEL_ORDER[minimum] or agreement in {EvidenceAgreementStatus.CONFLICTING, EvidenceAgreementStatus.NOT_COMPARABLE, EvidenceAgreementStatus.PARTIALLY_CONSISTENT, EvidenceAgreementStatus.INSUFFICIENT_EVIDENCE}:
        return ClaimStatus.INSUFFICIENT_EVIDENCE
    rule = target["decision_rule"]["type"]
    if rule == "PREDECLARED_DIRECTION":
        required = target["decision_rule"]["required_direction"]
        if directions == {required}:
            return ClaimStatus.SUPPORTED
        if directions == ({"CONTRADICTS"} if required == "SUPPORTS" else {"SUPPORTS"}):
            return ClaimStatus.REJECTED
        return ClaimStatus.INSUFFICIENT_EVIDENCE
    return ClaimStatus.SUPPORTED if directions == {"SUPPORTS"} and agreement == EvidenceAgreementStatus.CONSISTENT else ClaimStatus.INSUFFICIENT_EVIDENCE


@dataclass(frozen=True)
class ProgramSynthesisVerification:
    status: str
    root: str
    first_loss: str | None
    gates: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "root": self.root, "first_loss": self.first_loss, "gates": [dict(item) for item in self.gates]}


@dataclass(frozen=True)
class ResearchProgramSynthesis:
    synthesis_id: str
    synthesis_hash: str
    program_protocol_id: str
    program_execution_id: str
    engine_identity: str
    synthesis_input_hash: str
    claims: tuple[Mapping[str, Any], ...]
    agreements: tuple[Mapping[str, Any], ...]
    claim_revisions: tuple[Mapping[str, Any], ...]
    conflicts: tuple[Mapping[str, Any], ...]
    negative_results: tuple[Mapping[str, Any], ...]
    unavailable_evidence: tuple[Mapping[str, Any], ...]
    strongest_supported_level: str | None
    knowledge_gain: Mapping[str, Any]
    unresolved_uncertainty: tuple[str, ...]
    scientific_payload: Mapping[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SYNTHESIS_SCHEMA_VERSION,
            "synthesis_id": self.synthesis_id,
            "synthesis_hash": self.synthesis_hash,
            "program_protocol_id": self.program_protocol_id,
            "program_execution_id": self.program_execution_id,
            "engine_identity": self.engine_identity,
            "synthesis_input_hash": self.synthesis_input_hash,
            "claims": [dict(item) for item in self.claims],
            "agreements": [dict(item) for item in self.agreements],
            "claim_revisions": [dict(item) for item in self.claim_revisions],
            "conflicts": [dict(item) for item in self.conflicts],
            "negative_results": [dict(item) for item in self.negative_results],
            "unavailable_evidence": [dict(item) for item in self.unavailable_evidence],
            "strongest_supported_level": self.strongest_supported_level,
            "knowledge_gain": dict(self.knowledge_gain),
            "unresolved_uncertainty": list(self.unresolved_uncertainty),
            "scientific_payload": dict(self.scientific_payload),
            "created_at": self.created_at,
        }


def _build_synthesis(root: Path) -> ResearchProgramSynthesis:
    manifest, plan, protocol, synthesis_input = _load_context(root)
    synthesis_plan = _mapping(protocol.get("synthesis"), "program.synthesis")
    if synthesis_plan.get("mode") != "CLAIM_LEVEL" or not isinstance(synthesis_plan.get("claims"), list):
        raise ProgramSynthesisError("Program Protocol does not contain a CLAIM_LEVEL synthesis plan", first_loss="PROGRAM_SYNTHESIS_INVALID")
    claim_targets = {str(item["local_id"]): dict(item) for item in synthesis_plan["claims"]}
    campaign_evidence = _validate_inputs(root, manifest, synthesis_input, claim_targets)
    synthesis_input_hash = sha256_json(_canonical_synthesis_input(manifest, campaign_evidence))
    claim_outputs: list[dict[str, Any]] = []
    agreements: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    negative_results: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    revisions: list[dict[str, Any]] = []
    scientific_claims: list[dict[str, Any]] = []
    strongest_levels: list[str] = []
    supported_ids: list[str] = []
    rejected_ids: list[str] = []
    revised_ids: list[str] = []
    new_evidence_ids: list[str] = []
    unresolved: list[str] = []
    for local_id in sorted(claim_targets):
        target = claim_targets[local_id]
        rows = [dict(row, campaign_local_id=campaign_id) for campaign_id in target["campaigns"] for row in campaign_evidence[campaign_id] if row["claim_local_id"] == local_id]
        rows.sort(key=lambda row: (row["campaign_local_id"], row.get("evidence_id") or "", row["status"], row["contribution"]))
        agreement_status, strongest, conflict_ids, limitations = _agreement_for(target, rows)
        if strongest is not None:
            strongest_levels.append(strongest)
        status = _claim_outcome(target, rows, agreement_status, strongest)
        claim_identity = {"program_protocol_id": manifest["program_protocol_id"], "local_id": local_id, "statement": target["statement"]}
        prior_claim = target.get("prior_claim")
        claim_id = str(prior_claim.get("claim_id")) if isinstance(prior_claim, Mapping) and prior_claim.get("claim_id") else f"CLM-{sha256_json(claim_identity)[:12].upper()}"
        evidence_ids = tuple(sorted(str(row["evidence_id"]) for row in rows if row["status"] == "AVAILABLE" and row.get("evidence_id")))
        matrix = [{"campaign_local_id": row["campaign_local_id"], "status": row["status"], "contribution": row["contribution"], "evidence_id": row.get("evidence_id"), "level": row.get("level"), "dimensions": dict(row["dimensions"]), "negative_result": row["negative_result"], "limitations": sorted(row["limitations"])} for row in rows]
        assessment_identity = {"synthesis": manifest["program_execution_id"], "claim": local_id, "matrix": matrix}
        assessment_id = f"AGR-{sha256_json(assessment_identity)[:12].upper()}"
        assessment = EvidenceAgreementAssessment(claim_target=target["statement"], evidence_ids=evidence_ids, conditions={"required_dimensions": list(target["comparability"]["required_dimensions"])}, consistency=agreement_status, conflicts=tuple(conflict_ids), strongest_supported_level=strongest, limitations=tuple(limitations), agreement_id=assessment_id, assessment_id=assessment_id, evidence_types=tuple(sorted({row.get("evidence_type", "UNSPECIFIED") for row in rows})), comparability="COMPARABLE" if agreement_status in {EvidenceAgreementStatus.CONSISTENT, EvidenceAgreementStatus.PARTIALLY_CONSISTENT, EvidenceAgreementStatus.CONFLICTING} else agreement_status.value)
        agreement_dict = assessment.to_dict()
        agreements.append(agreement_dict)
        if agreement_status == EvidenceAgreementStatus.CONFLICTING:
            conflicts.append({"claim_local_id": local_id, "campaigns": sorted({row["campaign_local_id"] for row in rows if row["contribution"] in {"SUPPORTS", "CONTRADICTS"}}), "evidence_ids": conflict_ids, "reason": "comparable evidence points in incompatible directions"})
        for row in rows:
            if row["negative_result"] or row["contribution"] == "CONTRADICTS":
                negative_results.append({"claim_local_id": local_id, **matrix[rows.index(row)]})
            if row["status"] in {"UNAVAILABLE", "INDETERMINATE", "NOT_COMPARABLE"} or row["contribution"] in {"UNAVAILABLE", "INDETERMINATE", "NOT_COMPARABLE"}:
                unavailable.append({"claim_local_id": local_id, **matrix[rows.index(row)]})
        claim_conditions = {"required_dimensions": list(target["comparability"]["required_dimensions"]), "agreement": agreement_status.value}
        claim = ScientificClaim(statement=str(target["statement"]), run_id=str(manifest["program_execution_id"]), evidence_ids=evidence_ids, minimum_evidence_level=EvidenceLevel(_level(target["minimum_evidence_level"])), status=status, claim_id=claim_id, limitations=tuple(limitations), conditions=claim_conditions, derived_from=(assessment_id,))
        claim_dict = claim.to_dict()
        claim_output = {"local_id": local_id, "claim": claim_dict, "agreement_id": assessment_id, "agreement": agreement_dict, "matrix": matrix, "status": status.value}
        claim_outputs.append(claim_output)
        scientific_claims.append({"local_id": local_id, "claim_id": claim_id, "statement": str(target["statement"]), "minimum_evidence_level": _level(target["minimum_evidence_level"]), "status": status.value, "agreement": agreement_status.value, "strongest_supported_level": strongest, "evidence_ids": list(evidence_ids), "matrix": matrix, "decision_rule": dict(target["decision_rule"]), "campaigns": list(target["campaigns"])})
        if status == ClaimStatus.SUPPORTED:
            supported_ids.append(claim_id)
        elif status == ClaimStatus.REJECTED:
            rejected_ids.append(claim_id)
        if status == ClaimStatus.INSUFFICIENT_EVIDENCE:
            unresolved.append(f"{local_id}: {agreement_status.value}; claim support is not established.")
        prior = target.get("prior_claim")
        if isinstance(prior, Mapping) and (str(prior.get("status")) != status.value or tuple(prior.get("evidence_ids", ())) != evidence_ids):
            previous_status = ClaimStatus(str(prior["status"]))
            revision_identity = {"claim_id": claim_id, "version": int(prior["version"]) + 1, "synthesis": manifest["program_execution_id"]}
            revision_id = f"REV-{sha256_json(revision_identity)[:12].upper()}"
            revision = ClaimRevision(revision_id=revision_id, claim_id=claim_id, version=int(prior["version"]) + 1, statement=str(target["statement"]), previous_status=previous_status, current_status=status, previous_evidence_ids=tuple(str(item) for item in prior["evidence_ids"]), evidence_ids=evidence_ids, reason=f"Cross-campaign synthesis {manifest['program_execution_id']} produced {status.value} with agreement {agreement_status.value}.", limitations=tuple(limitations), derived_from=(assessment_id,), previous_revision_id=prior.get("revision_id"), conditions=claim_conditions)
            revisions.append(revision.to_dict())
            revised_ids.append(claim_id)
        new_evidence_ids.extend(evidence_ids)
    scientific_payload = {"schema_version": SYNTHESIS_SCHEMA_VERSION, "program_protocol_id": manifest["program_protocol_id"], "program_execution_id": manifest["program_execution_id"], "engine_identity": SYNTHESIS_ENGINE_ID, "synthesis_input_hash": synthesis_input_hash, "claims": scientific_claims, "conflicts": conflicts, "negative_results": negative_results, "unavailable_evidence": unavailable, "strongest_supported_level": max(strongest_levels, key=lambda value: _LEVEL_ORDER[value]) if strongest_levels else None}
    synthesis_hash = sha256_json(scientific_payload)
    synthesis_id = f"research-os.program.synthesis.v1+{synthesis_hash[:16]}"
    gain = KnowledgeGainAssessment(str(manifest["program_id"]), new_supported_claim_ids=tuple(supported_ids), new_rejected_claim_ids=tuple(rejected_ids), revised_claim_ids=tuple(revised_ids), new_evidence_ids=tuple(sorted(set(new_evidence_ids))), unresolved_uncertainty=tuple(unresolved), summary="Cross-campaign claim-level synthesis preserved agreement, conflict, unavailable evidence and declared limitations without Evidence Level promotion.")
    return ResearchProgramSynthesis(synthesis_id, synthesis_hash, str(manifest["program_protocol_id"]), str(manifest["program_execution_id"]), SYNTHESIS_ENGINE_ID, synthesis_input_hash, tuple(claim_outputs), tuple(agreements), tuple(revisions), tuple(conflicts), tuple(negative_results), tuple(unavailable), scientific_payload.get("strongest_supported_level"), gain.to_dict(), tuple(unresolved), scientific_payload, _now())


def synthesize_program(root: str | Path) -> dict[str, Any]:
    from research_os.programs.lineage import verify_program_execution

    target = Path(root).resolve()
    verification = verify_program_execution(target)
    if verification.status != "PASS":
        raise ProgramSynthesisError(f"Program verification failed: {verification.first_loss}", first_loss="PROGRAM_SYNTHESIS_INPUT_MISSING")
    result = _build_synthesis(target)
    manifest_path = target / "program-manifest.json"
    existing_synthesis_path = target / "program-synthesis.json"
    if existing_synthesis_path.is_file():
        existing_synthesis = _load_json(existing_synthesis_path)
        if existing_synthesis.get("synthesis_id") == result.synthesis_id and existing_synthesis.get("synthesis_hash") == result.synthesis_hash:
            result = replace(result, created_at=str(existing_synthesis.get("created_at", result.created_at)))
    manifest = _load_json(manifest_path)
    if manifest.get("synthesis"):
        history_dir = target / "syntheses"
        history_dir.mkdir(exist_ok=True)
        previous = manifest["synthesis"]
        if previous.get("synthesis_id") != result.synthesis_id or previous.get("synthesis_hash") != result.synthesis_hash:
            previous_path = history_dir / f"{previous['synthesis_id'].replace('/', '_')}.json"
            if not previous_path.exists():
                previous_path.write_text(json.dumps(previous, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
            history_entry = {"synthesis_id": previous["synthesis_id"], "synthesis_hash": previous["synthesis_hash"], "path": str(previous_path.relative_to(target))}
            if history_entry not in manifest.setdefault("synthesis_history", []):
                manifest["synthesis_history"].append(history_entry)
    synthesis_dict = result.to_dict()
    (target / "program-synthesis.json").write_text(json.dumps(synthesis_dict, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    manifest["synthesis"] = synthesis_dict
    manifest["scientific_status"] = "ASSESSED"
    manifest["knowledge_gain"] = result.knowledge_gain
    bundle_path = target / "program-bundle.json"
    bundle = _load_json(bundle_path)
    bundle.update({"synthesis_id": result.synthesis_id, "synthesis_hash": result.synthesis_hash, "claim_ids": [item["claim"]["claim_id"] for item in result.claims], "claim_revision_ids": [item["revision_id"] for item in result.claim_revisions], "agreement_assessment_ids": [item["agreement_id"] for item in result.claims], "conflict_refs": list(result.conflicts), "negative_result_refs": list(result.negative_results)})
    bundle["bundle_hash"] = sha256_json({key: value for key, value in bundle.items() if key != "bundle_hash"})
    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    manifest["bundle"] = bundle
    manifest["updated_at"] = _now()
    manifest["record_hash"] = sha256_json({key: value for key, value in manifest.items() if key != "record_hash"})
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    store = ResearchProgramStore(target / "program-store.sqlite3")
    store.save_synthesis(synthesis_dict, result.created_at)
    store.save_execution(manifest)
    store.append_event(str(manifest["program_execution_id"]), "PROGRAM_SYNTHESIS_RECORDED", {"synthesis_id": result.synthesis_id, "synthesis_hash": result.synthesis_hash}, manifest["updated_at"])
    store.close()
    return synthesis_dict


def _canonical_synthesis_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Project a synthesis record without operational assessment timestamps."""
    payload = json.loads(json.dumps(record, ensure_ascii=False, sort_keys=True))
    payload.pop("created_at", None)
    for agreement in payload.get("agreements", []):
        if isinstance(agreement, dict):
            agreement.pop("assessed_at", None)
            agreement.pop("digest", None)
    for claim in payload.get("claims", []):
        if isinstance(claim, dict) and isinstance(claim.get("agreement"), dict):
            claim["agreement"].pop("assessed_at", None)
            claim["agreement"].pop("digest", None)
    return payload


def _verify_agreement_records(record: Mapping[str, Any]) -> None:
    candidates: list[Mapping[str, Any]] = []
    candidates.extend(item for item in record.get("agreements", ()) if isinstance(item, Mapping))
    for claim in record.get("claims", ()):
        if isinstance(claim, Mapping) and isinstance(claim.get("agreement"), Mapping):
            candidates.append(claim["agreement"])
    for item in candidates:
        try:
            assessment = EvidenceAgreementAssessment(
                claim_target=str(item["claim_target"]),
                evidence_ids=tuple(item.get("evidence_ids", ())),
                conditions=dict(item.get("conditions", {})),
                consistency=str(item["consistency"]),
                conflicts=tuple(item.get("conflicts", ())),
                strongest_supported_level=item.get("strongest_supported_level"),
                limitations=tuple(item.get("limitations", ())),
                agreement_id=str(item["agreement_id"]),
                assessed_at=str(item["assessed_at"]),
                digest=str(item["digest"]),
                assessment_id=str(item.get("assessment_id") or item["agreement_id"]),
                evidence_types=tuple(item.get("evidence_types", ())),
                comparability=str(item.get("comparability", "NOT_ASSESSED")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProgramSynthesisError("invalid persisted EvidenceAgreementAssessment", first_loss="PROGRAM_SYNTHESIS_IDENTITY_MISMATCH") from exc
        if not assessment.valid:
            raise ProgramSynthesisError("persisted EvidenceAgreementAssessment digest mismatch", first_loss="PROGRAM_SYNTHESIS_IDENTITY_MISMATCH")


def _verify_synthesis_payload(root: str | Path, manifest: Mapping[str, Any] | None = None) -> ProgramSynthesisVerification:
    target = Path(root).resolve()
    try:
        current_manifest = dict(manifest) if manifest is not None else _load_json(target / "program-manifest.json")
        synthesis = current_manifest.get("synthesis")
        if not isinstance(synthesis, Mapping):
            raise ProgramSynthesisError("Program has no formal synthesis", first_loss="PROGRAM_SYNTHESIS_INPUT_MISSING")
        stored = _load_json(target / "program-synthesis.json")
        if stored != synthesis:
            raise ProgramSynthesisError("program synthesis file differs from Program manifest", first_loss="PROGRAM_SYNTHESIS_IDENTITY_MISMATCH")
        computed = _build_synthesis(target).to_dict()
        _verify_agreement_records(stored)
        if stored.get("scientific_payload") != computed.get("scientific_payload") or stored.get("synthesis_id") != computed.get("synthesis_id") or stored.get("synthesis_hash") != computed.get("synthesis_hash") or _canonical_synthesis_record(stored) != _canonical_synthesis_record(computed):
            raise ProgramSynthesisError("program synthesis identity or claim matrix mismatch", first_loss="PROGRAM_SYNTHESIS_IDENTITY_MISMATCH")
        store = ResearchProgramStore(target / "program-store.sqlite3")
        persisted = store.get_synthesis(str(stored["synthesis_id"]))
        store.close()
        if _canonical_synthesis_record(persisted) != _canonical_synthesis_record(stored):
            raise ProgramSynthesisError("persisted synthesis differs from the synthesis manifest", first_loss="PROGRAM_SYNTHESIS_IDENTITY_MISMATCH")
        if current_manifest.get("evidence_level") != "E2_COMPUTATIONAL":
            raise ProgramSynthesisError("Program synthesis attempted Evidence Level inflation", first_loss="PROGRAM_SYNTHESIS_LEVEL_INFLATION")
        return ProgramSynthesisVerification("PASS", str(target), None, ({"rule_id": "PROGRAM-SYNTHESIS-VERIFIED", "status": "PASS", "reason": "claim matrix and Campaign evidence inputs are deterministic and persisted"},))
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ProgramSynthesisError) as exc:
        return ProgramSynthesisVerification("FAIL", str(target), _first_loss(exc, "PROGRAM_SYNTHESIS_INVALID"), ())


def verify_program_synthesis(root: str | Path) -> ProgramSynthesisVerification:
    from research_os.programs.lineage import verify_program_execution

    base = verify_program_execution(root)
    if base.status != "PASS":
        return ProgramSynthesisVerification("FAIL", str(Path(root).resolve()), base.first_loss or "PROGRAM_SYNTHESIS_INPUT_MISSING", base.gates)
    return _verify_synthesis_payload(root)


def inspect_program_synthesis(root: str | Path) -> dict[str, Any]:
    verification = verify_program_synthesis(root)
    synthesis = _load_json(Path(root).resolve() / "program-synthesis.json")
    return {"verification": verification.to_dict(), "synthesis_id": synthesis.get("synthesis_id"), "program_execution_id": synthesis.get("program_execution_id"), "claims": synthesis.get("claims"), "agreements": synthesis.get("agreements"), "conflicts": synthesis.get("conflicts"), "negative_results": synthesis.get("negative_results"), "unavailable_evidence": synthesis.get("unavailable_evidence"), "strongest_supported_level": synthesis.get("strongest_supported_level"), "knowledge_gain": synthesis.get("knowledge_gain")}


__all__ = ["ProgramSynthesisError", "ProgramSynthesisVerification", "ResearchProgramSynthesis", "SYNTHESIS_ENGINE_ID", "SYNTHESIS_INPUT_SCHEMA_VERSION", "inspect_program_synthesis", "synthesize_program", "verify_program_synthesis"]
