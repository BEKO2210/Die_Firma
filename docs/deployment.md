# Deployment (review §10)

Die Firma runs three ways: directly (CLI + `systemd --user`), as installable
packages, or via Docker Compose.

## Packages

- **Python orchestrator** — `pip install ./services/orchestrator` exposes the
  `die-firma` CLI. Metadata, classifiers and entry point live in
  `services/orchestrator/pyproject.toml` (v0.2.0).
- **Dashboard** — `@die-firma/dashboard` (npm, private workspace). Build the
  standalone Node server with `npm run build` → `node ./dist/server/entry.mjs`.

## Docker Compose

```bash
export DIE_FIRMA_INGEST_TOKEN=$(openssl rand -hex 24)
docker compose up --build
# dashboard on http://127.0.0.1:4321
```

- `dashboard` is the only SQLite writer; `orchestrator` only POSTs telemetry to
  it. Shared named volumes (`inbox`, `outbox`, `state`) carry the filesystem
  queues between the services.
- For fully local, keyless inference, uncomment the `ollama` service and point
  `DIE_FIRMA_OLLAMA_URL` at `http://ollama:11434`; otherwise it uses the host's
  Ollama via `host.docker.internal`.
- Switch UI/CLI language with `DIE_FIRMA_LANG=en docker compose up`.

## Releases & versioning

Semantic versioning; changes are tracked in [`CHANGELOG.md`](../CHANGELOG.md).
Tag a release as `vX.Y.Z` once the manifests and changelog agree.

## Keeping dependencies fresh

`scripts/check-updates.sh` reports newer stable versions for both ecosystems
(read-only). Review, bump pins in `DEPENDENCIES.md` + the manifests, and re-run
the full CI gates before committing.
