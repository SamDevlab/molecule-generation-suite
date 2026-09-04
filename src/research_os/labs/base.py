from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
from research_os.core.types import RunManifest
from research_os.proof.rules import Rule
from research_os.proof.engine import ProofEngine

class Lab(ABC):
    name: str

    @abstractmethod
    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def rules(self) -> list[Rule]: ...

    def run(self, raw: dict[str, Any], experiment: str = "default") -> RunManifest:
        normalized = self.normalize(raw)
        manifest = RunManifest(lab=self.name, experiment=experiment, inputs=normalized)
        return ProofEngine().evaluate(manifest, self.rules())
