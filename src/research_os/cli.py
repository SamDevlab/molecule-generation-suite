"""Small CLI surface for inspecting and verifying Research OS artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from research_os.bundles import verify_bundle
from research_os.datasets import DatasetRegistry, inspect_dataset
from research_os.environment import capture_environment
from research_os.golden import run_golden_workflow
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
    run_verify = run_commands.add_parser("verify")
    run_verify.add_argument("bundle")

    bundle = commands.add_parser("bundle", help="verify a sealed ResearchBundle")
    bundle_commands = bundle.add_subparsers(dest="bundle_command", required=True)
    bundle_verify = bundle_commands.add_parser("verify")
    bundle_verify.add_argument("bundle")

    commands.add_parser("labs", help="list registered labs")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

