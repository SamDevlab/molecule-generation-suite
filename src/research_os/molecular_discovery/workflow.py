"""Flagship Molecular Discovery workflow built from existing Research OS Labs."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from research_os.core.hashing import sha256_json
from research_os.docking.lab import DockingLab
from research_os.molecule.lab import MoleculeLab
from research_os.molecular_discovery.solubility import FrozenESOLSolubilityPredictor


WORKFLOW_ID = "research-os.molecular-discovery.v0.1"
_PRIORITY_ORDER = {
    "ELIGIBLE_FOR_REVIEW": 0,
    "OUT_OF_DOMAIN": 1,
    "INCOMPLETE_EVIDENCE": 2,
    "EXCLUDED": 3,
}


@dataclass(frozen=True)
class CandidateAssessment:
    candidate_id: str
    smiles: str
    name: str | None
    chemistry_status: str
    molecule_run_id: str | None
    molecule_properties: Mapping[str, Any] | None
    solubility_status: str
    solubility: Mapping[str, Any] | None
    docking_status: str
    docking: Mapping[str, Any] | None
    first_loss: Mapping[str, Any] | None
    priority_group: str
    review_order: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MolecularDiscoveryReport:
    workflow_id: str
    created_at: str
    candidates: tuple[CandidateAssessment, ...]
    solubility_capability: Mapping[str, Any] | None
    limitations: tuple[str, ...]
    scientific_summary_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "created_at": self.created_at,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "solubility_capability": None if self.solubility_capability is None else dict(self.solubility_capability),
            "limitations": list(self.limitations),
            "scientific_summary_hash": self.scientific_summary_hash,
        }


def _loss(run: Any, stage: str) -> dict[str, Any] | None:
    loss = getattr(run, "first_loss", None)
    if loss is None:
        return None
    return {
        "stage": stage,
        "rule_id": loss.rule_id,
        "status": loss.status.value,
        "reason": loss.reason,
        "diagnostics": dict(loss.diagnostics),
    }


def _evidence_payload(run: Any, kind: str) -> dict[str, Any] | None:
    for evidence in reversed(tuple(getattr(run, "evidence", ()))):
        if getattr(evidence, "kind", None) == kind:
            return dict(evidence.payload)
    return None


def _priority(chemistry_status: str, solubility_status: str, docking_status: str) -> str:
    if chemistry_status != "PASS":
        return "EXCLUDED"
    if solubility_status == "OUT_OF_DOMAIN":
        return "OUT_OF_DOMAIN"
    if solubility_status != "IN_DOMAIN":
        return "INCOMPLETE_EVIDENCE"
    if docking_status not in {"PASS", "NOT_REQUESTED"}:
        return "INCOMPLETE_EVIDENCE"
    return "ELIGIBLE_FOR_REVIEW"


def _scientific_projection(
    candidates: Sequence[CandidateAssessment],
    solubility_capability: Mapping[str, Any] | None,
) -> dict[str, Any]:
    projected = []
    for item in candidates:
        docking = item.docking or {}
        projected.append(
            {
                "candidate_id": item.candidate_id,
                "smiles": item.smiles,
                "chemistry_status": item.chemistry_status,
                "molecule_properties": item.molecule_properties,
                "solubility_status": item.solubility_status,
                "solubility": item.solubility,
                "docking_status": item.docking_status,
                "docking": {
                    "best_affinity_kcal_mol": docking.get("best_affinity_kcal_mol"),
                    "engine": docking.get("engine"),
                    "engine_version": docking.get("engine_version"),
                    "docking_capability": docking.get("docking_capability"),
                } if docking else None,
                "priority_group": item.priority_group,
            }
        )
    return {
        "workflow_id": WORKFLOW_ID,
        "candidates": projected,
        "solubility_model_identity": (
            None if solubility_capability is None else solubility_capability.get("model_identity")
        ),
    }


class MolecularDiscoveryWorkflow:
    """Compose MoleculeLab, frozen solubility and optional DockingLab.

    No composite efficacy score is produced. Review order is only deterministic
    triage: evidence-complete in-domain candidates first, followed by higher
    predicted aqueous logS within the same frozen model.
    """

    def __init__(
        self,
        *,
        molecule_lab: MoleculeLab | None = None,
        solubility_predictor: FrozenESOLSolubilityPredictor | None = None,
        docking_lab: DockingLab | None = None,
    ) -> None:
        self.molecule_lab = molecule_lab or MoleculeLab()
        self.solubility_predictor = solubility_predictor
        self.docking_lab = docking_lab

    def assess(self, raw: Mapping[str, Any]) -> CandidateAssessment:
        candidate_id = str(raw.get("id") or raw.get("candidate_id") or "").strip()
        smiles = str(raw.get("smiles") or raw.get("SMILES") or "").strip()
        name = str(raw.get("name")).strip() if raw.get("name") is not None else None
        if not candidate_id:
            candidate_id = "UNNAMED"

        molecule = self.molecule_lab.run(
            {
                "id": candidate_id,
                "name": name,
                "smiles": smiles,
                "source": "molecular-discovery",
            },
            experiment="molecular_discovery_characterization",
        )
        chemistry_status = "PASS" if molecule.passed else "FAIL"
        molecule_properties = _evidence_payload(molecule, "deterministic_molecular_properties")
        first_loss = _loss(molecule, "chemistry")

        solubility_status = "UNAVAILABLE"
        solubility: dict[str, Any] | None = None
        if molecule.passed and self.solubility_predictor is not None:
            try:
                prediction = self.solubility_predictor.predict(smiles)
                solubility = prediction.to_dict()
                solubility_status = prediction.domain_status
            except Exception as exc:
                solubility_status = "FAILED"
                first_loss = first_loss or {
                    "stage": "solubility",
                    "rule_id": "MOLDISC-SOL-001",
                    "status": "INDETERMINATE",
                    "reason": "solubility prediction failed",
                    "diagnostics": {"error_type": type(exc).__name__, "error": str(exc)},
                }

        docking_status = "NOT_REQUESTED"
        docking: dict[str, Any] | None = None
        docking_request = raw.get("docking")
        if molecule.passed and docking_request:
            try:
                docking_run = self.docking_lab.run(
                    dict(docking_request),
                    experiment="molecular_discovery_docking",
                )
            except Exception as exc:
                docking_status = "FAILED"
                first_loss = first_loss or {
                    "stage": "docking",
                    "rule_id": "MOLDISC-DOCK-001",
                    "status": "FAIL",
                    "reason": "docking execution raised an exception",
                    "diagnostics": {"error_type": type(exc).__name__, "error": str(exc)},
                }
            else:
                docking_status = "PASS" if docking_run.passed else "FAILED"
                docking = _evidence_payload(docking_run, "molecular_docking_result")
                if not docking_run.passed:
                    first_loss = first_loss or _loss(docking_run, "docking")

        group = _priority(chemistry_status, solubility_status, docking_status)
        return CandidateAssessment(
            candidate_id=candidate_id,
            smiles=smiles,
            name=name,
            chemistry_status=chemistry_status,
            molecule_run_id=getattr(molecule, "run_id", None),
            molecule_properties=molecule_properties,
            solubility_status=solubility_status,
            solubility=solubility,
            docking_status=docking_status,
            docking=docking,
            first_loss=first_loss,
            priority_group=group,
        )

    def run(self, candidates: Sequence[Mapping[str, Any]]) -> MolecularDiscoveryReport:
        assessed = [self.assess(candidate) for candidate in candidates]
        assessed.sort(
            key=lambda item: (
                _PRIORITY_ORDER[item.priority_group],
                (
                    -float((item.solubility or {}).get("predicted_log_s_mol_l"))
                    if item.solubility is not None
                    and (item.solubility or {}).get("predicted_log_s_mol_l") is not None
                    else float("inf")
                ),
                item.candidate_id,
            )
        )
        ordered = tuple(
            CandidateAssessment(**{**item.to_dict(), "review_order": index + 1})
            for index, item in enumerate(assessed)
        )
        capability = (
            None
            if self.solubility_predictor is None
            else self.solubility_predictor.evidence_manifest()
        )
        limitations = (
            "This workflow prioritizes computational review; it does not establish efficacy, safety or clinical benefit.",
            "Review order is not a universal molecular score and must not be compared across different scientific objectives as if it were one.",
            "Solubility is E1_ML and retains the ESOL/AqSolDB applicability and external-generalization limitations.",
            "Docking, when requested, is E2_COMPUTATIONAL and requires a prepared ligand/receptor plus a declared target protocol.",
            "No unavailable capability is silently replaced by a heuristic.",
        )
        summary_hash = sha256_json(_scientific_projection(ordered, capability))
        return MolecularDiscoveryReport(
            workflow_id=WORKFLOW_ID,
            created_at=datetime.now(timezone.utc).isoformat(),
            candidates=ordered,
            solubility_capability=capability,
            limitations=limitations,
            scientific_summary_hash=summary_hash,
        )

    def run_to_directory(
        self,
        candidates: Sequence[Mapping[str, Any]],
        output_root: str | Path,
    ) -> MolecularDiscoveryReport:
        report = self.run(candidates)
        root = Path(output_root)
        root.mkdir(parents=True, exist_ok=False)

        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "workflow_id": report.workflow_id,
                    "created_at": report.created_at,
                    "candidate_count": len(report.candidates),
                    "scientific_summary_hash": report.scientific_summary_hash,
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (root / "evidence.json").write_text(
            json.dumps(
                {
                    "solubility_capability": report.solubility_capability,
                    "candidates": [candidate.to_dict() for candidate in report.candidates],
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (root / "limitations.json").write_text(
            json.dumps({"limitations": list(report.limitations)}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        with (root / "candidates.csv").open("w", encoding="utf-8", newline="") as handle:
            fieldnames = [
                "review_order",
                "candidate_id",
                "name",
                "smiles",
                "priority_group",
                "chemistry_status",
                "predicted_log_s_mol_l",
                "solubility_status",
                "max_training_tanimoto",
                "docking_status",
                "best_affinity_kcal_mol",
                "first_loss_rule",
            ]
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for candidate in report.candidates:
                solubility = candidate.solubility or {}
                docking = candidate.docking or {}
                writer.writerow(
                    {
                        "review_order": candidate.review_order,
                        "candidate_id": candidate.candidate_id,
                        "name": candidate.name,
                        "smiles": candidate.smiles,
                        "priority_group": candidate.priority_group,
                        "chemistry_status": candidate.chemistry_status,
                        "predicted_log_s_mol_l": solubility.get("predicted_log_s_mol_l"),
                        "solubility_status": candidate.solubility_status,
                        "max_training_tanimoto": solubility.get("max_training_tanimoto"),
                        "docking_status": candidate.docking_status,
                        "best_affinity_kcal_mol": docking.get("best_affinity_kcal_mol"),
                        "first_loss_rule": (candidate.first_loss or {}).get("rule_id"),
                    }
                )

        (root / "report.md").write_text(_markdown(report), encoding="utf-8")
        return report


def _markdown(report: MolecularDiscoveryReport) -> str:
    lines = [
        "# Molecular Discovery Program v0.1",
        "",
        f"- Workflow: {report.workflow_id}",
        f"- Candidates: {len(report.candidates)}",
        f"- Scientific summary SHA-256: {report.scientific_summary_hash}",
        "",
        "## Candidate review order",
        "",
        "| # | Candidate | Chemistry | Solubility | logS | Docking | Priority |",
        "|---:|---|---|---|---:|---|---|",
    ]
    for item in report.candidates:
        solubility = item.solubility or {}
        predicted = solubility.get("predicted_log_s_mol_l")
        predicted_text = "—" if predicted is None else f"{float(predicted):.4f}"
        lines.append(
            f"| {item.review_order} | {item.candidate_id} | {item.chemistry_status} | "
            f"{item.solubility_status} | {predicted_text} | {item.docking_status} | {item.priority_group} |"
        )
    lines.extend(["", "## Interpretation boundaries", ""])
    lines.extend(f"- {item}" for item in report.limitations)
    lines.extend(
        [
            "",
            "The table is a computational triage view. Review order is not evidence of therapeutic efficacy and is not a substitute for experimental validation.",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "CandidateAssessment",
    "MolecularDiscoveryReport",
    "MolecularDiscoveryWorkflow",
    "WORKFLOW_ID",
]
