"""Saved-ChatGPT Codex CLI transport for text-only office stages."""
import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

API_ENV = {"OFFICE_MODEL_KEY", "OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "OPENAI_BASE_URL", "OPENAI_API_BASE"}
DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "apps", "plugins", "hooks", "multi_agent",
    "browser_use", "computer_use", "image_generation", "view_image",
    "memories", "skill_search", "workspace_dependencies", "code_mode_host", "shell_snapshot",
)
MAX_RESULT_BYTES = 4 * 1024 * 1024


def child_environment(source=None):
    # Saved CLI login is the only credential path for this transport.
    return {key: value for key, value in (os.environ if source is None else source).items() if key not in API_ENV}


def find_cli(settings=None):
    settings = os.environ if settings is None else settings
    explicit = settings.get("OFFICE_CODEX_PATH", "").strip()
    if explicit:
        path = Path(explicit)
        if not path.is_absolute() or not path.is_file():
            return None
        if os.name == "nt" and path.suffix.lower() != ".exe":
            return None
        return str(path)
    return shutil.which("codex.exe" if os.name == "nt" else "codex")


def login_mode(returncode, output):
    if returncode != 0:
        return "not_logged_in"
    if "chatgpt" in output.lower():
        return "chatgpt"
    if "api key" in output.lower():
        return "api_key"
    return "unknown"


def check_login(cli, settings=None):
    if not cli:
        return "unavailable"
    try:
        result = subprocess.run([cli, "login", "status"], env=child_environment(settings), capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    return login_mode(result.returncode, (result.stdout + result.stderr).decode("utf-8", errors="replace"))


def model_option(settings):
    model = settings.get("OFFICE_MODEL_NAME", "").strip()
    if model and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", model):
        raise ValueError("Некорректное имя модели Codex в серверном .env.")
    return ["--model", model] if model else []


def office_command(cli, directory, policy, settings):
    command = [cli, "exec", "--ignore-user-config", "--ephemeral", "--json", "--sandbox", "read-only", "--skip-git-repo-check", "--cd", str(directory)]
    command += model_option(settings)
    for feature in DISABLED_FEATURES:
        command += ["--disable", feature]
    for override in (
        'forced_login_method="chatgpt"', 'model_provider="openai"',
        'approval_policy="never"',
        'web_search="disabled"', 'model_reasoning_effort="low"',
        "project_doc_max_bytes=0", 'history.persistence="none"',
        "developer_instructions=" + json.dumps(policy, ensure_ascii=False),
    ):
        command += ["--config", override]
    return command + ["-"]


def parse_result(output):
    if len(output) > MAX_RESULT_BYTES:
        raise ValueError("Результат Codex превышает допустимый размер.")
    content, completed, started, usage = None, False, False, None
    try:
        for line in output.decode("utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError
            kind = event.get("type")
            if not isinstance(kind, str):
                raise ValueError
            if kind in ("error", "turn.failed"):
                raise ValueError
            if kind == "turn.started":
                started = True
            if kind and kind.startswith("item."):
                item = event["item"]
                # CLI initialization can announce disabled optional capabilities.
                # A later successful turn is still required; turn errors stay fatal.
                if item["type"] == "error" and not started:
                    continue
                if item["type"] not in ("agent_message", "reasoning", "plan"):
                    raise ValueError
                if kind == "item.completed" and item["type"] == "agent_message":
                    content = item["text"]
            if kind == "turn.completed":
                completed = True
                raw = event.get("usage")
                if isinstance(raw, dict):
                    incoming, outgoing = raw.get("input_tokens"), raw.get("output_tokens")
                    if all(type(value) is int and value >= 0 for value in (incoming, outgoing)):
                        # cached_input_tokens is a subset of input_tokens, not an extra count.
                        usage = {"prompt_tokens": incoming, "completion_tokens": outgoing, "total_tokens": incoming + outgoing}
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise ValueError("Codex вернул ошибку или некорректный поток результата. Проверьте вход, лимиты и версию CLI.") from None
    if not completed or not isinstance(content, str) or not content.strip():
        raise ValueError("Codex не завершил этап текстовым результатом.")
    return {"content": content, "usage": usage, "cost": None}


async def run_cli(command, directory, env, timeout, prompt=None):
    try:
        process = await asyncio.create_subprocess_exec(
            *command, cwd=directory, env=env,
            stdin=asyncio.subprocess.PIPE if prompt is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except OSError:
        raise ValueError("Не удалось запустить Codex CLI. Проверьте установку и права доступа.") from None
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(prompt), timeout=timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError) as error:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        await process.communicate()
        if isinstance(error, asyncio.CancelledError):
            raise
        raise ValueError("Превышено время ожидания Codex. Проверьте доступ и повторите этап явно.") from None
    return process.returncode, stdout, stderr


class CodexAdapter:
    def __init__(self):
        self.lock = asyncio.Lock()

    async def execute(self, payload, policy):
        cli = find_cli()
        if not cli:
            raise ValueError("Codex CLI не найден. Установите его или задайте OFFICE_CODEX_PATH.")
        try:
            timeout = int(os.getenv("OFFICE_CODEX_TIMEOUT_SECONDS", "300"))
            if not 30 <= timeout <= 1800:
                raise ValueError
        except ValueError:
            raise ValueError("OFFICE_CODEX_TIMEOUT_SECONDS должен быть от 30 до 1800.") from None
        model_option(os.environ)
        prompt = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(prompt) > 2 * 1024 * 1024:
            raise ValueError("Контекст этапа слишком велик для Codex. Сократите выбранные материалы.")
        env = child_environment()
        async with self.lock:
            with tempfile.TemporaryDirectory(prefix="ai-office-codex-") as directory:
                code, out, err = await run_cli([cli, "login", "status"], directory, env, 10)
                if login_mode(code, (out + err).decode("utf-8", errors="replace")) != "chatgpt":
                    raise ValueError("Для этого режима нужен вход Codex через ChatGPT. Выполните codex login и проверьте codex login status.")
                command = office_command(cli, directory, policy, os.environ)
                code, out, _ = await run_cli(command, directory, env, timeout, prompt)
                if code != 0:
                    raise ValueError("Codex не выполнил этап. Проверьте вход ChatGPT, лимиты, модель и версию CLI (0.147.0+).")
                return parse_result(out)
