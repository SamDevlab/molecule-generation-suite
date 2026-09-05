import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / ".research-os-live-5.0" / "master-real-research-validation.json"


def _report():
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_v50_attempt_preserves_required_operational_counts():
    report = _report()
    counts = report["counts"]
    assert counts["programs"] >= 12
    assert counts["codex_dynamic_programs"] >= 4
    assert counts["systematic_questions"] >= 150
    assert counts["codex_generated_questions"] >= 50
    assert counts["total_questions"] >= 200
    assert counts["reproduced_cases"] >= 30
    assert counts["stress_cases"] >= 75


def test_v50_attempt_keeps_live_blocker_explicit_without_claiming_pass():
    report = _report()
    assert report["status"] != "PASS"
    assert report["problem_discovery"]["status"] == "LIVE_CODEX_UNAVAILABLE"
    assert report["review_panel"]["status"] == "FAIL"
    assert report["final_exam"]["status"] == "FAIL"
    assert report["scientific_audit"]["status"] == "PASS"
    assert report["security_audit"]["status"] == "PASS"


def test_v50_companion_artifacts_exist():
    base = ROOT / ".research-os-live-5.0"
    for name in ("final-scientific-exam.json", "reviewer-panel.json", "reproduction-matrix.json"):
        assert (base / name).is_file()

