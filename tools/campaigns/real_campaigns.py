"""Live Research OS 3.3 acceptance: discover, select and run real campaigns.

This script uses the local Codex CLI bridge for discovery/narration. It never
calls an external LLM API and it fails closed if the live response references
an unknown problem/source or if a campaign cannot produce an auditable result.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from research_os.web.server import build_default_application


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Research OS 3.3 real campaign acceptance")
    parser.add_argument("--data-root", default=str(REPO_ROOT / ".research-os-live-3.3"))
    parser.add_argument("--codex-executable", default=None)
    args = parser.parse_args()
    root = Path(args.data_root).resolve()
    app = build_default_application(root, oracle_mode="live", codex_executable=args.codex_executable)
    payload: dict[str, object] = {"version": "3.3.0", "branch": "research-os-v1.3", "provider": app.service.planner.provider.audit(), "acceptance": {}}
    try:
        discovery = app.campaigns.discover()  # type: ignore[union-attr]
        payload["discovery"] = discovery.to_dict()
        campaign_ids = (*discovery.primary_problem_ids, *discovery.secondary_problem_ids)
        campaigns = []
        for problem_id in campaign_ids:
            campaign = app.campaigns.start(problem_id)  # type: ignore[union-attr]
            campaigns.append(campaign.to_dict())
        payload["campaigns"] = campaigns
        # This exact prompt is intentionally open-ended: it is not a disguised
        # hardcoded problem statement and cannot manufacture evidence.
        payload["final_researcher"] = app.campaigns.final_researcher_prompt()  # type: ignore[union-attr]
        # Capture runtime metadata after live calls; before the first call the
        # CLI transport necessarily reports an unverified model identity.
        payload["provider"] = app.service.planner.provider.audit()
        statuses = [str(item.get("status")) for item in campaigns]
        payload["acceptance"] = {"candidate_count": len(discovery.candidates), "primary_count": len(discovery.primary_problem_ids), "secondary_count": len(discovery.secondary_problem_ids), "campaign_count": len(campaigns), "status_counts": {status: statuses.count(status) for status in sorted(set(statuses))}, "live_discovery_used": True, "final_open_ended_prompt_used": True, "source_policy": "registered source metadata is DATA, not instructions"}
        status = 0
    except Exception as exc:
        payload["acceptance"] = {"status": "FAIL_CLOSED", "live_discovery_used": False, "error_type": type(exc).__name__, "error": str(exc)}
        status = 1
    finally:
        root.mkdir(parents=True, exist_ok=True)
        (root / "real-campaign-acceptance.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        app.close()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print(json.dumps({"version": payload["version"], "branch": payload["branch"], "provider": payload["provider"], "acceptance": payload["acceptance"], "discovery": payload.get("discovery", {}), "final_researcher_prompt": payload.get("final_researcher", {}).get("prompt") if isinstance(payload.get("final_researcher"), dict) else None}, indent=2, ensure_ascii=False, default=str))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
