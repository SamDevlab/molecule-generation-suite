"""Explainable workflow regression findings."""

from __future__ import annotations

from typing import Any

from research_os.ledger.schema import RegressionFinding, WorkflowComparison


def detect_regressions(comparison: WorkflowComparison, *, original: Any | None = None, rerun: Any | None = None) -> tuple[RegressionFinding, ...]:
    findings: list[RegressionFinding] = []
    for difference in comparison.differences:
        category = {
            "result": "result",
            "inputs": "result",
            "config": "result",
            "datasets": "dataset",
            "environment": "environment",
            "code": "environment",
            "plan": "result",
            "metric": "metric",
            "gate": "gate",
            "claim": "claim",
            "artifact": "artifact",
        }.get(difference, "result")
        severity = "ERROR" if category in {"result", "metric", "dataset", "claim", "artifact"} else "WARN"
        findings.append(RegressionFinding(category, severity, f"workflow comparison detected {difference}", comparison.first_divergence_step, comparison.first_divergence_rule_id))
    if comparison.status.value == "REPRODUCED_WITH_ENVIRONMENT_CHANGE":
        findings.append(RegressionFinding("environment", "INFO", "workflow reproduced with an environment change"))
    if comparison.status.value == "INDETERMINATE":
        findings.append(RegressionFinding("gate", "WARN", "workflow comparison is indeterminate"))
    return tuple(findings)


def regressions(comparison: WorkflowComparison) -> tuple[RegressionFinding, ...]:
    return detect_regressions(comparison)
