# Configuration and operations

## Requirements

- Python 3.11+ for the API and included static UI.
- Node.js 22+ and npm for rebuilding or developing the frontend.
- Microsoft Edge for default local browser checks; an alternate Playwright-supported channel can be selected.
- Internet access for the first dependency installation; no model key is required for demo use.

## Environment variables

Copy `.env.example` to `.env` when configuring a provider. Keep `.env` out of Git.

| Variable | Default | Meaning |
| --- | --- | --- |
| `OFFICE_ENABLE_MODEL` | `false` | Explicitly permit configured provider calls |
| `OFFICE_MODEL_URL` | Example Chat Completions URL in `.env.example` | Full endpoint, not only a base URL |
| `OFFICE_MODEL_NAME` | Empty | A model available to your provider account |
| `OFFICE_MODEL_KEY` | Empty | Server-side bearer credential |
| `OFFICE_DATA_DIR` | `./data` | Directory containing `office.db` |
| `OFFICE_CATALOG_DIR` | `./catalog` | Directory containing source catalog and profiles |
| `OFFICE_ALLOWED_ORIGINS` | Built-in localhost origins | Additional comma-separated allowed origins; does not change allowed Host values |
| `OFFICE_URL` | `http://127.0.0.1:4197` | Browser test target only |
| `OFFICE_BROWSER` | `msedge` | Playwright browser channel for checks |

Path defaults resolve relative to the application source root. Model variables must be configured together; the default URL alone does not connect a model.

## Optional model setup

```dotenv
OFFICE_ENABLE_MODEL=true
OFFICE_MODEL_URL=https://api.openai.com/v1/chat/completions
OFFICE_MODEL_NAME=your-available-model
OFFICE_MODEL_KEY=your-server-side-key
```

Restart the server, select the connected-model executor in settings, then explicitly start a task. The subsequent provider call can consume the provider's balance. This repository does not include credentials or a provider budget system.

The adapter accepts HTTPS; HTTP is allowed only for a loopback provider. URLs containing user information and redirects are rejected. It uses the [Chat Completions protocol](https://developers.openai.com/api/reference/resources/chat), supplies only the current role/context, and requests Markdown output. No browser or shell commands are executed.

## Storage and backup

Stop the server before copying the `data/` directory as a backup. Preserve it during updates. Removing it creates a fresh office on next start and discards local project history. Source files and Git commits are not a backup of local SQLite data.

Repository pushes and archive packaging exclude `.env`, databases, virtual environments and dependency directories. The portable archive contains source, the built UI, catalog and validation artifacts.

## Docker

```bash
docker compose config --quiet
docker compose up --build
```

The Compose service uses a named volume, loopback-only published port, dropped capabilities and `no-new-privileges`. The image builds the UI in Node and runs Python as a non-root user. A host-side `.env` supplies the configured values through Compose environment interpolation.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Python command missing | Install Python 3.11+ and make it available to the launcher |
| First installation fails | Check registry/network access; run `INSTALL.cmd` separately |
| Port 4197 already used | Stop only the known previous AI Office server, or choose another local port and update the test URL |
| Blank or old UI | Rebuild `frontend/`, verify `frontend/dist/index.html`, then reload the browser |
| Lost live connection | Check the running server; the UI restores a snapshot after reconnecting |
| Model unavailable | Check all provider variables, restart, and select model mode explicitly |
| Model stage error | Inspect its visible error; verify provider account access and retry explicitly |
| Interrupted stage after restart | Expected recovery behavior; the server never silently retries paid calls |
| Scheduled task did not start | The server must be running; scheduled timestamps require a timezone |

For shared or public hosting, first address the controls listed in [SECURITY.md](../SECURITY.md).
