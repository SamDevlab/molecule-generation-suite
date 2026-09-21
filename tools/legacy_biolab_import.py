#!/usr/bin/env python3
"""CLI for deterministic Biolab legacy archaeology."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.legacy.biolab_archaeology import build_artifacts, dry_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-root", required=True, type=Path)
    parser.add_argument("--scope", choices=("priority",), default="priority")
    parser.add_argument("--output-dir", type=Path, default=Path("legacy/biolab-v0"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    if args.dry_run:
        result = dry_run(args.legacy_root, scope=args.scope, repo_root=repo_root)
    else:
        result = build_artifacts(args.legacy_root, output_dir=args.output_dir, scope=args.scope, repo_root=repo_root)
    stats = result.get("statistics", {})
    print(f"LEGACY_SOURCES_FOUND={stats.get('priority_sources_found', 0)}")
    print(f"ROWS_SCANNED={stats.get('rows_scanned', 0)}")
    print(f"MOLECULAR_ROWS={stats.get('molecular_rows', 0)}")
    print(f"IDENTITIES_VALID={stats.get('identity_valid', 0)}")
    print(f"IDENTITIES_PARTIAL={stats.get('identity_partial', 0)}")
    print(f"IDENTITIES_INVALID={stats.get('identity_invalid', 0)}")
    print(f"IDENTITIES_MISSING={stats.get('identity_missing', 0)}")
    print(f"UNIQUE_EXACT_IDENTITIES={stats.get('unique_exact_identities', 0)}")
    print(f"CURRENT_PANEL_EXACT_MATCHES={sum(result.get('current_panel', {}).get('status', {}).get('exact_matches', {}).values())}")
    print(f"CURRENT_PANEL_CONNECTIVITY_MATCHES={sum(result.get('current_panel', {}).get('status', {}).get('connectivity_matches', {}).values())}")
    if args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"CANONICAL_CORPUS_HASH={result['canonical_corpus_hash']}")
        print(f"OUTPUT_DIR={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
