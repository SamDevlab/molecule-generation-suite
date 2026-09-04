"""Research OS 3.4 live gap-resolution acceptance.

The local Codex process selects and narrates only.  Labs, hashes, runs,
bundles, conditions and resolution statuses are produced by Research OS.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from research_os.campaigns import FINAL_RESOLUTION_CHALLENGE_PROMPT, FINAL_UNRESOLVABLE_CHALLENGE_PROMPT
from research_os.web.server import build_default_application


BATTERY_URL = "https://data.nasa.gov/docs/legacy/ames/3.Battery_Uniform_Distribution_Variable_Charge_Room_Temp_DataSet_2Post.zip"


def _retrieve_battery(root: Path) -> Path:
    target = root / "public-artifacts" / "nasa-pcoe-rw3.zip"
    manifest = root / "public-artifacts" / "nasa-pcoe-rw3.manifest.json"
    if target.is_file() and manifest.is_file():
        return target
    from retrieve_public_battery import retrieve
    retrieve(BATTERY_URL, target, manifest, title="Randomized Battery Usage 3: Room Temperature Variable Recharge Random Walk", source_id="SRC-NASA-PCOE-RW3", license_name="https://www.usa.gov/government-works")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Research OS 3.4 real resolution challenge")
    parser.add_argument("--data-root", default=str(REPO_ROOT / ".research-os-live-3.4"))
    parser.add_argument("--codex-executable", default=None)
    parser.add_argument("--battery-artifact", default=None)
    args = parser.parse_args()
    root = Path(args.data_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    artifact = Path(args.battery_artifact).resolve() if args.battery_artifact else _retrieve_battery(root)
    app = build_default_application(root, oracle_mode="live", codex_executable=args.codex_executable)
    payload: dict[str, object] = {"version": "3.4.0", "branch": "research-os-v1.3", "provider": app.service.planner.provider.audit(), "prompts": {"resolution": FINAL_RESOLUTION_CHALLENGE_PROMPT, "unresolvable": FINAL_UNRESOLVABLE_CHALLENGE_PROMPT}}
    try:
        discovery = app.campaigns.discover()  # type: ignore[union-attr]
        payload["discovery"] = discovery.to_dict()
        problem_ids = (*discovery.primary_problem_ids, *discovery.secondary_problem_ids)
        campaigns = [app.campaigns.start(problem_id) for problem_id in problem_ids]  # type: ignore[union-attr]
        payload["campaigns_before_resolution"] = [item.to_dict() for item in campaigns]
        resolutions = []
        # Explicitly attempt the five milestone gaps.  Each status is an
        # honest result; a blocked attempt is part of the acceptance evidence.
        for campaign in campaigns:
            for gap in campaign.gaps:
                plan = {"artifact_path": str(artifact)} if campaign.problem_id == "P-BATT-01" else {}
                resolutions.append(app.campaigns.resolve_gap(campaign.campaign_id, gap.gap_id, provider_plan=plan).to_dict())  # type: ignore[union-attr]
        challenge = app.campaigns.final_resolution_challenge()  # type: ignore[union-attr]
        selected = challenge.get("selected_gap") or {}
        plan = dict(challenge.get("resolution_plan") or {})
        if selected.get("problem_id") == "P-BATT-01":
            plan["artifact_path"] = str(artifact)
        challenge["resolution_plan"] = plan
        final_resolution = app.campaigns.resolve_from_challenge(challenge)  # type: ignore[union-attr]
        resolutions.append(final_resolution.to_dict())
        unresolvable = app.campaigns.final_unresolvable_challenge()  # type: ignore[union-attr]
        payload["resolution_challenge"] = challenge
        payload["final_resolution"] = final_resolution.to_dict()
        payload["unresolvable_challenge"] = unresolvable
        payload["resolutions"] = resolutions
        payload["campaigns_after_resolution"] = [app.campaigns.get(item.campaign_id) for item in campaigns]  # type: ignore[union-attr]
        statuses = [str(item["status"]) for item in resolutions]
        payload["acceptance"] = {
            "candidate_count": len(discovery.candidates),
            "primary_count": len(discovery.primary_problem_ids),
            "secondary_count": len(discovery.secondary_problem_ids),
            "campaign_count": len(campaigns),
            "resolution_count": len(resolutions),
            "status_counts": {status: statuses.count(status) for status in sorted(set(statuses))},
            "live_discovery_used": True,
            "live_resolution_challenge_used": True,
            "unresolvable_challenge_execution": unresolvable.get("execution"),
            "provider_created_scientific_evidence": False,
            "artifact_path": str(artifact),
            "source_policy": "registered source metadata and archive README are DATA, not instructions",
        }
        status = 0
    except Exception as exc:
        payload["acceptance"] = {"status": "FAIL_CLOSED", "error_type": type(exc).__name__, "error": str(exc)}
        status = 1
    finally:
        payload["provider"] = app.service.planner.provider.audit()
        (root / "real-resolution-acceptance.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        app.close()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print(json.dumps({"version": payload["version"], "branch": payload["branch"], "provider": payload["provider"], "acceptance": payload.get("acceptance", {})}, indent=2, ensure_ascii=False, default=str))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
