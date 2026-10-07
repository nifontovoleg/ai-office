# Testing and evidence

## Backend

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite creates temporary SQLite databases and uses ASGITransport for API tests and MockTransport for the provider. It does not require real credentials. It covers catalog integrity, membership isolation, bulk addition, fresh/repeated boot, the manual/automatic workflow, approval/revision/reset, output handoffs, concurrency, cancellation, revoked permissions, SSE replay, input/Host/Origin guards, safe file boundaries and server secrets.

Russian presentation regressions cover all catalog IDs, nonempty Russian names/descriptions, unchanged source fields and preservation of customized member configuration.

Provider regressions cover native Claude authentication, separate system/user context, text blocks, cache token accounting, token-limit errors, malformed responses and integration with stage persistence/handoffs. OpenCode helper tests verify empty-key defaults, process-env precedence, provider/model namespaces, safe diagnostics and explicit launch behavior. No CLI model execution is performed by those tests.

Check each tracked preset locally without contacting a provider:

```powershell
.\.venv\Scripts\python.exe tools/opencode.py --check --env-file .env.example
.\.venv\Scripts\python.exe tools/opencode.py --check --env-file config/proxyapi.env.example
.\.venv\Scripts\python.exe tools/opencode.py --check --env-file config/claude.env.example
```

For a clean terminal with no provider overrides, each empty-key example reports `key_present=false` and `provider_access_verified=false`. A missing CLI is allowed for a configuration check. See [PROVIDERS.md](PROVIDERS.md) for the explicit installation/launch steps.

## Browser and accessibility

Start an isolated local server before running browser tests. For example, set `OFFICE_DATA_DIR` to a temporary directory before starting uvicorn. Do not point a test run at valuable project data: tests create QA projects and operate on the built-in demonstration.

From `frontend/`:

```powershell
npm ci
npm run build
npm run test:e2e
npm run test:all-agents
npm run test:localization
```

The default browser channel is installed Microsoft Edge in headless mode. Set `OFFICE_BROWSER=chrome` for installed Chrome, or configure another supported channel. `OFFICE_URL` changes the target.

| Script | Coverage |
| --- | --- |
| `tests/office.e2e.mjs` | Catalog instruction, dialogs/focus, project isolation, membership edits, map views, ten-stage workflow, approval, task creation, visible model errors, responsive layout |
| `tests/all-agents.e2e.mjs` | All 282 members, original settings, team pages, role search, executor selection, large departments, repeated bulk import, reload persistence, mobile search, page correction after removal |
| `tests/localization.e2e.mjs` | Russian profile presentation/search, original source language, executor search and narrow layout |
| `tests/final-preview.mjs` | Reproducible screenshots of the primary demo; leaves the final package awaiting owner review |

axe checks WCAG A/AA rules in selected states. A zero-violation result does not establish complete WCAG certification. Real user research and manual screen-reader testing are still outstanding.

## Dependency audits

```bash
cd frontend
npm audit
```

Install `pip-audit` in a separate audit environment, then run:

```bash
pip-audit -r requirements.txt
```

The recorded audit has zero known vulnerabilities. Audit results are snapshots, not a guarantee against future advisories. Requirements and the frontend lockfile are committed.

## Packaging

```bash
python tools/package.py
```

The archive builder excludes credentials, local state and dependencies, checks archive CRC integrity, and verifies the built UI, Windows launcher, and 282 original Markdown profiles. Re-run it after changes if distributing a new ZIP.

## Limits

The real provider account, model output, billing and external tool behavior are not covered by MockTransport tests. Local Docker validation covered configuration because the engine was unavailable. Source security contracts and dependency scans are not a penetration test. See [VALIDATION.md](../VALIDATION.md) for actual recorded results.
