#!/usr/bin/env python3
"""Verify the frozen APODOCK-001 protocol without executing docking."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.docking.apodock001_protocol import (
    DEFAULT_PROTOCOL_PATH,
    build_dry_run_report,
    load_protocol,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the frozen APODOCK-001 protocol without Vina"
    )
    parser.add_argument("--spec", default=str(DEFAULT_PROTOCOL_PATH))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    report = build_dry_run_report(load_protocol(Path(args.spec)))
    output = Path(args.output) if args.output else None
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print("APODOCK-001 protocol: FROZEN")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
