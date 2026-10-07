# Backend security review

Review scope: local single-user AI Office, FastAPI + SQLite, demo executor, server-configured Chat Completions/native Claude Messages adapter and the optional OpenCode launcher. API integration tests use ASGITransport; provider tests use MockTransport. No live model call, customer-project tool execution or paid execution was performed by the review.

## Verified controls

- Only localhost, 127.0.0.1 and the testserver test host are accepted. The launcher must bind the published service to 127.0.0.1. In Docker, publish with `127.0.0.1:4197:4197`.
- Requests carrying an unrelated Origin are rejected, including Origin `null`. Allowed development origins are localhost/127.0.0.1 ports 4197 and 5173. Additional origins require explicit server configuration through `OFFICE_ALLOWED_ORIGINS`.
- Mutating JSON API requests require `application/json`; malformed typed input returns 4xx. Catalog import is streamed with a 20 MB bound, validated completely before transactional upsert, and cannot write files or change membership settings.
- SQL object identifiers come from internal constants; values use placeholders. Profile paths are metadata and are never interpreted as client-selected filesystem paths. Downloads locate a server-generated material ID and send content as an attachment, not executable HTML.
- Teams, task inputs and previous-stage materials are scoped to their project. Tools are granted explicitly in office configuration. External integrations remain disconnected and no external tool execution is implemented. A role instruction cannot grant a tool.
- Export permissions are rechecked before the provider call and again under the commit lock. Revocation while a provider call is running prevents result export. Cancellation preserves allowed output already being produced and prevents handoff to a new stage.
- Stage completion, material storage and handoff events commit atomically. Per-task locks reject duplicate completion/reset while a call is running. Auto execution waits for a concurrent manual step. SQLite member hierarchy changes are checked under a lock to prevent hierarchy cycles.
- Model credentials stay on the server, are sent in the Authorization header for Chat Completions or x-api-key for Claude Messages, and do not appear in health/state, stage messages, provider error responses or event logs. The model adapter accepts HTTPS, with HTTP only for loopback providers; redirects and URL user-info are rejected.
- Model output and usage are schema checked. Token values are accepted only as actual nonnegative integer counters; unknown usage fields are discarded. Costs remain unknown. Provider failures produce an error without substituting demo content.
- Claude's system instruction is separate from user context. Text blocks are combined, cache/input/output counters are normalized and a token-limit stop cannot complete a stage. Unsupported protocols and invalid token/timeout settings stop before an HTTP request.
- Provider examples have empty keys and disable office calls by default. The OpenCode helper performs no HTTP calls and launches nothing without `--start`. It validates provider/model names and the HTTPS base URL, rejects credentials/query/fragment in that URL and does not echo invalid env values.
- Explicit OpenCode launch passes the key only in the child environment, never in command arguments or stored JSON. Templates disable sharing and request permission for edits, shell commands and external directories. These CLI permissions are not an OS sandbox, and OpenCode remains separate from office stages.
- Restart disables automatic execution and marks interrupted stages as errors. Retrying an interrupted provider call requires explicit user action. Event replay uses monotonically increasing sequence cursors and unique event IDs; Last-Event-ID resumes without replaying acknowledged events.

## Test evidence

Run from the project directory:

```powershell
python -m unittest discover -s tests -v
```

The suite uses fresh temporary database directories, including import-time app bootstrap. It verifies all 282 original catalog records and source SHA-256 values, all 18 categories, multi-project membership, complete manual and auto workflows, approval/revision/reset history, exact material handoff, cancellation/revocation concurrency, restart recovery, model payload isolation and safe errors, SSE replay, API input/Host/Origin validation, and path/secret boundaries.

On this Windows sandbox, Python 3.11 asyncio blocks while creating a socketpair before executing tests. Running the same isolated suite outside the sandbox avoids that environment limitation. No network provider access is required by the suite.

## Deployment limits

This MVP has no authentication and is intended for one local OS user. Local processes able to access loopback can call its API. SQLite project content and the optional `.env` are plaintext protected by the current user's filesystem permissions; the app does not encrypt data at rest. Do not expose it to a shared LAN or public network with this configuration. A shared deployment needs user authentication, project authorization, TLS, CSRF/session protection, rate limits, retention/backups and an independently audited secret store.

This review is a source review and executable contract suite, not a penetration test. The separate dependency audit identified a python-dotenv 1.2.1 advisory; requirements now pin the corrected version 1.2.2. The provider update passes all 63 backend tests, including native Claude, OpenCode launch boundaries and Russian presentation regressions, with the production frontend bundle present. The resulting log is `output/backend-tests.txt`; `pip check` reports no broken requirements. Provider protocols were verified with MockTransport and CLI launch with a mocked subprocess; provider account access, real model behavior, billing, actual CLI tools and paid execution remain unverified.
