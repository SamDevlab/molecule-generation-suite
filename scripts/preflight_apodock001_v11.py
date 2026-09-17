"""Run the APODOCK-001 v1.1 offline freeze preflight.

This script validates the frozen bundle and pristine run boundary only.  It
does not download, inspect, or invoke Vina and does not create a repository
run directory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research_os.docking.apodock001_v11 import APODOCK001V11ExecutionAdapter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--protocol",
        type=Path,
        default=ROOT / "configs" / "apodock001-protocol-freeze-v1.1.json",
    )
    parser.add_argument(
        "--v102",
        type=Path,
        default=ROOT / "configs" / "apodock001-protocol-freeze-v1.0.2.json",
    )
    parser.add_argument(
        "--bundle",
        type=Path,
        default=ROOT / "inputs" / "apodock001" / "v1.0.2",
    )
    parser.add_argument("--git-sha", default="offline")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="apodock001-v11-preflight-") as temp:
        temp_root = Path(temp)
        adapter = APODOCK001V11ExecutionAdapter(
            args.protocol,
            v102_path=args.v102,
            source_root=args.bundle,
            run_root=temp_root / "run",
            staging_root=temp_root / "staging",
            git_sha=args.git_sha,
        )
        report = adapter.preflight()

    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
