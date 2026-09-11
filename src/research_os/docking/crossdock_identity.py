from __future__ import annotations

from typing import Any

from research_os.core.hashing import sha256_json


# Structural alignment/grid calculations may differ at machine-epsilon scale
# across BLAS/LAPACK runners. Nine decimal places are far below any physical
# resolution used by the protocol while making the structural identity portable.
FLOAT_DIGITS = 9


def canonicalize(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, FLOAT_DIGITS)
    if isinstance(value, dict):
        return {key: canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [canonicalize(item) for item in value]
    return value


def stable_hash(value: Any) -> str:
    return sha256_json(canonicalize(value))
