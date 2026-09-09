"""Reproducibility helpers for online scientific benchmarks.

Scientific-result hashes intentionally normalize insignificant floating-point
noise and exclude legacy/raw execution hash fields. Execution hashes
additionally bind the normalized result to the runtime/software environment.
"""
from __future__ import annotations

import math
import platform
import sys
from typing import Any, Mapping

from research_os.core.hashing import sha256_json

SCIENTIFIC_FLOAT_DIGITS = 12
HASH_POLICY = f"round-finite-floats-{SCIENTIFIC_FLOAT_DIGITS}-decimal-digits-drop-volatile-hashes-v1"
VOLATILE_HASH_KEYS = frozenset({
    "report_hash",
    "scientific_result_hash",
    "scientific_hash_policy",
    "execution_environment",
    "execution_hash",
})


def normalize_scientific_payload(value: Any, *, float_digits: int = SCIENTIFIC_FLOAT_DIGITS) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("scientific hash payload cannot contain non-finite floats")
        normalized = round(value, float_digits)
        return 0.0 if normalized == 0.0 else normalized
    if isinstance(value, Mapping):
        return {
            str(key): normalize_scientific_payload(item, float_digits=float_digits)
            for key, item in value.items()
            if str(key) not in VOLATILE_HASH_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [normalize_scientific_payload(item, float_digits=float_digits) for item in value]
    return value


def scientific_result_hash(payload: Any) -> str:
    return sha256_json({
        "hash_policy": HASH_POLICY,
        "payload": normalize_scientific_payload(payload),
    })


def execution_environment() -> dict[str, str]:
    environment = {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
    }
    for module_name, key in (("numpy", "numpy"), ("rdkit", "rdkit"), ("sklearn", "scikit_learn")):
        try:
            module = __import__(module_name)
            environment[key] = str(getattr(module, "__version__", "unknown"))
        except ImportError:
            environment[key] = "unavailable"
    return environment


def execution_hash(scientific_hash: str, environment: Mapping[str, str] | None = None) -> str:
    env = dict(environment) if environment is not None else execution_environment()
    return sha256_json({
        "scientific_result_hash": scientific_hash,
        "environment": env,
        "python_hexversion": sys.hexversion,
    })


def reproducibility_metadata(payload: Any) -> dict[str, Any]:
    scientific_hash = scientific_result_hash(payload)
    environment = execution_environment()
    return {
        "scientific_result_hash": scientific_hash,
        "scientific_hash_policy": HASH_POLICY,
        "execution_environment": environment,
        "execution_hash": execution_hash(scientific_hash, environment),
    }
