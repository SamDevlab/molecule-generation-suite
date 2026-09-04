"""Compatibility import for callers using the longer registry module name."""

from research_os.ml.registry import ModelRecord, ModelRegistry, ModelStage

__all__ = ["ModelRecord", "ModelRegistry", "ModelStage"]
