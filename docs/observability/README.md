# Observability (review §6)

Beyond the live dashboard, "Die Firma" exposes its read-model projection as
**Prometheus** metrics so you can keep long-term history — throughput, error
rates, cost trends — and graph it in **Grafana** with alerting.

Everything stays loopback-only and read-only: the exporter only reads the SQLite
projection the dashboard already maintains.

## Endpoint

```
GET http://127.0.0.1:4321/api/metrics-prom
```

Returns the Prometheus text exposition format (`version=0.0.4`). Metrics:

| Metric | Type | Labels | Meaning |
| --- | --- | --- | --- |
| `die_firma_tasks` | gauge | `status` | tasks by current status |
| `die_firma_active_tasks` | gauge | — | non-terminal tasks |
| `die_firma_tokens_per_second` | gauge | — | live token throughput |
| `die_firma_events_per_second` | gauge | — | live event rate |
| `die_firma_idle_seconds` | gauge | — | seconds since last event (-1 if none) |
| `die_firma_today_cost_usd` | gauge | — | spend today (UTC) |
| `die_firma_today_tokens` | gauge | `direction` | tokens today (in/out) |
| `die_firma_agent_tokens_total` | counter | `agent`,`direction` | tokens per agent |
| `die_firma_agent_cost_usd_total` | counter | `agent` | cost per agent |
| `die_firma_agent_active_tasks` | gauge | `agent` | active tasks per agent |

## Scraping

Add the job in [`prometheus.yml`](./prometheus.yml) to your Prometheus config:

```yaml
scrape_configs:
  - job_name: die-firma
    metrics_path: /api/metrics-prom
    static_configs:
      - targets: ["127.0.0.1:4321"]
```

## Grafana

Import [`grafana-dashboard.json`](./grafana-dashboard.json) (Dashboards →
Import) and pick your Prometheus data source. It ships panels for task status,
throughput, active tasks, daily cost and per-agent token usage, plus an alert
rule on a high task-failure rate.

## OpenTelemetry

For OTel pipelines, scrape this endpoint with the OpenTelemetry Collector's
[`prometheus` receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/prometheusreceiver)
and forward via any exporter (OTLP, etc.) — no app change needed:

```yaml
receivers:
  prometheus:
    config:
      scrape_configs:
        - job_name: die-firma
          metrics_path: /api/metrics-prom
          static_configs:
            - targets: ["127.0.0.1:4321"]
```
