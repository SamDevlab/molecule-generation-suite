from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.moldisc011 import run_moldisc_011


DEFAULT_CONFIG = Path("programs/moldisc-011-demethyl03-second-demethyl/program.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run frozen MOLDISC-011 DEMETHYL-03 second demethyl series")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = run_moldisc_011(config_path=args.config, output_root=args.output)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
