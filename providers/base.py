from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


@dataclass
class LLMResponse:
    text: str
    raw: Optional[Dict[str, Any]] = None


class LLMProvider(Protocol):
    name: str

    def generate(self, prompt: str, *, system: str | None = None) -> LLMResponse:
        ...

    def json(self, prompt: str, *, system: str | None = None) -> Dict[str, Any]:
        ...
