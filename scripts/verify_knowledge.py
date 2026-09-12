#!/usr/bin/env python3
"""Validate benchmark-linked Research OS knowledge bundles."""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from research_os.knowledge import verify_bundle


def _expand_paths(values: list[str]) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for value in values:
        matches = sorted(glob.glob(value))
        candidates = [Path(match) for match in matches] if matches else [Path(value)]
        for path in candidates:
            key = str(path)
            if key not in seen:
                seen.add(key)
                paths.append(path)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    results: list[dict[str, str]] = []
    for path in _expand_paths([str(value) for value in args.paths]):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            identity = verify_bundle(payload)
        except Exception as exc:  # CLI boundary: report all validation/I/O errors cleanly.
            results.append({"path": str(path), "status": "error", "error": str(exc)})
            continue
        results.append({"path": str(path), "status": "ok", "scientific_identity": identity})

    if args.json_output:
        print(json.dumps(results, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        for result in results:
            if result["status"] == "ok":
                print(f"{result['path']}: {result['scientific_identity']}")
            else:
                print(f"{result['path']}: ERROR: {result['error']}", file=sys.stderr)
    return 1 if any(result["status"] == "error" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
