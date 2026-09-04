from __future__ import annotations

from pathlib import Path

from research_os.service import ResearchJob, ResearchJobStatus, ResearchStore
from research_os.web import build_default_application


def test_operational_web_chat_persists_session_and_reopens(tmp_path: Path):
    app = build_default_application(tmp_path / "state")
    status, health = app.dispatch("GET", "/api/health")
    assert status == 200
    assert health["provider"]["provider"] == "CODEX_TEST"

    status, created = app.dispatch("POST", "/api/chat", {"message": "Analise esta molécula."})
    assert status == 200
    response = created["response"]
    job_id = response["job"]["job_id"]
    session_id = created["session_id"]
    assert response["answer"]["status"] == "SUPPORTED"
    assert response["answer"]["evidence"]
    assert response["job"]["session_id"] == session_id
    assert response["job"]["question_id"] == response["planning"]["question"]["question_id"]

    assert app.dispatch("GET", f"/api/jobs/{job_id}/plan")[1]["plan_id"] == response["planning"]["plan"]["plan_id"]
    assert app.dispatch("GET", f"/api/jobs/{job_id}/evidence")[1]["evidence"]
    assert app.dispatch("GET", f"/api/sessions/{session_id}")[1]["user_messages"][0]["question_id"]

    reopened = build_default_application(tmp_path / "state")
    assert reopened.dispatch("GET", f"/api/jobs/{job_id}")[1]["answer"]["status"] == "SUPPORTED"
    assert reopened.dispatch("GET", "/api/sessions")[1]["sessions"]
    assert reopened.service.memory.search("Analise esta molécula.")
    continuation_status, continuation = reopened.dispatch("POST", f"/api/jobs/{job_id}/continue", {})
    assert continuation_status == 200
    assert continuation["response"]["planning"]["plan"]["rerun_of"] == response["planning"]["plan"]["plan_id"]
    assert continuation["response"]["job"]["job_id"] != job_id
    natural_status, natural = reopened.dispatch("POST", "/api/chat", {"message": "Continue essa pesquisa.", "session_id": session_id})
    assert natural_status == 200
    assert natural["response"]["planning"]["plan"]["rerun_of"] == continuation["response"]["planning"]["plan"]["plan_id"]
    assert reopened.dispatch("GET", f"/api/jobs/{job_id}/evidence?minimum=E4_CURATED_EXPERIMENTAL")[1]["status"] == "INSUFFICIENT_EVIDENCE"
    app.close()
    reopened.close()


def test_operational_web_exposes_views_engines_and_safe_import_review(tmp_path: Path):
    app = build_default_application(tmp_path / "state")
    status, page = app.dispatch("GET", "/")
    assert status == 200
    assert page["__static_path"].endswith("web\\index.html") or page["__static_path"].endswith("web/index.html")

    engines = app.dispatch("GET", "/api/engines")[1]["engines"]
    assert {item["engine_id"] for item in engines} >= {"rdkit", "cantera", "openbabel", "autodock-vina", "pymatgen", "matminer", "pycalphad"}
    assert all({"boundary", "available", "configured", "executed", "reference_validated"} <= set(item) for item in engines)

    imported = app.dispatch("POST", "/api/knowledge/import", {"title": "User note", "text": "# Method\nA user-provided note requires review before verification.", "url": "https://example.invalid/user-note"})
    assert imported[0] == 201
    queue = app.dispatch("GET", "/api/knowledge/review-queue")[1]
    assert queue["status"] == "REVIEW_REQUIRED"
    assert queue["items"]
    review_id = queue["items"][0]["review_id"]
    reviewed = app.dispatch("POST", f"/api/knowledge/review/{review_id}", {"status": "VERIFY"})
    assert reviewed[0] == 200
    assert reviewed[1]["item"]["status"] == "VERIFIED"

    response = app.dispatch("POST", "/api/chat", {"message": "Full-text retrieval"})[1]["response"]
    job_id = response["job"]["job_id"]
    assert app.dispatch("GET", f"/api/jobs/{job_id}/sources")[1]["sources"]
    source_id = app.dispatch("GET", "/api/knowledge/sources")[1]["sources"][0]["source_id"]
    assert app.dispatch("GET", f"/api/knowledge/sources/{source_id}")[1]["source"]["source_id"] == source_id
    assert app.dispatch("GET", f"/api/runs/{response['answer']['run_ids'][0]}")[0] == 200
    app.close()


def test_operational_web_keeps_explanation_fail_closed_without_recorded_ranking(tmp_path: Path):
    app = build_default_application(tmp_path / "state")
    status, payload = app.dispatch("POST", "/api/explain", {"message": "Por que A ficou acima de B?"})
    assert status == 200
    assert payload["status"] == "INSUFFICIENT_EVIDENCE"
    status, payload = app.dispatch("POST", "/api/explain", {"candidate_a": "A", "candidate_b": "B", "ranking": {"metric": "qed", "direction": "max", "evaluations": [{"candidate_id": "A", "metric": "qed", "value": 0.8, "direction": "max", "evidence": "RDKit", "status": "PASS"}]}})
    assert status == 200
    assert payload["status"] == "INSUFFICIENT_EVIDENCE"
    app.close()


def test_store_marks_interrupted_jobs_failed_after_restart(tmp_path: Path):
    store = ResearchStore(tmp_path / "experience.sqlite")
    try:
        job = ResearchJob("Q-INTERRUPTED", status=ResearchJobStatus.RUNNING)
        store.save_job(job)
        assert store.recover_interrupted_jobs() == [job.job_id]
        recovered = store.get_job(job.job_id)
        assert recovered["status"] == "FAILED"
        assert recovered["error_code"] == "PROCESS_RESTARTED"
    finally:
        store.close()
