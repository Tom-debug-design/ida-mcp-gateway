from __future__ import annotations
from typing import Any, Dict, Optional

from providers.base import LLMProvider, LLMResponse
from providers.openai_provider import OpenAIProvider


def get_provider() -> LLMProvider:
    # Nå: kun OpenAI. Senere kan du mappe på PROVIDER env.
    return OpenAIProvider()


def llm_text(prompt: str, system: Optional[str] = None) -> LLMResponse:
    p = get_provider()
    return p.generate(prompt, system=system)


def llm_json(prompt: str, system: Optional[str] = None) -> Dict[str, Any]:
    p = get_provider()
    return p.json(prompt, system=system)
