"""Equation registry with an explicit domain/condition gate."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable

from research_os.core.hashing import sha256_json


class EquationDomainError(ValueError):
    pass


@dataclass(frozen=True)
class EquationRecord:
    equation_id: str
    expression: str
    symbols: tuple[str, ...]
    units: dict[str, str]
    assumptions: tuple[str, ...] = ()
    domain: dict[str, Any] = field(default_factory=dict)
    conditions: dict[str, Any] = field(default_factory=dict)
    source_id: str | None = None
    locator: str | None = None
    review_status: str = "REVIEW_REQUIRED"
    digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbols", tuple(self.symbols))
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        if not self.equation_id.strip() or not self.expression.strip():
            raise ValueError("equation_id and expression are required")
        if self.digest is None:
            object.__setattr__(self, "digest", sha256_json(self._payload()))

    def _payload(self) -> dict[str, Any]:
        data = asdict(self)
        data["symbols"] = list(self.symbols)
        data["assumptions"] = list(self.assumptions)
        data.pop("digest", None)
        return data

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}

    def in_domain(self, context: dict[str, Any]) -> bool:
        for key, expected in self.domain.items():
            if key not in context:
                return False
            value = context[key]
            if isinstance(expected, dict):
                if "min" in expected and float(value) < float(expected["min"]):
                    return False
                if "max" in expected and float(value) > float(expected["max"]):
                    return False
                if "allowed" in expected and value not in expected["allowed"]:
                    return False
            elif value != expected:
                return False
        return True

    def assert_in_domain(self, context: dict[str, Any]) -> None:
        if not self.in_domain(context):
            raise EquationDomainError(f"equation {self.equation_id} is outside its declared domain")


class EquationRegistry:
    def __init__(self, root: str | Path | None = None, equations: Iterable[EquationRecord] = ()):
        self.root = Path(root) if root is not None else None
        self._equations: dict[str, EquationRecord] = {}
        if self.root is not None:
            (self.root / "equations").mkdir(parents=True, exist_ok=True)
            for path in sorted((self.root / "equations").glob("*.equation.json")):
                equation = EquationRecord(**json.loads(path.read_text(encoding="utf-8")))
                self._equations[equation.equation_id] = equation
        for equation in equations:
            self.register(equation)

    def register(self, equation: EquationRecord) -> EquationRecord:
        if equation.equation_id in self._equations:
            raise ValueError(f"equation already registered: {equation.equation_id}")
        self._equations[equation.equation_id] = equation
        if self.root is not None:
            self.write(equation)
        return equation

    def get(self, equation_id: str) -> EquationRecord:
        return self._equations[equation_id]

    def list(self) -> tuple[EquationRecord, ...]:
        return tuple(self._equations.values())

    def write(self, equation: EquationRecord) -> Path:
        if self.root is None:
            raise ValueError("EquationRegistry has no persistence root")
        target = self.root / "equations" / f"{equation.equation_id}.equation.json"
        target.write_text(json.dumps(equation.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return target

