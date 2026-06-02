"""Lightweight i18n for CLI output and reports (review §5).

Messages live in JSON catalogues under ``die_firma/locales/<lang>.json``. The
translator looks up a key in the selected language, falls back to English, then
to the key itself — so a missing translation degrades gracefully instead of
crashing. ``str.format`` placeholders let messages carry runtime values.

Dependency-free (stdlib json) and pure, so it is fully unit-testable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LANG = "en"
LOCALES_DIR = Path(__file__).resolve().parent / "locales"


@dataclass(frozen=True)
class Translator:
    """Resolves message keys to formatted strings for one language."""

    lang: str
    messages: dict[str, str]
    fallback: dict[str, str]

    def t(self, key: str, **kwargs: object) -> str:
        template = self.messages.get(key) or self.fallback.get(key) or key
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):  # pragma: no cover - bad placeholder guard
            return template


def _load_catalogue(lang: str, locales_dir: Path) -> dict[str, str]:
    path = locales_dir / f"{lang}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # pragma: no cover - corrupt catalogue guard
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def load_translator(lang: str = DEFAULT_LANG, locales_dir: Path = LOCALES_DIR) -> Translator:
    """Build a Translator for ``lang`` with an English fallback catalogue."""
    fallback = _load_catalogue(DEFAULT_LANG, locales_dir)
    messages = fallback if lang == DEFAULT_LANG else _load_catalogue(lang, locales_dir)
    return Translator(lang=lang, messages=messages, fallback=fallback)


def available_languages(locales_dir: Path = LOCALES_DIR) -> list[str]:
    """Language codes with a catalogue on disk."""
    if not locales_dir.is_dir():
        return []
    return sorted(p.stem for p in locales_dir.glob("*.json"))
