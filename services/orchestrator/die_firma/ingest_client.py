"""HTTP client to the dashboard's /api/ingest (the only writer) and read APIs.

The Python side speaks HTTP only — it never opens the SQLite DB (prompt §1/§7).
"""

from __future__ import annotations

from typing import Any

import httpx


class IngestClient:
    def __init__(self, base_url: str, token: str, client: httpx.Client | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._token = token
        self._client = client or httpx.Client(timeout=10.0)

    def emit(
        self,
        kind: str,
        *,
        task_id: str | None = None,
        subtask_id: str | None = None,
        agent: str | None = None,
        status: str | None = None,
        message: str | None = None,
        data: dict[str, Any] | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
    ) -> int:
        payload: dict[str, Any] = {"kind": kind}
        for key, value in (
            ("task_id", task_id),
            ("subtask_id", subtask_id),
            ("agent", agent),
            ("status", status),
            ("message", message),
            ("data", data),
        ):
            if value is not None:
                payload[key] = value
        if tokens_in:
            payload["tokens_in"] = tokens_in
        if tokens_out:
            payload["tokens_out"] = tokens_out
        if cost_usd:
            payload["cost_usd"] = cost_usd

        resp = self._client.post(
            f"{self._base}/api/ingest",
            json=payload,
            headers={"x-die-firma-token": self._token},
        )
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        return int(body["id"])

    def metrics(self) -> dict[str, Any]:
        resp = self._client.get(f"{self._base}/api/metrics")
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    def today_spend_usd(self) -> float:
        return float(self.metrics()["today_spend"]["cost_usd"])

    def close(self) -> None:
        self._client.close()
