from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import json
from research_os.core.types import RunManifest
from research_os.proof.rules import Rule

class ProofEngine:
    def evaluate(self, run: RunManifest, rules: list[Rule]) -> RunManifest:
        # fail-closed: stop at first non-PASS result
        for rule in rules:
            result = rule.evaluator(run.inputs, run.evidence)
            run.gates.append(result)
            if result.status.value != "PASS":
                break
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
