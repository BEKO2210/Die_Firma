"""Offline heuristic fallback (review §4).

When every model attempt fails — the Ollama server is down, the request times
out, and the configured fallback model is also unreachable — the worker can
still emit a deterministic placeholder deliverable instead of hard-crashing the
job. The placeholder is honest about being a stub (so a reviewer/operator can
see the model never ran) but keeps the pipeline flowing offline.

Pure and dependency-free: a single function mapping a sub-task to file content.
"""

from __future__ import annotations

from .models import Job, Subtask

# Per-action stub: a real file with the right extension, clearly marked offline.
_STUBS: dict[str, tuple[str, str]] = {
    "implement": ("implement.md", "Implementierung"),
    "self_review": ("NOTES.md", "Self-Review"),
    "analyze": ("REVIEW.md", "Analyse"),
    "build_script": ("README.md", "Automatisierung"),
    "smoke": ("SMOKE_TEST.md", "Smoke-Test"),
    "ingest": ("INGEST.md", "Daten-Ingest"),
    "transform": ("transform.md", "Transformation"),
}


def heuristic_artifact(job: Job, subtask: Subtask, *, reason: str = "offline") -> dict[str, str]:
    """A single placeholder file for a sub-task that could not reach any model.

    The content states the task, the step and *why* it is a stub, so the gap is
    visible downstream rather than silently passing as real work."""
    filename, label = _STUBS.get(subtask.action, (f"{subtask.action}.md", subtask.action))
    title = job.body.splitlines()[0].lstrip("# ").strip() if job.body else job.id
    content = (
        f"# {label} — {title}\n\n"
        f"> ⚠️ Platzhalter (Grund: {reason}). Kein Modell war erreichbar; dieser "
        f"Schritt wurde heuristisch erzeugt und muss noch ausgeführt werden.\n\n"
        f"- **Task:** {title}\n"
        f"- **Schritt:** {subtask.action} — {subtask.title}\n"
        f"- **Job-Typ:** {job.type}\n"
    )
    return {filename: content}
