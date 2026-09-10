"""CLI dispatcher for Research OS 5.1 declarative experiments.

All pre-5.1 commands are delegated to the preserved legacy CLI implementation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from research_os.experiments import (
    ExperimentEngine,
    compare_experiment_runs,
    inspect_experiment_run,
    verify_experiment_run,
)


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
    return parser


def _is_experiment_command(argv: Sequence[str]) -> bool:
    return len(argv) >= 2 and argv[0] == "run" and argv[1] in {
        "experiment",
        "experiment-verify",
        "experiment-inspect",
        "experiment-compare",
    }


def main(argv: Sequence[str] | None = None) -> int:
    import sys

    values = list(sys.argv[1:] if argv is None else argv)
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
        return 2
    except (KeyError, ValueError, OSError, RuntimeError) as exc:
        _json({"error": str(exc), "rule_id": getattr(exc, "rule_id", None)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
