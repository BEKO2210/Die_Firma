"""Anthropic SDK wrapper for the SDK-driven agents (dispatcher/reviewer/
sentinel) — structured JSON answers, tiered models (prompt §1).

Kept thin and lazily imported so the keyless mock pipeline never needs the
SDK. Not exercised in the mock E2E.
"""

from __future__ import annotations

import json
from typing import Any


class LLMError(RuntimeError):
    pass


def complete_json(
    *,
    api_key: str,
    model: str,
    system: str,
    prompt: str,
    max_tokens: int = 2048,
) -> dict[str, Any]:
    """Ask a model for a single JSON object and parse it. Raises on bad JSON."""
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - dependency always present
        raise LLMError("anthropic SDK not installed") from exc

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(
        getattr(block, "text", "")
        for block in message.content
        if getattr(block, "type", None) == "text"
    )
    try:
        parsed: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"model did not return valid JSON: {text[:200]}") from exc
    return parsed
