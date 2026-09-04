from __future__ import annotations

import argparse
from pathlib import Path

from research_os.golden import run_golden_workflow


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the safe Research OS v1.4 golden workflow")
    parser.add_argument("--mode", choices=("stub", "real"), default="stub")
    parser.add_argument("--output", default="examples/golden_workflow/output")
    args = parser.parse_args()
    result = run_golden_workflow(Path(args.output), mode=args.mode)
    print(f"mode={result.mode} plan_id={result.plan_run.plan_id} bundle={result.bundle.root} verification={result.verification.status.value}")


if __name__ == "__main__":
    main()
