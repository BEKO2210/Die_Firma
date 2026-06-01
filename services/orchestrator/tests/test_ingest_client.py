import json

import httpx

from die_firma.ingest_client import IngestClient


def _client(handler) -> IngestClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    return IngestClient("http://127.0.0.1:4321", "token-xyz", client=http)


def test_emit_builds_payload_and_sends_token():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("x-die-firma-token")
        seen["json"] = json.loads(request.content)
        return httpx.Response(201, json={"ok": True, "id": 7})

    client = _client(handler)
    eid = client.emit("status_changed", task_id="t1", status="running", tokens_in=5, cost_usd=0.2)
    assert eid == 7
    assert seen["url"].endswith("/api/ingest")
    assert seen["token"] == "token-xyz"
    # None-valued fields are omitted; zero numerics omitted.
    assert seen["json"] == {
        "kind": "status_changed",
        "task_id": "t1",
        "status": "running",
        "tokens_in": 5,
        "cost_usd": 0.2,
    }


def test_metrics_and_today_spend():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"today_spend": {"cost_usd": 1.25}})

    client = _client(handler)
    assert client.today_spend_usd() == 1.25
    assert client.metrics()["today_spend"]["cost_usd"] == 1.25
    client.close()
