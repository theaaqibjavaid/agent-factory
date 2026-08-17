# Security Policy

## Reporting a vulnerability

**Please do not open a public issue for security problems.** Use GitHub's
private vulnerability reporting instead:

1. Go to https://github.com/theaaqibjavaid/agent-factory/security/advisories/new
2. Describe the issue — include the affected version(s), a minimal
   reproduction, and (if known) the impact.
3. You should get an acknowledgement within 48 hours. We aim to ship a fix in
   a patch release within 7 days of confirmation.

If you prefer email, contact the maintainers through the private advisory
flow above only — there is no public support inbox for security mail.

## Scope

The following are in scope:

- The platform API (`agentfactory/app/**`) — auth, workspace isolation, the
  custom-tool sandbox, MCP handling, terminal, and SPA serving.
- The SDK core (`agentfactory/**` outside `app/`).
- The Studio SPA (`web/src/**`).

Out of scope (best-effort, documented limitations):

- The legacy v1 approval server (`agentfactory/app/approval_server.py`) — it
  is maintained for backward compatibility only; see `docs/migration-v1-v2.md`.
- Social-engineering or phishing attacks on the project's maintainers.
- Local-only setups where an attacker already has shell access to the host.

## Threat model

The full STRIDE threat model and the per-release security test plan live in
[docs/security.md](docs/security.md).

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.1.x   | ✅ active |
| 1.0.x   | ✅ security fixes only |
| < 1.0   | ❌ |

## Security-relevant configuration

- **Always** set `AGENTFACTORY_JWT_SECRET` to a long random value in
  production (see `docs/self-host.md`).
- Set `AGENTFACTORY_ALLOWED_ORIGINS` to your real origins — never `*` in
  production.
- Put the service behind a TLS-terminating reverse proxy.
- `AGENTFACTORY_RATE_LIMIT_AUTH` (default 20 req/min/IP) blunts credential
  stuffing on the auth surface; set `0` only for local development.

## Hall of fame

We thank everyone who reports issues responsibly. If you'd like credit, say so
in your report and we'll add you here.
