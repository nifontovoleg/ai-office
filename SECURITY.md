# Security policy

## Supported scope

AI Office is intended for one local OS user, with the API bound to `127.0.0.1`. It has no multi-user authentication. Any local process with loopback access can attempt API calls. Do not expose this configuration to a shared network or the public internet.

## Implemented controls

- Typed input validation, request size bounds and transactionally validated catalog imports.
- Host/Origin checks and JSON content requirements on mutating requests.
- Project-scoped membership, task inputs and material references.
- Explicit engine capabilities, permission rechecks and hierarchy cycle rejection.
- Per-task locks, atomic output/handoff commits, cancellation and restart recovery.
- Server-only model credentials, HTTPS or loopback provider URLs, no redirects or URL user information.
- Sanitized provider errors and explicit separation of demo/model execution.
- Restricted Codex text-stage subprocesses with saved ChatGPT login, stdin context and no API credentials in the child environment.
- Static-path filtering and attachment-based material downloads.
- Loopback Docker publication and a non-root container runtime configuration.

Detailed executable evidence is in [tests/SECURITY_REVIEW.md](tests/SECURITY_REVIEW.md).

## Data handling

SQLite project data and optional `.env` are plaintext files protected by the OS user's permissions. The application does not encrypt them at rest or implement retention/DSAR controls. Stop the server before backing up `data/`. Git and archive packaging exclude local data and secrets.

Codex and OpenCode maintain their own saved login outside this repository. Do not copy their authentication files into source, `.env`, archives or chat. Interactive coding sessions use the owner's selected project and CLI permissions; they remain separate from restricted office text stages.

Catalog instructions are role inputs, not authority to grant capabilities. Model output is stored as text; it is not executed as shell code or published automatically.

## Reporting

This repository is private. Report a suspected vulnerability privately to the repository owner through an existing authorized channel. Include the affected revision, reproduction steps, expected/actual behavior and impact. Do not publish credentials, sensitive project materials or exploit details in a public issue.

Before any shared deployment, add authentication, per-project authorization, TLS, suitable session/CSRF protections, request limits, audited secret handling, backups and a separate deployment security review.
