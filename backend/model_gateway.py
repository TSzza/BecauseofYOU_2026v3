from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from backend import config


@dataclass
class ModelResult:
    data: dict[str, Any] | None
    raw_text: str = ""
    error: str | None = None
    status_code: int | None = None
    provider: str = field(default_factory=lambda: config.MODEL_PROVIDER)
    model: str = field(default_factory=lambda: config.MODEL_NAME)
    base_url: str = field(default_factory=lambda: config.OPENAI_BASE_URL)

    @property
    def ok(self) -> bool:
        return self.data is not None and self.error is None

    def diagnostics(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "status_code": self.status_code,
            "error": self.error,
        }


class ModelGateway:
    """OpenAI-compatible JSON client with explicit, inspectable failures."""

    @property
    def enabled(self) -> bool:
        return config.MODEL_PROVIDER in {"openai", "deepseek"} and bool(config.OPENAI_API_KEY)

    def require_enabled(self) -> None:
        if config.MODEL_PROVIDER not in {"openai", "deepseek"}:
            raise RuntimeError('MODEL_SETTINGS["provider"] must be openai or deepseek for LLM mode')
        if not config.OPENAI_API_KEY:
            raise RuntimeError('MODEL_SETTINGS["api_key"] is required for LLM mode')

    def generate_json(self, system_prompt: str, user_payload: dict[str, Any]) -> ModelResult:
        if not self.enabled:
            return ModelResult(None, error="model gateway is disabled")
        payload = {
            "model": config.MODEL_NAME,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.75,
        }
        request = urllib.request.Request(
            f"{config.OPENAI_BASE_URL}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                status = response.status
                result = json.loads(response.read().decode("utf-8"))
            raw = result["choices"][0]["message"]["content"]
            return ModelResult(self._parse_json(raw), raw_text=raw, status_code=status)
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")[:2000]
            return ModelResult(None, error=f"HTTP {error.code}: {body}", status_code=error.code)
        except urllib.error.URLError as error:
            return ModelResult(None, error=f"network error: {error.reason}")
        except (KeyError, ValueError, json.JSONDecodeError) as error:
            return ModelResult(None, error=f"invalid model response: {error}")

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.S)
        if fenced:
            cleaned = fenced.group(1).strip()
        try:
            value = json.loads(cleaned)
        except json.JSONDecodeError:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start < 0 or end <= start:
                raise
            value = json.loads(cleaned[start : end + 1])
        if not isinstance(value, dict):
            raise ValueError("model JSON root must be an object")
        return value
