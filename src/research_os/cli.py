"""CLI dispatcher for Research OS declarative experiments and hardening utilities.

Pre-5.1 commands are delegated to the preserved legacy CLI implementation.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
from typing import Sequence

from research_os.experiments import (
    ExperimentEngine,
    compare_experiment_runs,
    inspect_experiment_run,
    reproduce_experiment_run,
    verify_experiment_run,
)
from research_os.campaigns.declarative import (
    DeclarativeCampaignRunner,
    inspect_campaign_execution,
    verify_campaign_execution,
)
from research_os.legacy_runtime import biolab_preflight
from research_os.artifacts import ModelArtifactManifest
from research_os.datasets import DatasetManifest, DatasetRegistry
from research_os.ml.registry import ModelRegistry, ModelStage


def _json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _experiment_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-os run", description="Research OS reproducible run utilities")
    commands = parser.add_subparsers(dest="run_command", required=True)

    run = commands.add_parser("experiment", help="run a declarative experiment protocol")
    run.add_argument("protocol")
    run.add_argument("--output", default="runs")

    verify = commands.add_parser("experiment-verify", help="verify a declarative experiment package")
    verify.add_argument("run")

    inspect = commands.add_parser("experiment-inspect", help="inspect a verified declarative experiment package")
    inspect.add_argument("run")

    compare = commands.add_parser("experiment-compare", help="compare compatible declarative experiment packages")
    compare.add_argument("left")
    compare.add_argument("right")

    reproduce = commands.add_parser("experiment-reproduce", help="reproduce a verified declarative experiment package")
    reproduce.add_argument("run")
    reproduce.add_argument("--output", default="reproduced-runs")
    return parser


def _legacy_preflight_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-os legacy-preflight",
        description="Resolve external executables required by preserved Biolab workflows",
    )
    parser.add_argument("base_dir", nargs="?", default="Biolab")
    return parser


def _model_registry_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-os registry model", description="Durable model provenance registry")
    commands = parser.add_subparsers(dest="model_command", required=True)

    register = commands.add_parser("register", help="register a model manifest and its bytes")
    register.add_argument("manifest")
    register.add_argument("--root", required=True)
    register.add_argument("--stage", choices=[stage.value for stage in ModelStage], default=ModelStage.CANDIDATE.value)

    verify = commands.add_parser("verify", help="verify model record, artifact and provenance")
    verify.add_argument("model_id")
    verify.add_argument("--root", required=True)

    inspect = commands.add_parser("inspect", help="inspect a model record without loading model bytes")
    inspect.add_argument("model_id")
    inspect.add_argument("--root", required=True)

    listing = commands.add_parser("list", help="list model records metadata-only")
    listing.add_argument("--root", required=True)
    return parser


def _is_experiment_command(argv: Sequence[str]) -> bool:
    return len(argv) >= 2 and argv[0] == "run" and argv[1] in {
        "experiment",
        "experiment-verify",
        "experiment-inspect",
        "experiment-compare",
        "experiment-reproduce",
    }


def _is_model_registry_command(argv: Sequence[str]) -> bool:
    return len(argv) >= 2 and argv[0] == "registry" and argv[1] == "model"


def _dataset_registry_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-os registry dataset", description="Durable dataset provenance registry")
    commands = parser.add_subparsers(dest="dataset_command", required=True)
    register = commands.add_parser("register", help="register a dataset manifest and managed/external artifact")
    register.add_argument("manifest")
    register.add_argument("--root", required=True)
    register.add_argument("--artifact-mode", choices=("managed", "external"), default="managed")
    verify = commands.add_parser("verify", help="verify dataset record, artifact and lineage")
    verify.add_argument("dataset_id")
    verify.add_argument("version", nargs="?", default=None)
    verify.add_argument("--root", required=True)
    inspect = commands.add_parser("inspect", help="inspect dataset provenance without loading records")
    inspect.add_argument("dataset_id")
    inspect.add_argument("version", nargs="?", default=None)
    inspect.add_argument("--root", required=True)
    listing = commands.add_parser("list", help="list dataset records metadata-only")
    listing.add_argument("--root", required=True)
    return parser


def _is_dataset_registry_command(argv: Sequence[str]) -> bool:
    return len(argv) >= 2 and argv[0] == "registry" and argv[1] == "dataset"


def _campaign_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-os campaign", description="Static declarative multi-experiment campaign utilities")
    commands = parser.add_subparsers(dest="campaign_command", required=True)
    plan = commands.add_parser("plan", help="resolve child protocols without executing experiments")
    plan.add_argument("protocol")
    validate = commands.add_parser("validate", help="validate a campaign protocol without executing experiments")
    validate.add_argument("protocol")
    run = commands.add_parser("run", help="run a predeclared campaign through the Experiment Engine")
    run.add_argument("protocol")
    run.add_argument("--output", required=True)
    verify = commands.add_parser("verify", help="verify a completed campaign package")
    verify.add_argument("root")
    inspect = commands.add_parser("inspect", help="inspect a campaign package without loading model bytes")
    inspect.add_argument("root")
    return parser


def _is_campaign_command(argv: Sequence[str]) -> bool:
    return len(argv) >= 1 and argv[0] == "campaign"


def main(argv: Sequence[str] | None = None) -> int:
    import sys

    values = list(sys.argv[1:] if argv is None else argv)

    if values and values[0] == "legacy-preflight":
        args = _legacy_preflight_parser().parse_args(values[1:])
        result = biolab_preflight(args.base_dir)
        _json(result)
        return 0 if result["status"] == "PASS" else 1

    if _is_model_registry_command(values):
        args = _model_registry_parser().parse_args(values[2:])
        try:
            registry = ModelRegistry(root=args.root)
            if args.model_command == "register":
                manifest_path = Path(args.manifest)
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest = ModelArtifactManifest.from_mapping(raw)
                if manifest.model_file and not Path(manifest.model_file).is_absolute():
                    manifest = replace(manifest, model_file=str((manifest_path.parent / manifest.model_file).resolve()))
                record = registry.register(manifest, stage=args.stage)
                _json({"record": record.to_dict(), "verification": registry.verify(str(record.record_id)).to_dict()})
                return 0
            if args.model_command == "verify":
                result = registry.verify(args.model_id)
                _json(result.to_dict())
                return 0 if result.status == "PASS" else 1
            if args.model_command == "inspect":
                _json(registry.inspect(args.model_id))
                return 0
            if args.model_command == "list":
                _json([record.to_dict() for record in registry.list()])
                return 0
            return 2
        except (KeyError, ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
            _json({"error": str(exc), "first_loss": getattr(exc, "first_loss", None)})
            return 1

    if _is_dataset_registry_command(values):
        args = _dataset_registry_parser().parse_args(values[2:])
        try:
            registry = DatasetRegistry(root=args.root)
            if args.dataset_command == "register":
                manifest_path = Path(args.manifest)
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and raw.get("schema_version") == "research-os.dataset-record.v1":
                    raise ValueError("register expects a manifest, not an already-enveloped dataset record")
                manifest = DatasetManifest.from_mapping(raw)
                if manifest.artifact_path and not Path(manifest.artifact_path).is_absolute():
                    manifest = replace(manifest, artifact_path=str((manifest_path.parent / manifest.artifact_path).resolve()))
                registered = registry.register(manifest, artifact_mode=args.artifact_mode)
                _json({"manifest": registered.to_dict(), "record": registry.get_record(registered.dataset_id, registered.version).to_dict(), "verification": registry.verify(registered.dataset_id, registered.version).to_dict()})
                return 0
            if args.dataset_command == "verify":
                result = registry.verify(args.dataset_id, args.version)
                _json(result.to_dict())
                return 0 if result.status == "PASS" else 1
            if args.dataset_command == "inspect":
                _json(registry.inspect(args.dataset_id, args.version))
                return 0
            if args.dataset_command == "list":
                _json([record.to_dict() for record in registry.list_records()])
                return 0
            return 2
        except (KeyError, ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
            _json({"error": str(exc), "first_loss": getattr(exc, "first_loss", None)})
            return 1

    if _is_campaign_command(values):
        args = _campaign_parser().parse_args(values[1:])
        try:
            runner = DeclarativeCampaignRunner()
            if args.campaign_command in {"plan", "validate"}:
                _json(runner.plan(args.protocol).to_dict())
                return 0
            if args.campaign_command == "run":
                _json(runner.run(args.protocol, args.output))
                return 0
            if args.campaign_command == "verify":
                result = verify_campaign_execution(args.root)
                _json(result.to_dict())
                return 0 if result.status == "PASS" else 1
            if args.campaign_command == "inspect":
                _json(inspect_campaign_execution(args.root))
                return 0
            return 2
        except (KeyError, ValueError, OSError, RuntimeError) as exc:
            _json({"error": str(exc), "first_loss": getattr(exc, "first_loss", None)})
            return 1

    if not _is_experiment_command(values):
        from research_os.cli_legacy import main as legacy_main

        return legacy_main(values)

    args = _experiment_parser().parse_args(values[1:])
    try:
        if args.run_command == "experiment":
            result = ExperimentEngine().run(args.protocol, args.output)
            _json(result.to_dict())
            return 0
        if args.run_command == "experiment-verify":
            result = verify_experiment_run(args.run)
            _json(result.to_dict())
            return 0 if result.status == "PASS" else 1
        if args.run_command == "experiment-inspect":
            _json(inspect_experiment_run(args.run))
            return 0
        if args.run_command == "experiment-compare":
            _json(compare_experiment_runs(args.left, args.right))
            return 0
        if args.run_command == "experiment-reproduce":
            _json(reproduce_experiment_run(args.run, args.output).to_dict())
            return 0
        return 2
    except (KeyError, ValueError, OSError, RuntimeError) as exc:
        _json({"error": str(exc), "rule_id": getattr(exc, "rule_id", None)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
