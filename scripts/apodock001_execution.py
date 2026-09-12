"""Build and validate the APODOCK-001 v1.0 execution infrastructure.

The command is deliberately a dry-run tool.  It can verify the exact Linux
tools in CI and emit a no-results evidence scaffold, but it has no flag that
starts docking.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.docking.apodock001_execution import (
    APODOCK001ExecutionAdapter,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=None)
    parser.add_argument("--run-root", type=Path, default=Path("runs/apodock001-v1.0"))
    parser.add_argument("--git-sha", default="unknown")
    parser.add_argument("--vina", type=Path)
    parser.add_argument("--openbabel", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    adapter_kwargs = {"run_root": args.run_root, "git_sha": args.git_sha}
    if args.spec:
        adapter_kwargs["spec_path"] = args.spec
    adapter = APODOCK001ExecutionAdapter(**adapter_kwargs)
    vina = None
    openbabel = None
    if bool(args.vina) != bool(args.openbabel):
        parser.error("--vina and --openbabel must be supplied together")
    if args.vina and args.openbabel:
        vina, openbabel = adapter.verify_tools(
            vina_executable=args.vina,
            openbabel_executable=args.openbabel,
        )
    report = adapter.preflight(vina=vina, openbabel=openbabel)
    if args.output:
        write_json(args.output, report)
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
