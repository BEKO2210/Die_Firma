# Orchestrator image (review §10). Build context = repo root so config.toml,
# tasks/ and the package are all available:
#   docker build -f services/orchestrator/Dockerfile -t die-firma-orchestrator .
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install the package first (better layer caching).
COPY services/orchestrator/pyproject.toml services/orchestrator/README.md /app/services/orchestrator/
COPY services/orchestrator/die_firma /app/services/orchestrator/die_firma
RUN pip install /app/services/orchestrator

# Repo-root runtime state the orchestrator reads (config + filesystem queues).
COPY config.toml /app/config.toml
COPY tasks /app/tasks
RUN mkdir -p /app/inbox /app/outbox /app/work /app/runlog /app/state

# Loopback-only by default; point at the dashboard service in compose.
ENV DIE_FIRMA_DASHBOARD_URL=http://dashboard:4321

CMD ["die-firma", "run"]
