#!/usr/bin/env python3
"""Analyze one sealed APODOCK-001 v1.0.2 run without invoking Vina."""

from __future__ import annotations

import argparse
from pathlib import Path

from research_os.docking.apodock001_analysis import (
    OpenBabelPoseAdapter,
    analyze_sealed_run,
    write_analysis_manifest,
)
from research_os.engines.openbabel import OpenBabelEngine


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze sealed APODOCK-001 raw results with the v1.0.2 same-frame evaluator"
    )
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--openbabel-executable", default=None)
    args = parser.parse_args()

    adapter = OpenBabelPoseAdapter(OpenBabelEngine(args.openbabel_executable))
    manifest = analyze_sealed_run(
        protocol_path=Path(args.protocol),
        bundle_root=Path(args.bundle),
        run_root=Path(args.run_root),
        converter=adapter,
        analysis_commit_sha=args.git_sha,
    )
    write_analysis_manifest(args.output, manifest)
    print("APODOCK-001 analysis: COMPLETE")
    print(f"analysis_engine_id: {manifest['analysis_engine_id']}")
    print(f"run_id: {manifest['run_id']}")
    print(f"indeterminate_count: {manifest['aggregation']['indeterminate_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
