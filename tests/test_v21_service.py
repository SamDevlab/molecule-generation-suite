from research_os.candidates import CandidateEvaluation, CandidateRanking
from research_os.oracle import OraclePlanner
from research_os.service import OracleService, ResearchJobStatus


def test_chat_service_exposes_plan_and_progress_without_lab_imports():
    response = OracleService(OraclePlanner()).ask("Calculate properties for ethanol")
    assert response.job.status is ResearchJobStatus.COMPLETED
    assert response.planning.question.question_id == response.job.question_id
    assert response.planning.plan.steps[0].lab == "MoleculeLab"
    assert {event.stage for event in response.job.progress} >= {"question_interpreted", "knowledge_retrieved", "plan_created", "plan_validated"}


def test_continue_research_creates_new_job_with_rerun_lineage():
    service = OracleService()
    first = service.ask("Calculate properties for ethanol")
    second = service.continue_research(first.job.job_id)
    assert second.job.job_id != first.job.job_id
    assert second.planning.plan.rerun_of == first.planning.plan.plan_id
    assert first.planning.plan.rerun_of is None


def test_ranking_explanation_uses_recorded_values_only():
    ranking = CandidateRanking.rank([CandidateEvaluation("A", "qed", 0.8, "max", "RDKit", "PASS"), CandidateEvaluation("B", "qed", 0.5, "max", "RDKit", "PASS")], metric="qed")
    explanation = OracleService().explain_ranking(ranking, "A", "B")
    assert explanation["winner"] == "A"
    assert "recorded" in explanation["reason"]

