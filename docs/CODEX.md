# Start with Codex and OpenCode

Codex with saved ChatGPT login is the primary local workflow. Claude Platform remains an optional API provider for later. OpenCode defaults to a separate coding session with free Big Pickle; ChatGPT browser login and API-key presets remain optional.

## Two execution paths

| Path | What it does | Authentication |
| --- | --- | --- |
| AI Office with `codex_cli` | Sends the current role and allowed stage context to Codex, stores its Russian Markdown result and hands it to the next role | Saved Codex ChatGPT login |
| Interactive Codex in a customer folder | Reads/edits project files and runs tools under Codex permissions | Saved Codex ChatGPT login |
| Interactive OpenCode in a customer folder | Reads/edits files and runs tools with the selected model | Public free Big Pickle endpoint; optional ChatGPT/API modes |

Codex use follows the ChatGPT account's available models and limits. Free Big Pickle uses OpenCode Zen, independently of Codex login. The launcher does not transfer saved credentials. Optional OpenCode ChatGPT login is completed separately; API-key use has separate API billing.

## 1. Check Codex

Run from the repository root with Python dependencies installed:

```powershell
codex --version
codex login status
.\.venv\Scripts\python.exe tools/codex.py --check --env-file .env.example
```

Use Codex CLI 0.147.0 or newer. An existing desktop installation may already expose `codex.exe` in PATH. The helper supports a native Windows executable; set `OFFICE_CODEX_PATH` to its absolute path if it is not discoverable. Linux/macOS use an executable named `codex` in PATH. See [official CLI guidance](https://learn.chatgpt.com/docs/codex-cli) for installation.

If you are not logged in, run `codex login`, choose ChatGPT and complete the browser sign-in. Then repeat `codex login status`. Starting login is not proof that it completed. Do not copy Codex's authentication files into this repository or `.env`.

The helper reports `cli_available`, `login_method`, `ready_for_codex` and `provider_access_verified=false`. The check uses only `login status`; it performs no model inference and does not print credential contents.

## 2. Prepare the office

```powershell
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
notepad .env
```

Set these fields in your local `.env`:

```dotenv
OFFICE_ENABLE_MODEL=true
OFFICE_MODEL_PROTOCOL=codex_cli
OFFICE_MODEL_NAME=
OFFICE_CODEX_TIMEOUT_SECONDS=300
OFFICE_CODEX_PATH=
```

No API key is required for office Codex stages. An empty `OFFICE_MODEL_NAME` uses the CLI default. Only override it with a model your ChatGPT/Codex account can access; API model IDs are not automatically valid for this login. `OFFICE_CODEX_TIMEOUT_SECONDS` allows `30..1800` seconds. Existing process variables take precedence over the file.

When switching an existing Claude/OpenAI setup, update the fields above and preserve local storage settings and keys. Codex mode ignores `OFFICE_MODEL_URL` and removes API-key variables from its child process environment. Existing API fields can be retained for later OpenCode or provider use.

## 3. Launch and verify

```powershell
.\START.cmd
```

Open **http://127.0.0.1:4197/**, then choose **Настройки → Подключённая модель**. Create a short one-stage task with one role and explicitly start it. A real connection check requires a completed stage material and CLI-reported usage; `/api/health` always distinguishes configured state from verified provider access.

Example goal:

> Prepare a short Russian plan for an auto-service landing page: page sections, the main call to action and acceptance criteria. Return Markdown only.

Keep the server window open. Restart it after changing `.env`. Demo mode remains available without Codex/model calls.

The office runs Codex in a temporary directory with a read-only sandbox, ignored user configuration, no project instructions and disabled shell/apps/plugins/browser capabilities. It captures the final text and token counters from JSON events. Calls are serialized per office engine. Initialization notices about disabled optional capabilities are accepted only if a successful text turn follows. Turn failures, unexpected tool events and missing final results become errors; there is no demo substitution. Timeouts and server cancellation stop the owned CLI process.

This path generates stage materials. It does not edit customer project files or connect the office's browser/GitHub capabilities. Use the separate interactive session below for actual development. A read-only CLI policy is not a multi-user isolation boundary.

## 4. Open Codex for actual coding

Use an existing customer project directory:

```powershell
.\.venv\Scripts\python.exe tools/codex.py --check
.\.venv\Scripts\python.exe tools/codex.py --start --project 'D:\Projects\customer-app'
```

The interactive launcher selects that folder, requests the workspace-write sandbox and on-request approvals, and reuses saved ChatGPT login. It keeps your normal Codex configuration available for this interactive coding session. Review the target folder and its project instructions before starting.

Linux/macOS use `.venv/bin/python` instead of the Windows Python path. The local office remains a separate process.

## 5. Start OpenCode with free Big Pickle

The primary `.env.example` selects:

```dotenv
OPENCODE_PROVIDER=opencode
OPENCODE_AUTH=free
OPENCODE_BASE_URL=https://opencode.ai/zen/v1
OPENCODE_MODEL=opencode/big-pickle
OPENCODE_SMALL_MODEL=opencode/big-pickle
```

Install OpenCode if needed, then check and open an existing project:

```powershell
npm install -g opencode-ai
.\.venv\Scripts\python.exe tools/opencode.py --check
.\.venv\Scripts\python.exe tools/opencode.py --start --project 'D:\Projects\customer-app'
```

Skip installation if already available. Big Pickle is selected automatically; `/models` can confirm the selected model. This route uses OpenCode's built-in Zen provider and the public free endpoint, without an account key or ChatGPT browser login. The literal `public` value is a non-secret sentinel used by OpenCode itself for anonymous free models.

The preset fixes both `model` and `small_model` to Big Pickle, enables only `opencode`, and whitelists only `big-pickle`. The launcher applies this public preset as inline configuration after global/project defaults, fixes the CLI `--model`, and removes account API-key variables. It does not introduce a paid fallback. If the free endpoint stops accepting requests, execution fails rather than selecting another model.

`ready_for_opencode=true` means local launcher readiness; `provider_access_verified=false` remains explicit because `--check` never performs inference. Free-model availability requires a real successful request. The current installed catalog reports zero input/output/cache cost for Big Pickle.

[OpenCode Zen pricing and privacy](https://opencode.ai/docs/zen/) list Big Pickle as free for a limited period and state that collected data may be used to improve it. Review this before sending confidential customer code. Rate limits, availability and the free period can change; this configuration is not an unlimited-use guarantee.

The preset disables sharing and asks before edits, shell commands and external-directory access. Other non-conflicting global/project settings can still merge. CLI permissions are not OS isolation. A known upstream free-tier error can occur when tools are disabled: `OpenCode's free tier can only be used from within OpenCode`. Use the normal built-in coding agent and seek an upstream fix rather than switching silently to a paid model.

## Optional OpenCode ChatGPT login

To switch from Big Pickle to account-managed OpenAI models, edit local `.env`:

```dotenv
OPENCODE_PROVIDER=openai
OPENCODE_AUTH=chatgpt
```

Install OpenCode if needed, then check and open it in an existing customer folder:

```powershell
npm install -g opencode-ai
.\.venv\Scripts\python.exe tools/opencode.py --check
.\.venv\Scripts\python.exe tools/opencode.py --start --project 'D:\Projects\customer-app'
```

Skip installation when the CLI is already available. Inside the OpenCode terminal:

1. Enter `/connect`, choose **OpenAI**, then **ChatGPT Plus/Pro**.
2. Complete the browser sign-in with the intended account and return to the terminal.
3. Enter `/models` and choose an available OpenAI model. Use the account's model list rather than copying an API model ID.
4. Give it a small project task and inspect the result before assigning a larger job.

This is the [official OpenCode OpenAI login workflow](https://opencode.ai/docs/providers/#openai). The `opencode.chatgpt.json` preset uses the built-in provider and live picker without injecting an API key, custom endpoint or fixed model. The helper removes API-key variables from this child process. It does not read either tool's authentication file.

`ready_for_opencode=true` means the CLI can be launched with the local configuration. `authentication_verified=false` and `provider_access_verified=false` remain explicit: `--check` does not inspect OpenCode credentials or perform inference. An existing API-key connection or global/project provider override must be reviewed and switched in OpenCode if you want subscription use. This mode alone does not prove which login is saved inside OpenCode.

The selected template disables sharing and asks before edits, shell commands and external-directory access. OpenCode merges its own global/project configuration; review those settings if behavior differs from the template. These permissions are not OS isolation.

## 6. Optional OpenCode API-key mode

For separate API access, set:

```dotenv
OPENCODE_AUTH=api_key
OPENCODE_PROVIDER=openai
OPENCODE_BASE_URL=https://api.openai.com/v1
OPENCODE_MODEL=openai/gpt-6.1-sol
OPENCODE_SMALL_MODEL=openai/gpt-6-luna
OFFICE_MODEL_KEY=
```

Create an OpenAI project API key in [OpenAI Platform](https://platform.openai.com/api-keys), check API billing/model access and paste it into `OFFICE_MODEL_KEY` in local `.env`. Keep `OFFICE_MODEL_PROTOCOL=codex_cli` for office stages. The same check/start commands now select `opencode.openai.json` and require the key. API presets for ProxyAPI and Claude explicitly use `OPENCODE_AUTH=api_key`; see [PROVIDERS.md](PROVIDERS.md).

The API key enters the child environment, not command arguments or committed JSON. The main/small model IDs are API examples and require account access. `small_model` handles internal lightweight work such as titles; it does not route office stages or every small development task.

Neither interactive launcher automatically imports its resulting code into office materials. Both sessions are owner-driven and distinct from automatic office stages.

## Optional providers and Docker

Direct OpenAI office calls use [config/openai.env.example](../config/openai.env.example). ProxyAPI and Claude retain their existing presets. See [PROVIDERS.md](PROVIDERS.md).

The standard Docker image does not bundle Codex or mount host login credentials. Use the native host workflow for Codex. For Docker office calls, select an API preset and configure its key deliberately.

## Official references

- [Non-interactive Codex](https://learn.chatgpt.com/docs/non-interactive-mode): saved CLI authentication, JSON events and read-only execution.
- [CLI commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli): login status, execution flags and interactive options.
- [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference): authentication method and tool/config settings.
- [OpenCode configuration](https://opencode.ai/docs/config/) and [providers](https://opencode.ai/docs/providers/).

Offline tests simulate CLI processes and HTTP providers. A real Codex text-stage smoke test passed with saved ChatGPT login and the CLI default model; its safe result is in `output/codex-smoke.json`. A real Big Pickle response through OpenCode CLI also passed with reported cost `0`; see `output/big-pickle-smoke.json`. Optional OpenCode ChatGPT/API authentication and customer coding tools have not been live-tested. Consult [VALIDATION.md](../VALIDATION.md) for recorded checks and limits.
