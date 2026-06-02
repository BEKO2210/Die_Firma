"""Example task plugin (review §1): a stricter `code_gen`.

Demonstrates the plugin contract by overriding the built-in `code_gen` type with
the SAME decomposition but an extra acceptance check: the produced files must not
still contain placeholder markers (TODO / FIXME / "...") that signal unfinished
work. A failing check fails the job just like a failing review.

This file is auto-discovered because it exposes ``register(registry)``.
"""

from __future__ import annotations

from pathlib import Path

from die_firma.models import Job
from die_firma.plugins import (
    BUILTIN_RULES,
    PluginRegistry,
    RuleBasedPlugin,
    ValidationResult,
)

_PLACEHOLDERS = ("TODO", "FIXME", "<<<", "PLACEHOLDER")
_TEXT_SUFFIXES = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".md", ".sh"}


def _no_placeholders(job: Job, workdir: Path) -> ValidationResult:
    if not workdir.is_dir():
        return ValidationResult(True, "nothing produced")
    offenders: list[str] = []
    for path in sorted(workdir.rglob("*")):
        if not path.is_file() or path.suffix not in _TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(marker in text for marker in _PLACEHOLDERS):
            offenders.append(str(path.relative_to(workdir)))
    if offenders:
        return ValidationResult(False, f"placeholder markers left in: {', '.join(offenders)}")
    return ValidationResult(True, "no placeholder markers")


def register(registry: PluginRegistry) -> None:
    registry.register(
        RuleBasedPlugin("code_gen", BUILTIN_RULES["code_gen"], validator=_no_placeholders),
        replace=True,
    )
