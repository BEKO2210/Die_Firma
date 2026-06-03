# Research notes — hardening & operability (2026-06)

These notes back the v0.2.x review follow-up. They summarise current best
practice for a **local-first, loopback-bound, single-user** service that ingests
telemetry from local agent processes, and record *why* each decision was made.
The threat model is local processes on the same machine — the `127.0.0.1` bind
is the primary control — so defenses are applied proportionally.

## Rate limiting `/api/ingest`

- **Decision:** in-process **token bucket**, generous ceiling, `429` +
  `RateLimit-*` / `Retry-After` headers (`src/lib/guard.ts`).
- **Why:** token bucket tolerates the natural bursts of buffered telemetry while
  capping a runaway/looping producer; sliding-window precision isn't needed for a
  single benign producer. Implemented dependency-free.
- Sources: [arcjet](https://blog.arcjet.com/rate-limiting-algorithms-token-bucket-vs-sliding-window-vs-fixed-window/),
  [leapcell](https://leapcell.io/blog/rate-limiting-in-backend-frameworks-token-bucket-vs-sliding-window).

## SQLite as a single-writer event store

- **Decision:** `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`
  (`src/lib/db.ts`); migrations via `PRAGMA user_version` with numbered,
  transactional steps (`src/lib/migrate.ts`).
- **Why:** WAL lets the dashboard read while writing; NORMAL is the documented
  WAL speed/durability sweet spot (a committed txn may roll back only on power
  loss — acceptable for telemetry); a ≥5s busy_timeout avoids spurious
  `SQLITE_BUSY`. `user_version` is the standard no-ORM migration ledger.
- Sources: [sqlite.org/wal](https://sqlite.org/wal.html),
  [recommended pragmas](https://databaseschool.com/articles/sqlite-recommended-pragmas),
  [busy_timeout](https://berthub.eu/articles/posts/a-brief-post-on-sqlite3-database-locked-despite-timeout/),
  [user_version migrations](https://levlaz.org/sqlite-db-migrations-with-pragma-user_version/).

## Bearer-token auth

- **Decision:** constant-time compare (`crypto.timingSafeEqual`, already in
  `secrets.ts`); token stays an env secret, rotation = restart both sides
  (documented). **HMAC request signing / nonce replay protection: intentionally
  skipped** (tracked in ROADMAP for any non-loopback deployment).
- **Why:** on `127.0.0.1` there is no network path to intercept or replay, and a
  local attacker who could replay can already read the `.env` token and any HMAC
  secret — so signing adds complexity without raising the bar.
- Sources: [authgear](https://www.authgear.com/post/hmac-api-security/),
  [gitguardian](https://blog.gitguardian.com/hmac-secrets-explained-authentication/).

## CORS

- **Decision:** send **no permissive CORS headers**; reject a present, non-allow­
  listed `Origin` (`originAllowed` in `guard.ts`). The Python client sends no
  Origin and is unaffected (CORS is browser-only).
- **Why:** restrictive-by-default; `Access-Control-Allow-Origin: *` would let any
  visited site's JS hit the local API.
- Sources: [PortSwigger CORS](https://portswigger.net/web-security/cors),
  [Moesif CORS guide](https://www.moesif.com/blog/technical/cors/Authoritative-Guide-to-CORS-Cross-Origin-Resource-Sharing-for-REST-APIs/).

## Inbox watching

- **Decision:** `watchdog` (native inotify) with a periodic safety re-scan and a
  **polling fallback** (`watch.py`).
- **Why:** event-driven removes the 2s latency and the CPU waste of busy-polling;
  watchdog's built-in `PollingObserver` (and our try/except fallback) preserves
  correctness where native events are unreliable (network mounts, some
  containers). Debounce isn't needed — re-processing is idempotent.
- Sources: [watchdog (PyPI)](https://pypi.org/project/watchdog/),
  [polling fallback](https://snyk.io/advisor/python/watchdog/functions/watchdog.observers.polling.PollingObserver).
