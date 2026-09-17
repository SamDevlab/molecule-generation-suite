#!/usr/bin/env python3
"""Execute the single authorized APODOCK-001 v1.1 prospective run.

This is deliberately run-branch-specific.  It requires the exact
``APODOCK-001-v1.1`` authorization label and uses explicit paths.  It never
calls the freeze adapter's blocked ``execute_prospective`` method.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research_os.docking.apodock001_execution import ExecutionAuthorization  # noqa: E402
from research_os.docking.apodock001_v11_run import (  # noqa: E402
    APODOCK001V11ProspectiveRunner,
    V11_AUTHORIZATION_LABEL,
    analyze_v11_sealed_run,
    build_v102_v11_comparison,
    write_comparison_markdown,
    write_evidence_bundle_manifest,
)
from research_os.engines.openbabel import OpenBabelEngine  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run APODOCK-001 v1.1 exactly once")
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--v102", required=True, type=Path)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--prepared-root", required=True, type=Path)
    parser.add_argument("--staging-root", required=True, type=Path)
    parser.add_argument("--vina", required=True, type=Path)
    parser.add_argument("--openbabel", required=True, type=Path)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--analysis-commit-sha", required=True)
    parser.add_argument("--historical-analysis", required=True, type=Path)
    parser.add_argument("--authorize", required=True)
    args = parser.parse_args()

    if args.authorize != V11_AUTHORIZATION_LABEL:
        raise SystemExit(f"authorization must equal {V11_AUTHORIZATION_LABEL}")

    runner = APODOCK001V11ProspectiveRunner(
        spec_path=args.protocol,
        v102_path=args.v102,
        source_root=args.bundle,
        run_root=args.run_root,
        prepared_root=args.prepared_root,
        staging_root=args.staging_root,
        git_sha=args.git_sha,
    )
    preflight = runner.preflight()
    print(f"preflight={preflight['status']}")
    vina, openbabel_identity = runner.verify_tools(
        vina_executable=args.vina,
        openbabel_executable=args.openbabel,
    )
    openbabel = OpenBabelEngine(str(args.openbabel))
    prepared = runner.prepare_inputs(openbabel=openbabel)
    commands = runner.command_audit(vina.executable)
    checkpoint = runner.write_pre_execution_checkpoint(
        args.checkpoint,
        vina=vina,
        openbabel=openbabel_identity,
        prepared_artifacts=prepared,
        commands=commands,
    )
    print(f"prepared_receptors={checkpoint['prepared_receptors']}/10")
    print(f"prepared_ligands={checkpoint['prepared_ligands']}/10")
    print(f"prepared_artifacts={checkpoint['prepared_artifacts']}/20")
    print(f"execution_implementation_sha={args.git_sha}")
    print("pre-execution checkpoint: READY_FOR_EXPLICIT_AUTHORIZATION")

    manifest = runner.execute_prospective(
        vina=vina,
        openbabel=openbabel_identity,
        prepared_artifacts=prepared,
        authorization=ExecutionAuthorization(True, args.authorize),
        checkpoint_path=args.checkpoint,
    )
    print(f"raw_status={manifest['status']}")
    print(f"run_id={manifest['run_id']}")
    print(f"raw_results_seal_sha256={manifest['raw_results_seal_sha256']}")

    analysis = analyze_v11_sealed_run(
        protocol_path=args.protocol,
        v102_path=args.v102,
        bundle_root=args.bundle,
        run_root=args.run_root,
        openbabel=openbabel,
        analysis_commit_sha=args.analysis_commit_sha,
    )
    from research_os.docking.apodock001_analysis import write_analysis_manifest

    write_analysis_manifest(args.run_root / "analysis-manifest.json", analysis)
    comparison = build_v102_v11_comparison(args.historical_analysis, analysis)
    from research_os.docking.apodock001_execution import write_json

    write_json(args.run_root / "comparison-manifest.json", comparison)
    write_comparison_markdown(args.run_root / "v1.0.2-v1.1-comparison.md", comparison)
    evidence = write_evidence_bundle_manifest(
        run_root=args.run_root,
        protocol_id=manifest["protocol_id"],
        protocol_hash=manifest["protocol_hash"],
        run_id=manifest["run_id"],
        raw_seal_sha256=manifest["raw_results_seal_sha256"],
    )
    print(f"analysis_status={analysis['status']}")
    print(f"analysis_engine_id={analysis['analysis_engine_id']}")
    print(f"evidence_bundle_sha256={evidence['evidence_bundle_sha256']}")
    print("APODOCK-001 v1.1 prospective execution and post-seal analysis complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
