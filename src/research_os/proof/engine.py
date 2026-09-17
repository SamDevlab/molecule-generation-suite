from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import json
from research_os.core.types import GateResult, GateStatus, RunManifest
from research_os.observability import StructuredLogger
from research_os.proof.rules import Rule


class ProofEngine:
    def __init__(self, *, logger: StructuredLogger | None = None):
        self.logger = logger or StructuredLogger()

    def evaluate(self, run: RunManifest, rules: list[Rule], *, finalize: bool = True) -> RunManifest:
        """Evaluate proof gates, optionally leaving a successful run open.

        Labs that still need to execute a scientific calculation or attach
        evidence after their preflight gates must pass ``finalize=False`` and
        call :meth:`finalize` only after that work succeeds.  The default stays
        ``True`` for validation-only callers and backward compatibility.
        """
        if run.lifecycle.value == "CREATED":
            run.start()
        # fail-closed: stop at first non-PASS result
        for rule in rules:
            try:
                result = rule.evaluator(run.inputs, run.evidence)
            except Exception as exc:
                result = GateResult(
                    "GATE-RULE-EVALUATION",
                    rule.rule_id,
                    GateStatus.FAIL,
                    "rule evaluation raised an exception",
                    diagnostics={"error_type": type(exc).__name__, "error": str(exc)},
                )
            run.gates.append(result)
            self.logger.emit(
                "rule_evaluated",
                run_id=run.run_id,
                lab=run.lab,
                status=result.status.value,
                message=result.reason,
                fields={"rule_id": result.rule_id},
            )
            if result.status.value != "PASS":
                break
        if run.first_loss is None and finalize:
            run.complete()
        return run

    def finalize(self, run: RunManifest) -> RunManifest:
        """Complete a staged run only when no gate has recorded FIRST_LOSS."""
        if run.first_loss is None and run.lifecycle.value == "RUNNING":
            run.complete()
        return run

    def write_ledger(self, run: RunManifest, root: str | Path) -> Path:
        target = Path(root) / run.run_id
        target.mkdir(parents=True, exist_ok=False)
        manifest = asdict(run)
        manifest["digest"] = run.digest()
        (target / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
        return target
