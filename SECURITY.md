# Security Policy

## Supported versions

Die Firma is pre-1.0; security fixes land on `main` and the latest tagged
release.

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue.

- Use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
  ("Report a vulnerability" on the Security tab), or
- email the maintainer.

Please include reproduction steps and impact. We aim to acknowledge within a
few days.

## Security model (honest scope)

Die Firma is designed as a **local-first, single-user** system:

- All HTTP services bind to `127.0.0.1` (loopback only).
- `/api/ingest` requires a high-entropy bearer token from the environment;
  there are no committed default secrets, and placeholder tokens are rejected
  at startup. Requests are rate-limited and constant-time compared.
- Real Claude workers run under a `firejail` sandbox with a path allow-list
  (fail-closed if the sandbox is missing).

Out of scope for the current design (see `ROADMAP.md` for multi-user/cloud
hardening): network exposure, multi-tenant auth, and centralized audit logging.
Do **not** expose the dashboard to an untrusted network without adding the
hardening tracked in the roadmap.

## A note on the `secrets` modules

`apps/dashboard/src/lib/secrets.ts` and
`services/orchestrator/die_firma/secrets.py` are **secret-validation** modules:
they reject placeholder tokens and enforce length / entropy / format floors at
startup. They contain **no** committed credentials — the filenames can trip
filename-based secret scanners as a false positive. Real secrets live only in a
local, git-ignored `.env` (see `.env.example`).
