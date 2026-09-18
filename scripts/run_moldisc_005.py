from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.moldisc005 import run_moldisc_005


DEFAULT_CONFIG = Path("programs/moldisc-005-nct-nalkyl-series/program.json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run frozen MOLDISC-005 NCT N-alkyl series"
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    result = run_moldisc_005(
        config_path=args.config,
        output_root=args.output,
        timeout=args.timeout,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
