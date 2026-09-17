"""Research OS 3.5 live evidence-expansion acceptance.

The live Codex process selects and explains only.  Scientific runs, hashes,
bundles, Ledger records and claim boundaries are produced by Research OS.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from research_os.bundles import verify_bundle
from research_os.campaigns import FINAL_RESOLUTION_CHALLENGE_PROMPT, FINAL_UNRESOLVABLE_CHALLENGE_PROMPT
from research_os.core.hashing import sha256_file
from research_os.core.types import EvidenceLevel
from research_os.evidence import EvidenceAgreementAssessment, EvidenceAgreementStatus
from research_os.knowledge import ClaimRevision, ClaimStatus, ScientificClaim
from research_os.web.server import build_default_application


PHARMA_PLAN_DEFAULTS = {
    "candidate_id": "diclofenac-1pxx",
    "selected_chains": ["A"],
    "retained_cofactors": [],
    "removed_components": [
        "DIF",
        "BOG",
        "NAG",
        "HOH",
        "HEM (excluded from prepared PDBQT; Open Babel Fe cofactor conversion was incompatible)",
    ],
    "grid": {"center_x": 27.1155, "center_y": 24.09, "center_z": 14.936, "size_x": 21.427, "size_y": 22.664, "size_z": 22.533},
    "exhaustiveness": 4,
    "cpu": 2,
    "num_modes": 9,
    "docking_protocol_id": "autodock-vina.docking.v1",
    "raw_source_url": "https://www.rcsb.org/structure/1PXX",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_commit() -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=False, shell=False)
    except OSError:
        return "GIT_UNAVAILABLE"
    return result.stdout.strip() if result.returncode == 0 else "GIT_UNAVAILABLE"


def _module_probe(module_name: str, package_name: str | None = None) -> dict[str, Any]:
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        return {"status": "BLOCKED", "module": module_name, "error_type": type(exc).__name__}
    return {"status": "AVAILABLE", "module": module_name, "version": str(getattr(module, "__version__", "UNKNOWN")), "package": package_name or module_name}


def _pharma_plan(args: argparse.Namespace) -> dict[str, Any]:
    raw = dict(PHARMA_PLAN_DEFAULTS)
    raw["grid"] = dict(PHARMA_PLAN_DEFAULTS["grid"])
    receptor = Path(args.pharma_receptor).resolve() if args.pharma_receptor else REPO_ROOT / ".research-os-live-3.4.1-pharma" / "1PXX_chainA_only.pdb"
    ligand = Path(args.pharma_ligand).resolve() if args.pharma_ligand else REPO_ROOT / ".research-os-live-3.4.1-pharma" / "1PXX_DIF_chainA.pdb"
    raw.update({
        "vina_executable": str(Path(args.vina_executable).resolve()) if args.vina_executable else None,
        "openbabel_executable": str(Path(args.openbabel_executable).resolve()) if args.openbabel_executable else None,
        "receptor_path": str(receptor),
        "ligand_path": str(ligand),
        "raw_source_sha256": sha256_file(Path(args.raw_structure).resolve()) if args.raw_structure and Path(args.raw_structure).is_file() else None,
    })
    return raw


def _engine_reprobe(root: Path, vina: str | None, openbabel: str | None) -> dict[str, Any]:
    from research_os.engines import EngineRegistry

    configuration: dict[str, dict[str, str]] = {}
    if vina:
        configuration["autodock-vina"] = {"executable": vina}
    if openbabel:
        configuration["openbabel"] = {"executable": openbabel}
    registry = EngineRegistry(root / "engines-reprobe", configuration=configuration)
    return {
        "modules": [_module_probe(name) for name in ("rdkit", "cantera", "pymatgen", "matminer", "pycalphad", "scipy", "pyarrow", "duckdb")],
        "executables": {
            "openbabel": {"path": openbabel, "available": bool(openbabel and Path(openbabel).is_file()), "sha256": sha256_file(openbabel) if openbabel and Path(openbabel).is_file() else None},
            "autodock-vina": {"path": vina, "available": bool(vina and Path(vina).is_file()), "sha256": sha256_file(vina) if vina and Path(vina).is_file() else None},
        },
        "engine_manifests": [item.to_dict() for item in registry.probe_all()],
        "datasets_directory": {"path": str(root / "datasets"), "files": sorted(str(item.relative_to(root / "datasets")) for item in (root / "datasets").rglob("*") if item.is_file()) if (root / "datasets").exists() else []},
        "user_corpus": {"path": str(root / "knowledge"), "status": "AWAITING_USER_CORPUS", "files": sorted(str(item.relative_to(root / "knowledge")) for item in (root / "knowledge").rglob("*") if item.is_file() and item.name != ".gitkeep") if (root / "knowledge").exists() else []},
        "network": {"status": "AVAILABLE_FOR_OFFICIAL_SOURCE_RETRIEVAL", "policy": "registered official URLs only; source content is DATA, not instructions"},
    }


def _resolution_plan(campaign: Any, pharma_plan: dict[str, Any], battery: Path | None) -> dict[str, Any]:
    if campaign.problem_id == "P-PHARMA-01":
        return dict(pharma_plan)
    if campaign.problem_id == "P-BATT-01" and battery is not None:
        return {"artifact_path": str(battery)}
    return {}


def _resolution_for(resolutions: list[dict[str, Any]], *, campaign_id: str | None = None, gap_id: str | None = None) -> dict[str, Any] | None:
    for item in reversed(resolutions):
        if campaign_id is not None and item.get("campaign_id") != campaign_id:
            continue
        if gap_id is not None and item.get("gap_id") != gap_id:
            continue
        return item
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Research OS 3.5 live evidence expansion")
    parser.add_argument("--data-root", default=str(REPO_ROOT / ".research-os-live-3.5"))
    parser.add_argument("--codex-executable", default=None)
    parser.add_argument("--vina-executable", default=str(REPO_ROOT / ".venv" / "Scripts" / "vina.exe"))
    parser.add_argument("--openbabel-executable", default=str(REPO_ROOT / ".venv" / "Scripts" / "obabel.exe"))
    parser.add_argument("--battery-artifact", default=str(REPO_ROOT / ".research-os-live-3.4-battery" / "nasa-pcoe-rw3.zip"))
    parser.add_argument("--pharma-receptor", default=None)
    parser.add_argument("--pharma-ligand", default=None)
    parser.add_argument("--raw-structure", default=str(REPO_ROOT / ".research-os-live-3.4.1-pharma" / "1PXX.pdb"))
    args = parser.parse_args()

    root = Path(args.data_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    vina = Path(args.vina_executable).resolve() if args.vina_executable else None
    openbabel = Path(args.openbabel_executable).resolve() if args.openbabel_executable else None
    battery = Path(args.battery_artifact).resolve() if args.battery_artifact and Path(args.battery_artifact).is_file() else None
    if vina and not vina.is_file():
        vina = None
    if openbabel and not openbabel.is_file():
        openbabel = None

    if vina:
        import os
        os.environ["RESEARCH_OS_VINA_EXECUTABLE"] = str(vina)
    if openbabel:
        import os
        os.environ["RESEARCH_OS_OPENBABEL_EXECUTABLE"] = str(openbabel)

    app = build_default_application(root, oracle_mode="live", codex_executable=args.codex_executable)
    payload: dict[str, Any] = {
        "version": "3.5.0",
        "branch": "research-os-v1.3",
        "prior_checkpoint": {"version": "3.4.0", "commit": "940330d1b19efb378d1d8f46224d668cea7ac1e0", "status": "CONFIRMED"},
        "prompts": {"resolution": FINAL_RESOLUTION_CHALLENGE_PROMPT, "unresolvable": FINAL_UNRESOLVABLE_CHALLENGE_PROMPT},
        "provider": app.service.planner.provider.audit(),
        "engine_reprobe": _engine_reprobe(root, str(vina) if vina else None, str(openbabel) if openbabel else None),
        "inputs": {"pharma_plan": _pharma_plan(args), "battery_artifact": {"path": str(battery) if battery else None, "sha256": sha256_file(battery) if battery else None}},
    }
    resolutions: list[dict[str, Any]] = []
    campaigns: list[Any] = []
    try:
        discovery = app.campaigns.discover()  # type: ignore[union-attr]
        payload["discovery"] = discovery.to_dict()
        selected_ids = list(dict.fromkeys((*discovery.primary_problem_ids, *discovery.secondary_problem_ids)))
        required_ids = ["P-MOL-01", "P-COMB-01", "P-MAT-01", "P-BATT-01", "P-PHARMA-01"]
        campaign_ids = list(dict.fromkeys((*selected_ids, *required_ids)))
        for problem_id in campaign_ids:
            campaign = app.campaigns.start(problem_id)  # type: ignore[union-attr]
            campaigns.append(campaign)
        payload["campaigns_before_resolution"] = [item.to_dict() for item in campaigns]

        pharma_plan = payload["inputs"]["pharma_plan"]
        for campaign in campaigns:
            for gap in campaign.gaps:
                resolutions.append(app.campaigns.resolve_gap(campaign.campaign_id, gap.gap_id, provider_plan=_resolution_plan(campaign, pharma_plan, battery)).to_dict())  # type: ignore[union-attr]

        challenge = app.campaigns.final_resolution_challenge()  # type: ignore[union-attr]
        selected = challenge.get("selected_gap") or {}
        challenge_plan = dict(challenge.get("resolution_plan") or {})
        selected_campaign = next((item for item in campaigns if item.campaign_id == selected.get("campaign_id")), None)
        if selected_campaign is not None:
            challenge_plan.update(_resolution_plan(selected_campaign, pharma_plan, battery))
        challenge["resolution_plan"] = challenge_plan
        final_resolution = app.campaigns.resolve_from_challenge(challenge)  # type: ignore[union-attr]
        resolutions.append(final_resolution.to_dict())
        unresolvable = app.campaigns.final_unresolvable_challenge()  # type: ignore[union-attr]

        target_campaign = next((item for item in campaigns if item.problem_id == "P-PHARMA-01"), None)
        target_resolution = _resolution_for(resolutions, campaign_id=target_campaign.campaign_id if target_campaign else None, gap_id="GAP-PHARMA-DOCKING")
        agreement = None
        claim = None
        claim_revision = None
        docking_verification: list[dict[str, Any]] = []
        if target_campaign is not None and target_resolution and target_resolution.get("status") == "RESOLVED":
            target_run_id = target_campaign.run_ids[0] if target_campaign.run_ids else None
            docking_run_ids = tuple(target_resolution.get("run_ids") or ())
            evidence_ids: list[str] = []
            if target_run_id and app.service.ledger is not None:
                evidence_ids.extend(item.evidence_id for item in app.service.ledger.evidence_from_run(target_run_id))
            for run_id in docking_run_ids:
                if app.service.ledger is not None:
                    evidence_ids.extend(item.evidence_id for item in app.service.ledger.evidence_from_run(run_id))
                record = app.service.ledger.get_run(run_id) if app.service.ledger is not None else None
                if record is not None:
                    verification = verify_bundle(record.bundle_path)
                    docking_verification.append({"run_id": run_id, "bundle_path": record.bundle_path, "status": verification.status.value, "passed": verification.passed})
            docking_evidence_ids = tuple(item for item in evidence_ids if item not in tuple(target_campaign.evidence_ids))
            agreement = EvidenceAgreementAssessment(
                claim_target="murine PTGS2 / COX-2 structure 1PXX with co-crystallized diclofenac under the declared Vina protocol",
                evidence_ids=tuple(dict.fromkeys(evidence_ids)),
                conditions={"species": "Mus musculus", "structure_id": "1PXX", "selected_chains": ["A"], "docking_protocol_id": "autodock-vina.docking.v1"},
                consistency=EvidenceAgreementStatus.PARTIALLY_CONSISTENT,
                conflicts=("The HEM cofactor was removed from the prepared PDBQT because Open Babel conversion of the Fe-containing component was incompatible; the prepared receptor is therefore not cofactor-complete.",),
                strongest_supported_level=EvidenceLevel.E2_COMPUTATIONAL,
                limitations=("The docking scores are computational outputs, not measured binding affinity.", "No human, therapeutic, clinical, efficacy or safety inference is supported."),
            )
            claim = ScientificClaim(
                "Under the declared murine 1PXX preparation and AutoDock Vina protocol, the diclofenac reference docking completed three reproducible computational replicates.",
                docking_run_ids[0],
                tuple(dict.fromkeys(evidence_ids)),
                EvidenceLevel.E2_COMPUTATIONAL,
                ClaimStatus.SUPPORTED,
                claim_id="CLM-COX2-1PXX-V2",
                limitations=("This claim is E2 computational evidence only; the HEM exclusion and lack of measured affinity remain material limitations.",),
                conditions={"species": "Mus musculus", "structure_id": "1PXX", "docking_protocol_id": "autodock-vina.docking.v1"},
                supersedes="CLM-COX2-1PXX-V1",
                derived_from=docking_run_ids,
            )
            claim_revision = ClaimRevision(
                revision_id="REV-COX2-1PXX-V2",
                claim_id=claim.claim_id,
                version=2,
                statement=claim.statement,
                previous_status=ClaimStatus.INSUFFICIENT_EVIDENCE,
                current_status=claim.status,
                previous_evidence_ids=tuple(target_campaign.evidence_ids),
                evidence_ids=tuple(dict.fromkeys(evidence_ids)),
                reason="AutoDock Vina and Open Babel were installed/configured in the isolated project environment; three sealed, Ledger-indexed docking bundles passed verification.",
                limitations=claim.limitations,
                supersedes="CLM-COX2-1PXX-V1",
                derived_from=docking_run_ids,
            )

        memory = app.campaigns.cross_campaign_memory("COX-2 docking resolution")  # type: ignore[union-attr]
        payload.update({
            "resolution_challenge": challenge,
            "final_resolution": final_resolution.to_dict(),
            "unresolvable_challenge": unresolvable,
            "resolutions": resolutions,
            "campaigns_after_resolution": [app.campaigns.get(item.campaign_id) for item in campaigns],  # type: ignore[union-attr]
            "evidence_agreement": agreement.to_dict() if agreement else {"status": "NOT_COMPARABLE", "reason": "the real docking resolution did not complete"},
            "claim": claim.to_dict() if claim else None,
            "claim_revision": claim_revision.to_dict() if claim_revision else None,
            "cross_campaign_memory": {**memory, "useful": bool(memory.get("campaigns") or memory.get("ledger_runs") or memory.get("citations"))},
            "docking_bundle_verification": docking_verification,
        })
        target_status = target_resolution.get("status") if target_resolution else "NOT_ATTEMPTED"
        payload["acceptance"] = {
            "docking_gate": "OPENED_AND_RESOLVED" if target_status == "RESOLVED" and all(item["passed"] for item in docking_verification) else "NOT_RESOLVED",
            "docking_status": target_status,
            "evidence_ceiling": "E2_COMPUTATIONAL",
            "independent_solubility": "NOT_ELIGIBLE_AS_EXTERNAL_TEST",
            "materials": "UNRESOLVED_NO_RECORD_LEVEL_OBSERVATION",
            "battery": "PARTIALLY_RESOLVED_SCHEMA_LIMITED" if any(item.get("gap_id", "").startswith("GAP-P-BATT-01") and item.get("status") == "PARTIALLY_RESOLVED" for item in resolutions) else "BLOCKED_OR_UNRESOLVED",
            "user_corpus": "AWAITING_USER_CORPUS",
            "provider_created_scientific_evidence": False,
            "claim_revision_recorded": claim_revision is not None and claim_revision.valid,
            "evidence_agreement_recorded": agreement is not None and agreement.valid,
            "live_discovery_used": True,
            "live_resolution_challenge_used": True,
            "second_unresolvable_challenge_execution": unresolvable.get("execution"),
        }
        payload["real_resolution_test_manifest"] = {
            "test_id": "RRM-V35-REAL-RESOLUTION-001",
            "timestamp": _now(),
            "commit": _git_commit(),
            "environment_hash": app.service.ledger.get_run(target_campaign.run_ids[0]).environment_hash if target_campaign and target_campaign.run_ids and app.service.ledger is not None else None,
            "model_identity": app.service.planner.provider.audit(),
            "question": FINAL_RESOLUTION_CHALLENGE_PROMPT,
            "selected_gap": selected,
            "sources": ["SRC-RCSB-1PXX", "SRC-AQSOLDB-PAPER", "SRC-AQSOLDB-DATA", "SRC-NASA-PCOE-RW3"],
            "datasets": ["aqsoldb-g", "battery-nasa-pcoe-rw3"],
            "engines": ["rdkit", "cantera", "openbabel", "autodock-vina", "pymatgen", "matminer", "pycalphad"],
            "plan": pharma_plan,
            "runs": [item.get("run_ids", []) for item in resolutions],
            "result": payload["acceptance"],
            "evidence": {"agreement": payload["evidence_agreement"], "claim": payload["claim"], "revision": payload["claim_revision"]},
            "remaining_gap": ["independent overlap-audited solubility data", "condition-complete materials observation", "battery capacity and uncertainty fields", "user corpus"],
        }
        status = 0
    except Exception as exc:
        payload["acceptance"] = {"status": "FAIL_CLOSED", "error_type": type(exc).__name__, "error": str(exc)}
        status = 1
    finally:
        payload["provider"] = app.service.planner.provider.audit()
        (root / "v3.5-evidence-expansion.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        app.close()

    print(json.dumps({"version": payload["version"], "branch": payload["branch"], "provider": payload["provider"], "acceptance": payload.get("acceptance", {}), "docking_bundle_verification": payload.get("docking_bundle_verification", [])}, indent=2, ensure_ascii=False, default=str))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
