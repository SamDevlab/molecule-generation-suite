#!/usr/bin/env python3
"""Validate benchmark-linked Research OS knowledge bundles."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.knowledge import verify_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()

    for path in args.paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        identity = verify_bundle(payload)
        print(f"{path}: {identity}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
