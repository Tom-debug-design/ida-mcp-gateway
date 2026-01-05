from __future__ import annotations
import json
from typing import Any, Dict, Optional

from core.config import OPENAI_API_KEY, OPENAI_MODEL
from providers.base import LLMProvider, LLMResponse


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        if not OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY mangler. Sett den i repo Secrets / env."
            )

        # Lazy import så systemet ikke crasher ved import hvis pakken mangler.
        from openai import OpenAI  # type: ignore
        self._client = OpenAI(api_key=OPENAI_API_KEY)
        self._model = OPENAI_MODEL or "gpt-4.1-mini"

    def generate(self, prompt: str, *, system: Optional[str] = None) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # Bruk Responses API hvis tilgjengelig i din openai lib.
        # Hvis ikke: bytt til chat.completions. Dette fungerer for de fleste nye versjoner.
        try:
            resp = self._client.responses.create(
                model=self._model,
                input=messages,
            )
            # responses API kan returnere flere blocks – vi tar første tekst.
            text = ""
            for item in getattr(resp, "output", []) or []:
                for c in getattr(item, "content", []) or []:
                    if getattr(c, "type", "") == "output_text":
                        text += getattr(c, "text", "")
            if not text:
                text = str(resp)
            return LLMResponse(text=text, raw={"responses": True})
        except Exception:
            # Fallback til chat.completions
            resp2 = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.2,
            )
            text2 = resp2.choices[0].message.content or ""
            return LLMResponse(text=text2, raw={"responses": False})

    def json(self, prompt: str, *, system: Optional[str] = None) -> Dict[str, Any]:
        out = self.generate(
            prompt,
            system=(system or "") + "\n\nSvar KUN med gyldig JSON. Ingen tekst utenfor JSON.",
        ).text.strip()

        # Hard parse: hvis modellen tuller → fail tydelig
        try:
            return json.loads(out)
        except Exception as e:
            raise RuntimeError(f"LLM returnerte ikke JSON. Raw:\n{out}\nError: {e}")
