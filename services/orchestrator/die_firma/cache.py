"""Result cache: reuse artifacts for identical sub-task inputs (review §3).

A worker step is a pure-ish function of (job type, task text, action, the files
it can already see, the model). When the exact same input recurs — a re-run, a
duplicated sub-task, an unchanged dependency — we can skip the (minutes-long,
sometimes paid) model call and replay the stored artifacts instead.

The cache is content-addressed: the key is a SHA-256 over the normalised input,
and the artifacts plus a small `meta.json` live under
``state/cache/<key[:2]>/<key>/``. Pure and dependency-free so it is fully
unit-testable without a model or server.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

_META = "meta.json"
_ARTIFACTS = "artifacts"


def subtask_cache_key(
    *,
    job_type: str,
    task_text: str,
    action: str,
    model: str,
    context: dict[str, str],
) -> str:
    """Stable content hash for a worker step.

    ``context`` is the map of files already in the workdir the step builds on;
    sorting it makes the key order-independent. The model name is part of the
    key so a model change correctly busts the cache.
    """
    h = hashlib.sha256()
    for field in (job_type, action, model, task_text):
        h.update(field.encode("utf-8"))
        h.update(b"\x00")
    for name in sorted(context):
        h.update(name.encode("utf-8"))
        h.update(b"\x00")
        h.update(context[name].encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


@dataclass(frozen=True)
class CachedResult:
    """A replayed cache hit: the artifacts and the model that produced them."""

    artifacts: dict[str, str]
    model: str
    output: str


class ResultCache:
    """Content-addressed store of sub-task artifacts under a root directory.

    Disabled instances (``enabled=False``) are inert no-ops, so callers can wire
    the cache in unconditionally and let config decide whether it does anything.
    """

    def __init__(self, root: Path, *, enabled: bool = True) -> None:
        self._root = root
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _dir(self, key: str) -> Path:
        return self._root / key[:2] / key

    def get(self, key: str) -> CachedResult | None:
        """Return the stored result for ``key`` or ``None`` on a miss.

        A corrupt or partial entry reads as a miss (never raises), so a botched
        write can never poison future runs."""
        if not self._enabled:
            return None
        entry = self._dir(key)
        meta_path = entry / _META
        if not meta_path.is_file():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            artifacts: dict[str, str] = {}
            for rel in meta.get("artifacts", []):
                fp = entry / _ARTIFACTS / rel
                artifacts[str(rel)] = fp.read_text(encoding="utf-8")
        except (OSError, ValueError):
            return None
        return CachedResult(
            artifacts=artifacts,
            model=str(meta.get("model", "")),
            output=str(meta.get("output", "")),
        )

    def put(self, key: str, *, artifacts: dict[str, str], model: str, output: str) -> None:
        """Store ``artifacts`` for ``key`` atomically (write to a temp dir, then
        swap). A failed write is swallowed — the cache must never break a job."""
        if not self._enabled or not artifacts:
            return
        entry = self._dir(key)
        tmp = entry.with_name(entry.name + ".tmp")
        try:
            if tmp.exists():
                shutil.rmtree(tmp)
            (tmp / _ARTIFACTS).mkdir(parents=True, exist_ok=True)
            for rel, content in artifacts.items():
                dest = tmp / _ARTIFACTS / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
            meta = {"model": model, "output": output, "artifacts": sorted(artifacts)}
            (tmp / _META).write_text(json.dumps(meta, indent=2), encoding="utf-8")
            if entry.exists():
                shutil.rmtree(entry)
            tmp.rename(entry)
        except OSError:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
