"""Die Firma orchestrator — the Python side.

Filesystem is the single source of truth for orchestration; the dashboard's
SQLite read-model is fed exclusively over HTTP via /api/ingest. This package
never touches the DB directly (prompt §1/§7).
"""

__version__ = "0.1.0"
