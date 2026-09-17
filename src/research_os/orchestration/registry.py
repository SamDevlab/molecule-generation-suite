from __future__ import annotations
from dataclasses import dataclass,field
from typing import Iterable
from research_os.labs.base import Lab
class LabNotFoundError(KeyError): pass
@dataclass
class LabRegistry:
    _labs:dict[str,Lab]=field(default_factory=dict)
    def register(self,lab:Lab,*,aliases:Iterable[str]=()):
        for name in [lab.name,*aliases]:
            key=name.strip().lower()
            if not key: raise ValueError("lab name/alias cannot be empty")
            existing=self._labs.get(key)
            if existing is not None and existing is not lab: raise ValueError(f"lab name already registered: {name}")
            self._labs[key]=lab
    def get(self,name:str)->Lab:
        try:return self._labs[name.strip().lower()]
        except KeyError as exc: raise LabNotFoundError(name) from exc
    def names(self): return tuple(sorted({lab.name for lab in self._labs.values()}))
