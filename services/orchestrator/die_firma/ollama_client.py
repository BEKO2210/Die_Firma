"""Thin, shared client for a local Ollama server.

Centralises every HTTP call to Ollama so the executor, the critique pass, the
visual (VLM) critic, the chat endpoint and the RAG embedder all speak to it the
same way. Dependency-free beyond httpx (already a project dep).

Robustness baked in:
  * reasoning models (deepseek-r1) wrap their answer in <think>…</think> — we
    strip that before returning text or parsing JSON;
  * models ignore "return only JSON" and add prose or ```json fences — we
    extract the first balanced {...} object before json.loads.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import httpx

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Remove <think>…</think> spans that reasoning models prepend."""
    return _THINK.sub("", text).strip()


def extract_json(text: str) -> dict[str, Any]:
    """Best-effort parse of a JSON object embedded in model output.

    Tolerates ```json fences, leading prose and trailing commentary by scanning
    for the first balanced top-level object. Raises ValueError if none parses."""
    cleaned = strip_reasoning(text)
    # Fast path: the whole thing is JSON.
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # Scan for the first balanced {...} and try to parse it.
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(cleaned)):
            c = cleaned[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    chunk = cleaned[start : i + 1]
                    try:
                        obj = json.loads(chunk)
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        break
        start = cleaned.find("{", start + 1)
    raise ValueError(f"no JSON object found in model output: {cleaned[:200]!r}")


class OllamaClient:
    """Synchronous Ollama HTTP wrapper. One instance is shared per process."""

    def __init__(
        self,
        url: str = "http://localhost:11434",
        client: httpx.Client | None = None,
        timeout: float = 600.0,
    ) -> None:
        self._url = url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    # -- low level -------------------------------------------------------
    def generate(
        self,
        model: str,
        prompt: str,
        *,
        system: str | None = None,
        images: list[str] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Raw /api/generate call (non-streaming). Returns the parsed response."""
        payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
        if system is not None:
            payload["system"] = system
        if images:
            payload["images"] = images
        if options:
            payload["options"] = options
        resp = self._client.post(f"{self._url}/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json()

    # -- convenience -----------------------------------------------------
    def generate_text(
        self,
        model: str,
        prompt: str,
        *,
        system: str | None = None,
        images: list[str] | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[str, int, int]:
        """Generate and return (text, tokens_in, tokens_out). Reasoning spans
        are NOT stripped here (the executor wants the raw deliverable text)."""
        data = self.generate(model, prompt, system=system, images=images, options=options)
        text = str(data.get("response", ""))
        return (
            text,
            int(data.get("prompt_eval_count", 0) or 0),
            int(data.get("eval_count", 0) or 0),
        )

    def generate_json(
        self,
        model: str,
        prompt: str,
        *,
        system: str | None = None,
        images: list[str] | None = None,
    ) -> tuple[dict[str, Any], int, int]:
        """Generate and parse a JSON object. Asks Ollama for JSON-format output
        and still defends against prose/think-wrapped replies."""
        data = self.generate(
            model,
            prompt,
            system=system,
            images=images,
            options={"temperature": 0.2},
        )
        text = str(data.get("response", ""))
        obj = extract_json(text)
        return (
            obj,
            int(data.get("prompt_eval_count", 0) or 0),
            int(data.get("eval_count", 0) or 0),
        )

    def embed(self, model: str, text: str) -> list[float]:
        """Single-text embedding via /api/embeddings."""
        resp = self._client.post(
            f"{self._url}/api/embeddings", json={"model": model, "prompt": text}
        )
        resp.raise_for_status()
        return [float(x) for x in resp.json().get("embedding", [])]

    def has_model(self, name: str) -> bool:
        """Whether `name` (with or without a tag) is installed on the server."""
        try:
            resp = self._client.get(f"{self._url}/api/tags")
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        installed = {m.get("name", "") for m in resp.json().get("models", [])}
        bare = name.split(":")[0]
        return any(n == name or n.split(":")[0] == bare for n in installed)

    def close(self) -> None:
        self._client.close()


def encode_image(path: Path) -> str:
    """Base64-encode an image file for the `images` field of /api/generate."""
    return base64.b64encode(path.read_bytes()).decode("ascii")
