"""Small LLM adapter: any OpenAI-compatible endpoint (Gemini default).

Kept behind one class so swapping providers = change LLM_BASE_URL / LLM_MODEL.
Structured output is enforced by asking for JSON and validating with Pydantic;
every failure mode (timeout, 4xx/5xx, invalid JSON) is returned as data so the
batch never dies because one model call failed.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from ..config import Settings

T = TypeVar("T", bound=BaseModel)

SYSTEM_PROMPT = (
    "You are a rigorous technical recruiter screening resumes for an SDE intern "
    "role requiring strong Python fundamentals and practical AI/agentic experience. "
    "Score strictly inside the category caps, always cite short evidence quotes "
    "from the resume, and never invent details that are not present."
)


@dataclass
class LLMOutcome:
    """Result of one model call — success or failure, never an exception."""

    ok: bool
    value: BaseModel | None = None
    error: str | None = None


def _extract_json(text: str) -> dict:
    """Pull a JSON object out of the model reply (handles ```json fences)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object in model reply")
        candidate = text[start : end + 1]
    return json.loads(candidate)


class LLMClient:
    """Minimal chat-completions client with retries and typed parsing."""

    def __init__(self, settings: Settings):
        self.settings = settings
        # Circuit breaker: once the *daily* quota is exhausted, stop calling
        # — remaining candidates fall back to rule-based without waiting on
        # pointless retries (set from any worker thread; benign race).
        self._quota_exhausted_reason: str | None = None

    @property
    def available(self) -> bool:
        return self.settings.llm_available

    def complete_json(
        self,
        user_prompt: str,
        schema: Type[T],
        *,
        max_tokens: int = 4000,
        retries: int = 3,
    ) -> LLMOutcome:
        """Call the model and validate its JSON against ``schema``."""
        if not self.available:
            return LLMOutcome(ok=False, error="llm_not_configured")
        if self._quota_exhausted_reason:
            # Daily budget already blown this run — fail fast for the rest.
            return LLMOutcome(ok=False, error=f"llm_skipped: {self._quota_exhausted_reason}")

        payload = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        url = self.settings.llm_base_url.rstrip("/") + "/chat/completions"

        last_error = "unknown"
        for attempt in range(retries + 1):
            try:
                with httpx.Client(timeout=self.settings.llm_timeout) as client:
                    response = client.post(url, headers=headers, json=payload)
                if response.status_code >= 400:
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                    if response.status_code in (400, 401, 403, 404, 422):
                        return LLMOutcome(ok=False, error=last_error)  # not retryable
                    if response.status_code == 429:
                        if "PerDay" in response.text:
                            # Daily quota: retrying cannot help this run.
                            self._quota_exhausted_reason = "daily quota exhausted"
                            return LLMOutcome(ok=False, error=last_error)
                        # Per-minute limit: backoff and retry.
                    time.sleep(1.5 * (attempt + 1))
                    continue
                body = response.json()
                choice = body["choices"][0]
                message = choice.get("message", {})
                # Some OpenAI-compatible gateways return content under
                # extra_content, or truncate it (finish_reason == "length").
                content = message.get("content") or message.get("extra_content") or ""
                if not isinstance(content, str) or not content.strip():
                    if choice.get("finish_reason") == "length":
                        last_error = "reply truncated (finish_reason=length)"
                    else:
                        last_error = "empty model reply"
                    time.sleep(1.0 * (attempt + 1))
                    continue  # retry with backoff; often transient
                data = _extract_json(content)
                try:
                    value = schema.model_validate(data)
                except ValidationError as exc:
                    last_error = f"schema validation failed: {exc.error_count()} errors"
                    time.sleep(1.0 * (attempt + 1))
                    continue  # ask again with a repair hint
                return LLMOutcome(ok=True, value=value)
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, ValueError) as exc:
                snippet = repr(content)[:200] if isinstance(content, str) else "<non-str>"
                last_error = f"{type(exc).__name__}: {exc} | reply: {snippet}"
        return LLMOutcome(ok=False, error=last_error)
