# Provider connections and OpenCode

This guide covers direct OpenAI, ProxyAPI and direct Claude Platform access. All keys are supplied locally by the owner. The checked-in examples contain empty key fields and keep AI Office model calls disabled.

## What is connected

| Component | Behavior |
| --- | --- |
| AI Office model executor | Calls the selected provider for one stage and stores Russian Markdown and reported token usage |
| OpenAI / ProxyAPI office preset | Uses Chat Completions for text generation |
| Claude Platform office preset | Uses Anthropic Messages with `x-api-key` authentication |
| Optional OpenCode launcher | Opens a separate coding session in an existing project folder, using an env-backed configuration |
| Codex | Your separate development workspace; no Codex subscription credential is copied into the application |

OpenCode is not registered as an AI Office stage executor. The office does not run returned code, invoke the OpenCode CLI, browse customer sites or push their repositories. Its browser/GitHub capabilities remain disconnected. Launching OpenCode separately enables the coding workflow described below; it does not connect those UI capabilities.

## Choose a preset

| Provider | Env template | Office model | OpenCode main / small model |
| --- | --- | --- | --- |
| OpenAI | [`.env.example`](../.env.example) | `gpt-6.1-sol` | Sol / Luna |
| ProxyAPI | [`config/proxyapi.env.example`](../config/proxyapi.env.example) | `openai/gpt-6.1-sol` | Sol / Luna through ProxyAPI |
| Claude Platform | [`config/claude.env.example`](../config/claude.env.example) | `claude-sonnet-5-5` | Sonnet 5.5 / Haiku 5.5 |

Only one office provider is active at a time. Switching providers requires updating `.env` and restarting the server. There is no automatic fallback or per-stage model routing. OpenCode's `small_model` handles lightweight internal work such as session titles; it is not a router for all simple development requests.

Models can have account-specific availability. The examples use IDs verified in provider documentation on October 8, 2026; check your account's catalog before use.

## Obtain a key

### OpenAI

1. Open [OpenAI Platform](https://platform.openai.com/) and select the organization/project that will pay for requests.
2. Create a project API key in [API keys](https://platform.openai.com/api-keys).
3. Check billing, model availability and project usage settings before enabling calls.
4. Put that key in `OFFICE_MODEL_KEY` in your local `.env`.

API billing and included Codex/ChatGPT plan usage are different access paths. This application uses an API key; it does not inherit the desktop application's subscription allowance.

### ProxyAPI

1. Open [ProxyAPI Console](https://console.proxyapi.ru/) and create an API key.
2. Check the balance and the [model catalog](https://proxyapi.ru/models/browse).
3. Use the ProxyAPI env template and put the ProxyAPI key in `OFFICE_MODEL_KEY`.
4. Use complete vendor/model IDs such as `openai/gpt-6.1-sol` for office requests.

The OpenCode model name has one additional provider prefix: `proxyapi/openai/gpt-6.1-sol`. The application request model remains `openai/gpt-6.1-sol`.

### Claude Platform

1. Open [Claude Platform](https://platform.claude.com/) and sign in to the Claude Console.
2. Select the intended organization, create an API key in its API-key settings and check API billing/model access.
3. Use the Claude env template and put that API key in `OFFICE_MODEL_KEY`.
4. Keep `OFFICE_MODEL_PROTOCOL=anthropic_messages` and the full Messages endpoint.

A Claude web chat subscription is not the credential consumed by this adapter. Check the provider's [supported countries](https://www.anthropic.com/supported-countries) for direct access. The UI cannot resolve a provider-side account or regional rejection.

## Prepare the local env file

Run these commands from the repository root after installing the application. Choose one template before copying it:

```powershell
# OpenAI:
$providerTemplate = '.env.example'
# Or ProxyAPI: $providerTemplate = 'config/proxyapi.env.example'
# Or Claude:   $providerTemplate = 'config/claude.env.example'

if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath $providerTemplate -Destination '.env'
}
notepad .env
```

If `.env` already exists, edit it using the selected template rather than overwriting local data paths or the existing key. Keep any private backup under an ignored `.env.*` filename. No real key belongs in an example file.

On Linux/macOS, copy the selected file only when `.env` does not already exist, then edit it locally:

```bash
test -f .env || cp .env.example .env
# To select Claude on a fresh checkout, use config/claude.env.example instead.
```

## Variables

| Variable | Purpose |
| --- | --- |
| `OFFICE_ENABLE_MODEL` | Keep `false` for initial setup; set `true` to permit office provider calls |
| `OFFICE_MODEL_PROTOCOL` | `chat_completions` or `anthropic_messages` |
| `OFFICE_MODEL_URL` | Full office endpoint ending in `/chat/completions` or `/messages` |
| `OFFICE_MODEL_NAME` | Provider request model ID, without an OpenCode-only prefix |
| `OFFICE_MODEL_KEY` | The selected provider's secret API key; shared with the optional launcher |
| `OFFICE_MODEL_MAX_TOKENS` | Anthropic output-token limit, default `8192`, allowed range `128..128000`; not sent to Chat Completions |
| `OFFICE_MODEL_TIMEOUT_SECONDS` | Office HTTP timeout, default `120`, allowed range `1..600` |
| `OPENCODE_PROVIDER` | `openai`, `proxyapi` or `anthropic`; chooses the tracked JSON template |
| `OPENCODE_BASE_URL` | HTTPS base URL ending in `/v1`, without a request-specific suffix |
| `OPENCODE_MODEL` | Registered OpenCode main model, including its provider prefix |
| `OPENCODE_SMALL_MODEL` | Registered OpenCode small model, including its provider prefix |

The application and launcher give existing process environment variables precedence over `.env`. If editing the file has no effect, inspect the relevant environment-variable *presence* or restart from a clean terminal; do not print secrets. Write literal values, not `${OTHER_VARIABLE}` references, in the shared env file.

## Connect the office

1. Save `.env` with your selected provider and key.
2. Set `OFFICE_ENABLE_MODEL=true` when ready to allow model requests.
3. Restart with `START.cmd`, or restart the documented uvicorn command.
4. Open `http://127.0.0.1:4197/` and select **Настройки → Подключённая модель**.
5. Create a small one-stage task with a short, non-sensitive goal and explicitly start it.
6. Inspect the resulting material and token counters. Check the provider dashboard for actual usage and cost.

`GET /api/health` reports configuration, protocol and `verified=false`. Configuration being available is not proof of a successful authenticated request. The adapter never silently substitutes demo text after a model failure.

Claude text blocks are stored together as Markdown. Its input/output/cache counters are normalized to the office's token fields. A response stopped by `max_tokens` becomes a visible error instead of a completed stage; raise the configured limit or shorten the task and retry explicitly.

For Docker, the office variables are forwarded by [Compose](../compose.yaml). Restart the service after editing `.env`:

```bash
docker compose config --quiet
docker compose up -d --build
```

Use `--quiet`: printing the fully interpolated Compose configuration can reveal keys. OpenCode runs separately on the host; the office container does not include or execute it.

## Optional OpenCode coding session

Install the CLI with Node.js/npm according to [OpenCode installation](https://opencode.ai/docs/):

```powershell
npm install -g opencode-ai
opencode --version
```

Check the local connection settings without contacting a model:

```powershell
.\.venv\Scripts\python.exe tools/opencode.py --check
```

The result contains provider/model names, `key_present`, `cli_available`, `ready_for_opencode` and `provider_access_verified=false`. It never prints the key. This check neither generates text nor launches OpenCode; it validates local settings only.

Start a coding session explicitly, using an existing customer project directory:

```powershell
.\.venv\Scripts\python.exe tools/opencode.py --start --project 'D:\Projects\customer-app'
```

Linux/macOS:

```bash
.venv/bin/python tools/opencode.py --check
.venv/bin/python tools/opencode.py --start --project /path/to/customer-app
```

The launcher reads the office `.env`, selects a config from `config/`, passes the secret in the child process environment and launches the CLI without putting the key in command arguments. It does not change your global OpenCode configuration or store a key in JSON. Without `--start`, it only checks settings.

OpenCode reads the project and uses the selected model after launch. Usage can incur charges even while `OFFICE_ENABLE_MODEL=false`: that flag gates office stages, while `--start` explicitly starts the separate coding tool. The templates ask before edits, shell commands and access outside the project, and disable session sharing. OpenCode permissions are not OS isolation; use a container or VM for execution that needs isolation.

You can start with this brief:

> Read the project, describe the smallest implementation plan, implement the agreed feature, run its meaningful tests, and review the rendered UI when browser tools are available. Keep UI copy in Russian and source identifiers/documentation in English. Report files changed, checks run and remaining limits. Do not claim an external action without executing and verifying it.

To change models, edit the env values and register any new model in the selected JSON template. The helper rejects models not registered in that template to catch wrong provider prefixes before launch.

## Cost and acceptance

Start with Sol for development and Luna for small OpenCode tasks, or Sonnet/Haiku for the Claude preset. Prefer a short representative task before a large project. The office has no monetary budget enforcement, automatic model router or provider billing integration; token usage is not a final invoice.

Before selecting a permanent model, compare a landing page, an authenticated data application and a Telegram bot by accepted functionality, rendered UI, elapsed time, retries and provider-reported spend. That benchmark has not been run by this setup change.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Model unavailable | Fill all office fields, enable model access, restart and select model mode |
| HTTP 401 / 403 | Verify key, organization, model permissions and provider-supported access |
| HTTP 402 / insufficient credit | Check the selected provider's balance/billing |
| HTTP 404 / model not found | Check endpoint, current model ID and ProxyAPI vendor prefix |
| HTTP 429 | Check account limits; reduce concurrency and retry deliberately |
| Protocol-format error | Match `OFFICE_MODEL_PROTOCOL` to the endpoint and provider |
| Claude token-limit error | Adjust `OFFICE_MODEL_MAX_TOKENS` or shorten the task; retry explicitly |
| OpenCode check fails | Check provider, registered IDs and the HTTPS `/v1` base URL |
| OpenCode CLI missing | Install the CLI; on Windows the helper supports a direct executable or the npm installation |
| File edits not reflected | Restart; existing process variables take precedence over `.env` |

## Reference documentation

- [OpenAI GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol): Chat Completions for text; Responses for tool calling.
- [Claude quickstart](https://platform.claude.com/docs/en/get-started) and [model IDs](https://platform.claude.com/docs/en/models/overview).
- [OpenCode config](https://opencode.ai/docs/config/) and [providers](https://opencode.ai/docs/providers/).
- [ProxyAPI documentation](https://proxyapi.ru/docs) and [OpenCode integration](https://proxyapi.ru/docs/opencode-proxyapi).

Live account access, real model output, cost and OpenCode's actual model/tool execution require a configured account and an explicit run. Offline tests cover protocol and configuration behavior, not those live outcomes.
