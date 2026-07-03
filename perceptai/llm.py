"""Single LLM access point for the engine.

All Groq calls, JSON fence-stripping and permissive parsing live here —
in exactly one place. A malformed model reply degrades to (None, raw),
never to an exception in the execution path.
"""
from __future__ import annotations

import json
from typing import Any, Optional


def parse_json_reply(raw: str) -> Optional[Any]:
    cleaned = raw.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


class LLMClient:
    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = None
        self.calls = 0

    def _get_client(self):
        if self._client is None:
            from groq import Groq  # lazy: keeps the package importable without groq installed
            self._client = Groq(api_key=self._api_key)
        return self._client

    def complete_text(self, prompt: str, model: str, max_tokens: int = 800) -> str:
        self.calls += 1
        response = self._get_client().chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()

    def complete_json(self, prompt: str, model: str, max_tokens: int = 800) -> tuple[Optional[Any], str]:
        raw = self.complete_text(prompt, model, max_tokens)
        return parse_json_reply(raw), raw

    def complete_vision_json(
        self, image_b64: str, prompt: str, model: str, max_tokens: int = 1500
    ) -> tuple[Optional[Any], str]:
        self.calls += 1
        response = self._get_client().chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            max_tokens=max_tokens,
        )
        raw = response.choices[0].message.content.strip()
        return parse_json_reply(raw), raw
