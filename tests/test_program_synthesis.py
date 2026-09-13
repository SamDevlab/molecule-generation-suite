from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research_os.cli import main
from research_os.core.hashing import sha256_file
from research_os.programs import DeclarativeProgramRunner, ProgramSynthesisError, ResearchProgramStore, synthesize_program, verify_program_synthesis


def _dataset(path: Path) -> None:
    rows = ["x1,x2,y"]
    for index in range(20):
        rows.append(f"{index},{(index * 3) % 7},{1.0 + 2.0 * index - 0.25 * ((index * 3) % 7)}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _campaign(path: Path, child: Path, campaign_id: str, *, bad: bool = False) -> None:
    child.write_text(yaml.safe_dump({
        "protocol": "research-os.declarative-experiment.v1",
        "experiment": {"id": campaign_id, "task": "regression", "seed": 42},
        "dataset": {"adapter": "csv", "path": "data.csv", "target": "y", "features": ["x1", "x2"]},
        "split": {"strategy": "random", "train_fraction": 0.8},
        "models": [{"id": "ols", "adapter": "linear_regression"}],
        "metrics": ["mae", "not-registered" if bad else "r2"],
        "evidence": {"require_dataset_hash": True, "require_protocol_hash": True, "fail_closed": True},
    }, sort_keys=False), encoding="utf-8")
    path.write_text(yaml.safe_dump({
        "schema_version": "research-os.campaign.v1",
        "campaign": {"title": campaign_id, "domain": "fixture", "objective": "synthesis", "hypothesis": "fixture"},
        "limits": {"max_runs": 1, "max_failures": 1},
        "execution": {"mode": "static", "retry_count": 0, "failure_policy": "continue_independent"},
        "experiments": [{"experiment_id": "experiment", "protocol": child.name}],
        "analysis": {"multiplicity": {"family_id": f"family-{campaign_id}", "mode": "DESCRIPTIVE_ONLY", "comparisons": []}},
    }, sort_keys=False), encoding="utf-8")


def _program(path: Path, campaigns: list[dict], *, claim_campaigns: list[str], minimum: str = "E2_COMPUTATIONAL", decision: dict | None = None, prior_claim: dict | None = None) -> None:
    ids = [item["local_id"] for item in campaigns]
    claim = {
        "local_id": "claim-x",
        "statement": "the declared fixture condition supports the target claim",
        "minimum_evidence_level": minimum,
        "campaigns": claim_campaigns,
        "comparability": {"required_dimensions": ["endpoint", "metric", "threshold"]},
        "decision_rule": decision or {"type": "DESCRIPTIVE_AGREEMENT"},
    }
    if prior_claim is not None:
        claim["prior_claim"] = prior_claim
    path.write_text(yaml.safe_dump({
        "schema_version": "research-os.program.v1",
        "program": {"program_id": "PROG-SYNTH", "title": "Synthesis fixture", "domain": "fixture", "objective": "evaluate a claim", "motivation": "test claim-level synthesis", "initial_problem": "cross-campaign evidence is not synthesized", "research_questions": [{"question_id": "Q-1", "question": "is synthesis auditable?", "gap_it_attempts_to_resolve": "claim synthesis"}], "evidence_target": "E2_COMPUTATIONAL"},
        "limits": {"max_campaigns": 8, "max_runs": 12, "max_failures": 3},
        "execution": {"mode": "STATIC_PREDECLARED", "retry_count": 0, "failure_policy": "continue_independent"},
        "campaigns": campaigns,
        "synthesis": {"mode": "CLAIM_LEVEL", "primary_campaigns": ids[:1], "complementary_campaigns": ids[1:], "claims": [claim]},
    }, sort_keys=False), encoding="utf-8")


def _run_program(tmp_path: Path, *, directions: dict[str, str], dimensions: dict[str, dict] | None = None, minimum: str = "E2_COMPUTATIONAL", failed: tuple[str, ...] = (), decision: dict | None = None, prior_claim: dict | None = None) -> tuple[Path, dict]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    _dataset(tmp_path / "data.csv")
    campaign_specs = []
    for local_id in directions:
        campaign_path = tmp_path / f"{local_id}.yaml"
        child_path = tmp_path / f"{local_id}-child.yaml"
        _campaign(campaign_path, child_path, local_id, bad=local_id in failed)
        campaign_specs.append({"local_id": local_id, "protocol_path": campaign_path.name})
    _program(tmp_path / "program.yaml", campaign_specs, claim_campaigns=list(directions), minimum=minimum, decision=decision, prior_claim=prior_claim)
    root = tmp_path / "execution"
    manifest = DeclarativeProgramRunner().run(tmp_path / "program.yaml", root)
    input_campaigns = []
    for local_id in directions:
        child = manifest["campaigns"][local_id]
        evidence = []
        if child["status"] == "COMPLETED":
            bundle_path = Path(child["root"]) / "campaign-bundle.json"
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            evidence_id = bundle["child_evidence_refs"][0]["sha256"]
            evidence.append({"claim_local_id": "claim-x", "evidence_id": evidence_id, "level": "E2_COMPUTATIONAL", "contribution": directions[local_id], "status": "AVAILABLE", "dimensions": (dimensions or {}).get(local_id, {"endpoint": "fixture", "metric": "accuracy", "threshold": 0.8}), "negative_result": directions[local_id] == "CONTRADICTS", "limitations": []})
            bundle_sha256 = sha256_file(bundle_path)
        else:
            evidence.append({"claim_local_id": "claim-x", "contribution": "UNAVAILABLE", "status": "UNAVAILABLE", "dimensions": {}, "negative_result": False, "limitations": ["Campaign execution failed before evidence was produced."]})
            bundle_sha256 = None
        input_campaigns.append({"local_id": local_id, "campaign_execution_id": child["campaign_execution_id"], "campaign_bundle_id": child["campaign_bundle_id"], "bundle_sha256": bundle_sha256, "evidence": evidence})
    (root / "synthesis-input.json").write_text(json.dumps({"schema_version": "research-os.program-synthesis-input.v1", "program_execution_id": manifest["program_execution_id"], "campaigns": input_campaigns}, indent=2, sort_keys=True), encoding="utf-8")
    return root, manifest


def _claim(root: Path) -> dict:
    return json.loads((root / "program-synthesis.json").read_text(encoding="utf-8"))["claims"][0]


def test_consistent_synthesis_is_claim_level_and_deterministic(tmp_path: Path) -> None:
    root, _ = _run_program(tmp_path, directions={"a": "SUPPORTS", "b": "SUPPORTS", "c": "SUPPORTS"})
    first = synthesize_program(root)
    second = verify_program_synthesis(root)
    assert first["synthesis_id"].startswith("research-os.program.synthesis.v1+")
    assert _claim(root)["status"] == "SUPPORTED"
    assert _claim(root)["agreement"]["consistency"] == "CONSISTENT"
    assert second.status == "PASS"
    assert first["strongest_supported_level"] == "E2_COMPUTATIONAL"
    assert json.loads((root / "program-manifest.json").read_text(encoding="utf-8"))["evidence_level"] == "E2_COMPUTATIONAL"


def test_synthesis_identity_ignores_input_order_and_json_formatting(tmp_path: Path) -> None:
    root, _ = _run_program(tmp_path, directions={"a": "SUPPORTS", "b": "SUPPORTS", "c": "SUPPORTS"})
    first = synthesize_program(root)
    input_path = root / "synthesis-input.json"
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    payload["campaigns"] = list(reversed(payload["campaigns"]))
    for campaign in payload["campaigns"]:
        campaign["evidence"] = list(reversed(campaign["evidence"]))
    input_path.write_text(json.dumps(payload, indent=7, sort_keys=False), encoding="utf-8")
    second = synthesize_program(root)
    assert second["synthesis_id"] == first["synthesis_id"]
    assert second["synthesis_hash"] == first["synthesis_hash"]


def test_conflict_is_preserved_and_not_majority_voted(tmp_path: Path) -> None:
    root, _ = _run_program(tmp_path, directions={"a": "SUPPORTS", "b": "CONTRADICTS", "c": "SUPPORTS"})
    result = synthesize_program(root)
    assert _claim(root)["status"] == "INSUFFICIENT_EVIDENCE"
    assert _claim(root)["agreement"]["consistency"] == "CONFLICTING"
    assert len(result["conflicts"]) == 1
    assert {"a", "b", "c"}.issubset(set(result["conflicts"][0]["campaigns"]))


def test_not_comparable_and_insufficient_level_are_distinct(tmp_path: Path) -> None:
    root, _ = _run_program(tmp_path, directions={"a": "SUPPORTS", "b": "SUPPORTS"}, dimensions={"a": {"endpoint": "fixture", "metric": "accuracy", "threshold": 0.8}, "b": {"endpoint": "fixture", "metric": "rmse", "threshold": 0.8}})
    synthesize_program(root)
    assert _claim(root)["agreement"]["consistency"] == "NOT_COMPARABLE"
    assert _claim(root)["status"] == "INSUFFICIENT_EVIDENCE"
    root2, _ = _run_program(tmp_path / "low", directions={"a": "SUPPORTS", "b": "SUPPORTS"}, minimum="E3_PHYSICS")
    synthesize_program(root2)
    assert _claim(root2)["agreement"]["consistency"] == "CONSISTENT"
    assert _claim(root2)["status"] == "INSUFFICIENT_EVIDENCE"
    assert json.loads((root2 / "program-synthesis.json").read_text(encoding="utf-8"))["strongest_supported_level"] == "E2_COMPUTATIONAL"


def test_negative_evidence_differs_from_failed_execution(tmp_path: Path) -> None:
    root, _ = _run_program(tmp_path, directions={"negative": "CONTRADICTS", "positive": "SUPPORTS", "failed": "SUPPORTS"}, failed=("failed",))
    result = synthesize_program(root)
    assert any(item["campaign_local_id"] == "negative" for item in result["negative_results"])
    assert any(item["campaign_local_id"] == "failed" for item in result["unavailable_evidence"])
    assert all(item.get("campaign_local_id") != "failed" for item in result["negative_results"])


def test_predeclared_rejection_and_append_only_claim_revision(tmp_path: Path) -> None:
    prior = {"claim_id": "CLM-HISTORICAL", "version": 1, "statement": "the declared fixture condition supports the target claim", "status": "SUPPORTED", "evidence_ids": ["old-evidence"]}
    root, _ = _run_program(tmp_path, directions={"a": "CONTRADICTS", "b": "CONTRADICTS"}, decision={"type": "PREDECLARED_DIRECTION", "required_direction": "SUPPORTS"}, prior_claim=prior)
    result = synthesize_program(root)
    assert _claim(root)["status"] == "REJECTED"
    assert result["claim_revisions"][0]["claim_id"] == "CLM-HISTORICAL"
    assert result["knowledge_gain"]["new_rejected_claim_ids"] == ["CLM-HISTORICAL"]


def test_synthesis_tampering_and_missing_member_fail_closed(tmp_path: Path) -> None:
    root, _ = _run_program(tmp_path, directions={"a": "SUPPORTS", "b": "SUPPORTS"})
    synthesize_program(root)
    synthesis_path = root / "program-synthesis.json"
    payload = json.loads(synthesis_path.read_text(encoding="utf-8"))
    payload["claims"][0]["agreement"]["conflicts"] = ["hidden"]
    synthesis_path.write_text(json.dumps(payload), encoding="utf-8")
    assert verify_program_synthesis(root).first_loss == "PROGRAM_SYNTHESIS_IDENTITY_MISMATCH"

    root2, _ = _run_program(tmp_path / "missing", directions={"a": "SUPPORTS", "b": "SUPPORTS"})
    input_path = root2 / "synthesis-input.json"
    evidence_input = json.loads(input_path.read_text(encoding="utf-8"))
    evidence_input["campaigns"] = evidence_input["campaigns"][:1]
    input_path.write_text(json.dumps(evidence_input), encoding="utf-8")
    with pytest.raises(ProgramSynthesisError, match="Campaign set"):
        synthesize_program(root2)


def test_synthesis_restart_persistence_and_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root, _ = _run_program(tmp_path, directions={"a": "SUPPORTS", "b": "SUPPORTS"})
    result = synthesize_program(root)
    assert main(["program", "verify", str(root)]) == 0
    verification = json.loads(capsys.readouterr().out)
    assert verification["status"] == "PASS"
    store = ResearchProgramStore(root / "program-store.sqlite3")
    restored = store.get_synthesis(result["synthesis_id"])
    store.close()
    assert restored["synthesis_hash"] == result["synthesis_hash"]
    assert main(["program", "inspect", str(root)]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["synthesis"]["synthesis_id"] == result["synthesis_id"]
    assert main(["program", "synthesize", str(root)]) == 0
    rerun = json.loads(capsys.readouterr().out)
    assert rerun["synthesis_id"] == result["synthesis_id"]
    assert verify_program_synthesis(root).status == "PASS"
