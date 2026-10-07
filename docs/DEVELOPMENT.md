# Development

## Local setup

Create the Python virtual environment and install `requirements.txt` as described in the README. Then:

```bash
cd frontend
npm ci
npm run build
npm run dev
```

Vite serves `http://127.0.0.1:5173`; `/api` proxies to the API at port 4197. FastAPI serves the built bundle on one origin for ordinary local use. Rebuild before committing a UI change because the production bundle is included for users without Node.

## Code conventions

- Keep programming identifiers, comments, commit messages and repository documentation in English.
- Keep interface text, default stage labels and localized role presentation in Russian.
- Keep original catalog fields and source checksums unchanged.
- Preserve custom member names and permissions during localization and upgrades.
- Add capabilities in the engine, not through role prompt text.
- Display failures explicitly; never hide a model failure behind demo output.

## Extension points

### Another executor

Implement asynchronous `execute(payload, stage)` returning `{content, usage, cost}` and register it in `Engine.adapter`. Keep credentials server-side. Validate output and usage, respect input scope, and recheck permissions before persisting results.

### An external tool

The current browser and GitHub capabilities are disconnected placeholders. A real tool needs a server-side adapter, explicit credentials/scope, input validation, pre/post permission checks, cancellation semantics, safe event reporting and contract tests. A checked UI permission alone is insufficient.

### A catalog update

Validate and import a complete schema-versioned catalog. Preserve `name`, source paths, `instructions_md` and checksums from the supplied records. Add separate Russian presentation fields for new IDs. Test custom membership preservation and repeated import.

## CI

`.github/workflows/ci.yml` uses a read-only repository token and runs on pushes and pull requests to `main`, plus manual dispatch. It installs locked frontend dependencies, builds TypeScript/Vite, installs Python requirements, executes backend tests, audits dependencies, and validates Compose configuration. It does not deploy or call a model.

Browser testing currently runs locally against a running application; commands and isolated-storage guidance are in [TESTING.md](TESTING.md). Local results and CI results are separate evidence; a prepared workflow is not a completed run.

Action references come from the official [checkout](https://github.com/actions/checkout), [setup-node](https://github.com/actions/setup-node) and [setup-python](https://github.com/actions/setup-python) projects.

## Changes and commits

Prefer narrow commits with a clear subject, for example:

```text
feat(office): add complete agent workspace
feat(ui): localize all role descriptions
docs: add setup and architecture guides
ci: verify build tests and dependencies
```

Do not commit `.env`, SQLite state, secrets, virtual environments, `node_modules`, or failed screenshots. Check `git diff --cached --stat` and `git status --short` before pushing. See [CONTRIBUTING.md](../CONTRIBUTING.md).
