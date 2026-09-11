#!/usr/bin/env python3
"""Validate Research OS knowledge bundles and print their scientific identity."""
from __future__ import annotations

import argparse
from pathlib import Path

from research_os.knowledge import bundle_from_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()

    for path in args.paths:
        bundle = bundle_from_json(path.read_text(encoding="utf-8"))
        print(f"{path}: {bundle.scientific_identity}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
