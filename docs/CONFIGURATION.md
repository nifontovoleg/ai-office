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
| `OFFICE_MODEL_PROTOCOL` | `codex_cli` in `.env.example`; legacy fallback `chat_completions` | Saved-ChatGPT Codex CLI, Chat Completions or native `anthropic_messages` |
| `OFFICE_MODEL_URL` | Empty in the primary template | Full HTTP endpoint for API transports; unused by Codex |
| `OFFICE_MODEL_NAME` | Empty for Codex; provider ID in API presets | A model available to your account; blank uses the default in Codex mode |
| `OFFICE_MODEL_KEY` | Empty | Server-side provider API key |
| `OFFICE_CODEX_PATH` | CLI discovered in PATH | Optional absolute native Codex executable path |
| `OFFICE_CODEX_TIMEOUT_SECONDS` | `300` | Codex stage timeout, `30..1800` seconds |
| `OFFICE_MODEL_MAX_TOKENS` | `8192` | Anthropic output limit, `128..128000`; not sent to Chat Completions |
| `OFFICE_MODEL_TIMEOUT_SECONDS` | `120` | HTTP timeout in seconds, `1..600` |
| `OFFICE_DATA_DIR` | `./data` | Directory containing `office.db` |
| `OFFICE_CATALOG_DIR` | `./catalog` | Directory containing source catalog and profiles |
| `OFFICE_ALLOWED_ORIGINS` | Built-in localhost origins | Additional comma-separated allowed origins; does not change allowed Host values |
| `OFFICE_URL` | `http://127.0.0.1:4197` | Browser test target only |
| `OFFICE_BROWSER` | `msedge` | Playwright browser channel for checks |
| `OPENCODE_AUTH` | `free` in the primary template; `api_key` in API presets | Big Pickle public free route, optional `chatgpt` browser login or API-key mode; legacy helper default is `api_key` |
| `OPENCODE_PROVIDER` | `opencode` | OpenCode Zen, OpenAI, ProxyAPI or Anthropic; ChatGPT mode requires OpenAI |
| `OPENCODE_BASE_URL` | `https://opencode.ai/zen/v1` for free mode | Free mode fixes the official endpoint; API mode uses its provider base |
| `OPENCODE_MODEL` / `OPENCODE_SMALL_MODEL` | Both `opencode/big-pickle` | Fixed to Big Pickle in free mode; API preset IDs in API mode; ChatGPT mode uses `/models` |

Path defaults resolve relative to the application source root. API transports need URL/name/key together. Codex mode requires the CLI and saved ChatGPT login; it does not use the API key field.

## Primary Codex setup

```dotenv
OFFICE_ENABLE_MODEL=true
OFFICE_MODEL_PROTOCOL=codex_cli
OFFICE_MODEL_NAME=gpt-6.1-sol
OFFICE_CODEX_TIMEOUT_SECONDS=300
```

Complete `codex login` with ChatGPT, restart the server, select the connected-model executor in settings, then explicitly start a task. This uses account model availability and Codex limits. The CLI is run in a temporary read-only text-stage workspace; coding sessions are launched separately with `tools/codex.py --start`. See [CODEX.md](CODEX.md).

The alternative HTTP adapter accepts HTTPS; HTTP is allowed only for a loopback provider. URLs containing user information and redirects are rejected. It supports [Chat Completions](https://developers.openai.com/api/reference/resources/chat) and native [Claude Messages](https://platform.claude.com/docs/en/get-started), supplies only the current role/context, and requests Markdown output.

Use [the provider guide](PROVIDERS.md) for optional OpenAI, ProxyAPI and Claude Platform setup. `config/openai.env.example` is the direct OpenAI office preset. `OPENCODE_*` variables and `tools/opencode.py` configure a separate OpenCode coding session. Its primary mode selects free Big Pickle without an account key/login. Optional ChatGPT browser-login and API-key modes can be configured while office stages remain on Codex. See [CODEX.md](CODEX.md).

## Storage and backup

Stop the server before copying the `data/` directory as a backup. Preserve it during updates. Removing it creates a fresh office on next start and discards local project history. Source files and Git commits are not a backup of local SQLite data.

Repository pushes and archive packaging exclude `.env`, databases, virtual environments and dependency directories. The portable archive contains source, the built UI, catalog and validation artifacts.

## Docker

```bash
docker compose config --quiet
docker compose up --build
```

The Compose service uses a named volume, loopback-only published port, dropped capabilities and `no-new-privileges`. The image builds the UI in Node and runs Python as a non-root user. A host-side `.env` supplies the configured values through Compose environment interpolation.

The standard image does not contain Codex CLI or host ChatGPT login credentials. Use native host execution for `codex_cli`, or select an API preset for Docker.

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
