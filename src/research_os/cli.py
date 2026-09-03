"""Small CLI surface for inspecting and verifying Research OS artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from research_os.bundles import verify_bundle
from research_os.datasets import DatasetRegistry, inspect_dataset
from research_os.environment import capture_environment
from research_os.engines import EngineRegistry
from research_os.legacy import (
    deterministic_property_parity,
    legacy_engine_audit,
    migration_decisions,
    scan_legacy,
)
from research_os.golden import run_golden_workflow
from research_os.ledger import RunRegistry
from research_os.ledger.schema import LedgerError
from research_os.ml.real_golden import run_real_data_golden
from research_os.orchestration import default_registry


def _json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-os", description="Research OS reproducibility and audit utilities")
    commands = parser.add_subparsers(dest="command", required=True)

    env = commands.add_parser("env", help="capture the execution environment")
    env_commands = env.add_subparsers(dest="env_command", required=True)
    capture = env_commands.add_parser("capture")
    capture.add_argument("--repo-root", default=None)
    capture.add_argument("--output", default=None)

    dataset = commands.add_parser("dataset", help="inspect, register and verify dataset artifacts")
    dataset_commands = dataset.add_subparsers(dest="dataset_command", required=True)
    inspect = dataset_commands.add_parser("inspect")
    inspect.add_argument("path")
    register = dataset_commands.add_parser("register")
    register.add_argument("path")
    register.add_argument("--dataset-id", required=True)
    register.add_argument("--version", required=True)
    register.add_argument("--schema-id", required=True)
    register.add_argument("--root", default="datasets")
    register.add_argument("--curated-path", default=None)
    verify = dataset_commands.add_parser("verify")
    verify.add_argument("dataset_id")
    verify.add_argument("--version", default=None)
    verify.add_argument("--root", default="datasets")

    run = commands.add_parser("run", help="execute or verify a reproducible run")
    run_commands = run.add_subparsers(dest="run_command", required=True)
    golden = run_commands.add_parser("golden")
    golden.add_argument("--mode", choices=("stub", "real"), default="stub")
    golden.add_argument("--output", default="runs/golden")
    real_data_golden = run_commands.add_parser("real-data-golden", help="run the pinned real-data validation golden path")
    real_data_golden.add_argument("--source", default=None, help="optional local AqSolDB-G CSV; defaults to the checked-in CC0-derived sample")
    real_data_golden.add_argument("--output", default="runs/real-data-golden")
    real_data_golden.add_argument("--repo-root", default=None)
    run_verify = run_commands.add_parser("verify")
    run_verify.add_argument("bundle")

    bundle = commands.add_parser("bundle", help="verify a sealed ResearchBundle")
    bundle_commands = bundle.add_subparsers(dest="bundle_command", required=True)
    bundle_verify = bundle_commands.add_parser("verify")
    bundle_verify.add_argument("bundle")

    commands.add_parser("labs", help="list registered labs")


    engines = commands.add_parser("engines", help="inspect optional scientific engines")
    engine_commands = engines.add_subparsers(dest="engines_command", required=True)
    engine_commands.add_parser("list")
    engine_commands.add_parser("probe")
    engine_show = engine_commands.add_parser("show")
    engine_show.add_argument("engine_id")
    engine_verify = engine_commands.add_parser("verify")
    engine_verify.add_argument("manifest")
    engine_commands.add_parser("audit-legacy")

    legacy = commands.add_parser("legacy", help="inventory and assess preserved legacy workflows")
    legacy_commands = legacy.add_subparsers(dest="legacy_command", required=True)
    legacy_commands.add_parser("list")
    legacy_show = legacy_commands.add_parser("show")
    legacy_show.add_argument("component")
    legacy_commands.add_parser("audit")
    legacy_parity = legacy_commands.add_parser("parity")
    legacy_parity.add_argument("--smiles", default="CCO")
    legacy_commands.add_parser("datasets")
    legacy_commands.add_parser("quarantine")
    legacy_commands.add_parser("retirement-check")

    runs = commands.add_parser("runs", help="query the persistent run ledger")
    runs_commands = runs.add_subparsers(dest="runs_command", required=True)
    runs_list = runs_commands.add_parser("list")
    runs_list.add_argument("--root", default="research-ledger")
    runs_list.add_argument("--limit", type=int, default=100)
    runs_list.add_argument("--offset", type=int, default=0)
    runs_list.add_argument("--order-by", default="created_at")
    runs_list.add_argument("--ascending", action="store_true")
    runs_show = runs_commands.add_parser("show")
    runs_show.add_argument("run_id")
    runs_show.add_argument("--root", default="research-ledger")
    runs_search = runs_commands.add_parser("search")
    runs_search.add_argument("--root", default="research-ledger")
    for name in ("status", "lab", "experiment", "workflow-id", "dataset-id", "claim-id", "model-id", "rule-id", "tag", "git-commit", "environment-hash", "date-from", "date-to"):
        runs_search.add_argument(f"--{name}", dest=name.replace("-", "_"), default=None)
    runs_search.add_argument("--limit", type=int, default=100)
    runs_search.add_argument("--offset", type=int, default=0)
    runs_search.add_argument("--order-by", default="created_at")
    runs_search.add_argument("--ascending", action="store_true")
    runs_verify = runs_commands.add_parser("verify")
    runs_verify.add_argument("run_id")
    runs_verify.add_argument("--root", default="research-ledger")
    runs_rebuild = runs_commands.add_parser("rebuild-index")
    runs_rebuild.add_argument("bundle_root")
    runs_rebuild.add_argument("--root", default="research-ledger")
    runs_lineage = runs_commands.add_parser("lineage")
    runs_lineage.add_argument("run_id")
    runs_lineage.add_argument("--root", default="research-ledger")
    runs_compare = runs_commands.add_parser("compare")
    runs_compare.add_argument("original_run_id")
    runs_compare.add_argument("rerun_run_id")
    runs_compare.add_argument("--root", default="research-ledger")

    workflows = commands.add_parser("workflows", help="query and operate workflow executions")
    workflows_commands = workflows.add_subparsers(dest="workflows_command", required=True)
    workflows_list = workflows_commands.add_parser("list")
    workflows_list.add_argument("--root", default="research-ledger")
    workflows_list.add_argument("--limit", type=int, default=100)
    workflows_list.add_argument("--offset", type=int, default=0)
    workflows_show = workflows_commands.add_parser("show")
    workflows_show.add_argument("workflow_id")
    workflows_show.add_argument("--root", default="research-ledger")
    workflows_rerun = workflows_commands.add_parser("rerun")
    workflows_rerun.add_argument("workflow_id")
    workflows_rerun.add_argument("--root", default="research-ledger")
    workflows_rerun.add_argument("--output", default=None)
    workflows_compare = workflows_commands.add_parser("compare")
    workflows_compare.add_argument("original_workflow_id")
    workflows_compare.add_argument("rerun_workflow_id")
    workflows_compare.add_argument("--root", default="research-ledger")
    workflows_lineage = workflows_commands.add_parser("lineage")
    workflows_lineage.add_argument("workflow_id")
    workflows_lineage.add_argument("--root", default="research-ledger")
    workflows_regressions = workflows_commands.add_parser("regressions")
    workflows_regressions.add_argument("original_workflow_id")
    workflows_regressions.add_argument("rerun_workflow_id")
    workflows_regressions.add_argument("--root", default="research-ledger")

    ledger = commands.add_parser("ledger", help="verify ledger structure and references")
    ledger_commands = ledger.add_subparsers(dest="ledger_command", required=True)
    ledger_verify = ledger_commands.add_parser("verify")
    ledger_verify.add_argument("--root", default="research-ledger")

    export = commands.add_parser("export", help="export ledger records as JSON")
    export_commands = export.add_subparsers(dest="export_command", required=True)
    export_json = export_commands.add_parser("json")
    export_json.add_argument("--root", default="research-ledger")
    export_json.add_argument("--output", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "env":
            manifest = capture_environment(repo_root=args.repo_root)
            if args.output:
                target = Path(args.output)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(manifest.to_json(), encoding="utf-8")
            _json(manifest.to_dict())
            return 0
        if args.command == "dataset":
            if args.dataset_command == "inspect":
                _json(inspect_dataset(args.path).to_dict())
                return 0
            if args.dataset_command == "register":
                root = Path(args.root)
                curated = args.curated_path
                if curated is None and Path(args.path).suffix.lower() == ".csv":
                    curated = str(root / "curated" / f"{args.dataset_id}-{args.version}.parquet")
                registry = DatasetRegistry(root=root)
                manifest = registry.register_dataset(dataset_id=args.dataset_id, version=args.version, schema_id=args.schema_id, path=args.path, curated_path=curated)
                _json(manifest.to_dict())
                return 0
            registry = DatasetRegistry(root=args.root)
            _json({"dataset_id": args.dataset_id, "version": args.version, "verified": registry.verify_dataset(args.dataset_id, args.version)})
            return 0
        if args.command == "run" and args.run_command == "golden":
            result = run_golden_workflow(args.output, mode=args.mode)
            _json({"plan_id": result.plan_run.plan_id, "bundle": result.bundle.root, "verification": result.verification.status.value, "claim_id": result.claim.claim_id})
            return 0 if result.verification.status.value != "FAIL" else 1
        if args.command == "run" and args.run_command == "real-data-golden":
            result = run_real_data_golden(args.output, source_path=args.source, repo_root=args.repo_root)
            _json({"run_id": result.run.run_id, "run_status": result.run.status, "dataset_id": result.ingestion.manifest.dataset_id, "rows": result.ingestion.validation.row_count, "model_id": result.ml.model_artifact.model_id, "metrics": result.ml.validation.metrics, "promotion": result.promotion.status.value, "first_loss": result.run.first_loss_rule_id, "bundle": result.bundle.root, "bundle_verification": result.verification.status.value, "ledger": result.ledger_record.to_dict()})
            return 0 if result.verification.status.value != "FAIL" else 1
        if args.command == "run" and args.run_command == "verify":
            result = verify_bundle(args.bundle)
            _json({"status": result.status.value, "first_loss": result.first_loss.rule_id if result.first_loss else None})
            return 0 if result.status.value != "FAIL" else 1
        if args.command == "bundle":
            result = verify_bundle(args.bundle)
            _json({"status": result.status.value, "first_loss": result.first_loss.rule_id if result.first_loss else None})
            return 0 if result.status.value != "FAIL" else 1
        if args.command == "labs":
            _json({"labs": list(default_registry().names())})
            return 0
        if args.command == "engines":
            registry = EngineRegistry()
            if args.engines_command in {"list", "probe"}:
                _json([item.to_dict() for item in registry.probe_all()])
                return 0
            if args.engines_command == "show":
                _json(registry.get_engine(args.engine_id).to_dict())
                return 0
            if args.engines_command == "audit-legacy":
                _json(legacy_engine_audit(Path.cwd()))
                return 0
            raw = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            if isinstance(raw, list):
                result = [registry.verify_engine(item) for item in raw]
            else:
                result = registry.verify_engine(raw)
            valid = result if isinstance(result, bool) else all(result)
            _json({"valid": valid})
            return 0 if valid else 1
        if args.command == "legacy":
            inventory = scan_legacy(Path.cwd())
            if args.legacy_command == "list":
                _json({"counts": inventory.to_dict()["counts"], "flows": [flow.to_dict() for flow in inventory.flows], "replacements": [item.to_dict() for item in inventory.replacements]})
                return 0
            if args.legacy_command == "show":
                needle = args.component.lower()
                matches = [item.to_dict() for item in inventory.components if item.component_id.lower() == needle or item.path.lower() == needle or item.path.lower().endswith(needle)]
                _json({"matches": matches})
                return 0 if matches else 1
            if args.legacy_command == "audit":
                _json(inventory.to_dict())
                return 0
            if args.legacy_command == "parity":
                _json(deterministic_property_parity(args.smiles).to_dict())
                return 0
            if args.legacy_command in {"datasets", "quarantine"}:
                _json({"policy": "eligible_for_training=false until independent provenance review", "manifests": [item.to_dict() for item in inventory.quarantine]})
                return 0
            decisions = migration_decisions(inventory)
            _json({"retirement_allowed": False, "reason": "legacy components still have active dependencies or incomplete parity/evidence gates", "decisions": [item.to_dict() for item in decisions]})
            return 0
        if args.command == "runs":
            registry = RunRegistry(args.root)
            try:
                if args.runs_command == "list":
                    _json([item.to_dict() for item in registry.list_runs(limit=args.limit, offset=args.offset, order_by=args.order_by, descending=not args.ascending)])
                elif args.runs_command == "show":
                    _json(registry.get_run(args.run_id).to_dict())
                elif args.runs_command == "search":
                    filters = {key: value for key, value in vars(args).items() if key in {"status", "lab", "experiment", "workflow_id", "dataset_id", "claim_id", "model_id", "rule_id", "tag", "git_commit", "environment_hash", "date_from", "date_to"} and value is not None}
                    _json([item.to_dict() for item in registry.search_runs(**filters, limit=args.limit, offset=args.offset, order_by=args.order_by, descending=not args.ascending)])
                elif args.runs_command == "verify":
                    result = registry.verify_run(args.run_id)
                    _json({"status": result.status.value, "gates": [{"rule_id": gate.rule_id, "status": gate.status.value, "reason": gate.reason} for gate in result.gates]})
                    return 0 if result.status.value != "FAIL" else 1
                elif args.runs_command == "rebuild-index":
                    _json(registry.rebuild_index(args.bundle_root).to_dict())
                elif args.runs_command == "lineage":
                    _json(registry.get_lineage(args.run_id).to_dict())
                elif args.runs_command == "compare":
                    _json(registry.compare_runs(args.original_run_id, args.rerun_run_id).to_dict())
                return 0
            finally:
                registry.close()
        if args.command == "workflows":
            registry = RunRegistry(args.root)
            try:
                if args.workflows_command == "list":
                    _json([item.to_dict() for item in registry.list_workflows(limit=args.limit, offset=args.offset)])
                elif args.workflows_command == "show":
                    _json(registry.get_workflow(args.workflow_id).to_dict())
                elif args.workflows_command == "rerun":
                    result = registry.rerun_workflow(args.workflow_id, output_root=args.output)
                    _json(result.to_dict())
                elif args.workflows_command == "compare":
                    _json(registry.compare_workflows(args.original_workflow_id, args.rerun_workflow_id).to_dict())
                elif args.workflows_command == "lineage":
                    workflow = registry.get_workflow(args.workflow_id)
                    _json({"workflow": workflow.to_dict(), "steps": {step.step_id: registry.get_lineage(step.run_id).to_dict() for step in workflow.steps if step.run_id}})
                elif args.workflows_command == "regressions":
                    from research_os.ledger.regression import detect_regressions
                    comparison = registry.compare_workflows(args.original_workflow_id, args.rerun_workflow_id)
                    _json([item.to_dict() for item in detect_regressions(comparison)])
                return 0
            finally:
                registry.close()
        if args.command == "ledger" and args.ledger_command == "verify":
            registry = RunRegistry(args.root)
            try:
                result = registry.verify_ledger()
                _json(result.to_dict())
                return 0 if result.status != "FAIL" else 1
            finally:
                registry.close()
        if args.command == "export" and args.export_command == "json":
            registry = RunRegistry(args.root)
            try:
                payload = {"schema_version": 2, "runs": [item.to_dict() for item in registry.list_runs(limit=1_000_000)], "workflows": [item.to_dict() for item in registry.list_workflows(limit=1_000_000)]}
                if args.output:
                    target = Path(args.output)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
                _json(payload)
                return 0
            finally:
                registry.close()
        return 2
    except (LedgerError, KeyError, ValueError, OSError) as exc:
        _json({"error": str(exc), "rule_id": getattr(exc, "rule_id", None)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
