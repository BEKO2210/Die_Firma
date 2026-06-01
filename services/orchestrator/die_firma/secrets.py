"""Secret hardening for the Python side (claude.md §6 / prompt §7).

Mirrors the dashboard's check: reject known placeholders, enforce a minimum
length / character-variety floor, validate the Anthropic key format. Startup
aborts when a required secret fails. 100% coverage target.
"""

from __future__ import annotations

PLACEHOLDERS = (
    "changeme",
    "change-me",
    "bitte-ersetzen",
    "replace",
    "your-key-here",
    "your-token",
    "example",
    "placeholder",
    "todo",
    "xxx",
    "secret",
    "dummy",
)

MIN_TOKEN_LENGTH = 24


class SecretError(ValueError):
    """A required secret is missing or looks like a placeholder."""


def _contains_placeholder(value: str) -> str | None:
    lower = value.lower()
    for p in PLACEHOLDERS:
        if p in lower:
            return p
    return None


def check_token(value: str | None, *, name: str = "token") -> str:
    """Validate a shared-secret style token; return it trimmed or raise."""
    if value is None or value.strip() == "":
        raise SecretError(f"{name} is missing")
    v = value.strip()
    if len(v) < MIN_TOKEN_LENGTH:
        raise SecretError(f"{name} is too short (< {MIN_TOKEN_LENGTH} chars)")
    hit = _contains_placeholder(v)
    if hit is not None:
        raise SecretError(f"{name} looks like a placeholder ({hit!r})")
    classes = sum(
        1
        for ok in (
            any(c.islower() for c in v),
            any(c.isupper() or c.isdigit() for c in v),
            any(c in "-_" for c in v),
        )
        if ok
    )
    if classes < 2:
        raise SecretError(f"{name} has insufficient character variety")
    return v


def check_anthropic_key(value: str | None) -> str:
    """Validate an Anthropic API key (format + not a placeholder)."""
    if value is None or value.strip() == "":
        raise SecretError("ANTHROPIC_API_KEY is missing")
    v = value.strip()
    if not v.startswith("sk-ant-"):
        raise SecretError("ANTHROPIC_API_KEY must start with 'sk-ant-'")
    hit = _contains_placeholder(v)
    if hit is not None:
        raise SecretError(f"ANTHROPIC_API_KEY looks like a placeholder ({hit!r})")
    if len(v) < MIN_TOKEN_LENGTH:
        raise SecretError("ANTHROPIC_API_KEY is too short")
    return v
