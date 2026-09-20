from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.moldisc019 import (
    PACKAGE_RELATIVE_PATH,
    build_first_decision,
    ingest_result,
    package_status,
    prepare_package,
    record_first_run,
    validate_result,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "programs" / "moldisc-019-experimental-bridge" / "program.json"
DEFAULT_PACKAGE = ROOT / PACKAGE_RELATIVE_PATH
DEFAULT_VALIDATION = ROOT / "validation"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the bounded MOLDISC-019 Biolab experimental bridge contracts")
    parser.add_argument("command", choices=("prepare", "status", "validate-result", "ingest-result", "first-run"))
    parser.add_argument("result", nargs="?", help="external result JSON for validate-result or ingest-result")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--package", default=str(DEFAULT_PACKAGE))
    parser.add_argument("--validation-root", default=str(DEFAULT_VALIDATION))
    args = parser.parse_args()

    if args.command == "prepare":
        output = prepare_package(args.config, args.package)
    elif args.command == "status":
        output = package_status(args.package)
    elif args.command == "validate-result":
        if not args.result:
            parser.error("validate-result requires a result JSON path")
        output = validate_result(args.result, args.package)
    elif args.command == "ingest-result":
        if not args.result:
            parser.error("ingest-result requires a result JSON path")
        output = ingest_result(args.result, args.package)
    else:
        output = record_first_run(args.config, args.package, args.validation_root)
    print(json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
