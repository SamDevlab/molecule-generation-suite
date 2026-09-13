"""Generate the APODOCK-001 v1.1 preregistration from the frozen v1.0.2 file."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research_os.docking.apodock001_v11 import write_v11_protocol  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "configs" / "apodock001-protocol-freeze-v1.1.json",
    )
    parser.add_argument(
        "--v102",
        type=Path,
        default=ROOT / "configs" / "apodock001-protocol-freeze-v1.0.2.json",
    )
    args = parser.parse_args()
    protocol = write_v11_protocol(args.output, args.v102)
    print(f"protocol_id={protocol['protocol_id']}")
    print(f"protocol_hash={protocol['protocol_hash']}")
    print(f"planned_run_id={protocol['operational_metadata']['planned_run_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
