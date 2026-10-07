"""Load a local env file and check or explicitly launch an OpenCode session.

No HTTP request is made by this helper. Keys only enter the child environment.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = {
    "openai": {
        "OPENCODE_BASE_URL": "https://api.openai.com/v1",
        "OPENCODE_MODEL": "openai/gpt-6.1-sol",
        "OPENCODE_SMALL_MODEL": "openai/gpt-6-luna",
    },
    "proxyapi": {
        "OPENCODE_BASE_URL": "https://api.proxyapi.ru/v1",
        "OPENCODE_MODEL": "proxyapi/openai/gpt-6.1-sol",
        "OPENCODE_SMALL_MODEL": "proxyapi/openai/gpt-6-luna",
    },
    "anthropic": {
        "OPENCODE_BASE_URL": "https://api.anthropic.com/v1",
        "OPENCODE_MODEL": "anthropic/claude-sonnet-5-5",
        "OPENCODE_SMALL_MODEL": "anthropic/claude-haiku-5-5",
    },
}


def load_settings(env_file, inherited=None):
    # Disable interpolation: a secret containing '$' must stay unchanged.
    local = dotenv_values(env_file, interpolate=False) if env_file.is_file() else {}
    settings = {key: value for key, value in local.items() if value is not None}
    settings.update(os.environ if inherited is None else inherited)
    provider = settings.get("OPENCODE_PROVIDER", "openai")
    if provider not in DEFAULTS:
        raise ValueError("OPENCODE_PROVIDER must be openai, proxyapi or anthropic.")
    for key, value in DEFAULTS[provider].items():
        settings.setdefault(key, value)
    settings["OPENCODE_PROVIDER"] = provider
    url = urlsplit(settings["OPENCODE_BASE_URL"])
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.query or url.fragment or not url.path.rstrip("/").endswith("/v1")):
        raise ValueError("OPENCODE_BASE_URL must be an HTTPS /v1 base URL without credentials or a query.")
    config_path = ROOT / "config" / f"opencode.{provider}.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    models = config["provider"][provider]["models"]
    for key in ("OPENCODE_MODEL", "OPENCODE_SMALL_MODEL"):
        model = settings[key]
        prefix = provider + "/"
        if not model.startswith(prefix) or model[len(prefix):] not in models:
            raise ValueError(f"{key} must name a model registered in the selected config template.")
    # Explicit selection also prevents a caller's OPENCODE_CONFIG_CONTENT override.
    settings.pop("OPENCODE_CONFIG_CONTENT", None)
    settings["OPENCODE_CONFIG"] = str(config_path)
    return settings


def find_cli():
    if os.name != "nt":
        return shutil.which("opencode")
    executable = shutil.which("opencode.exe")
    if executable:
        return executable
    # Invoke the executable behind npm's shim directly, without a shell.
    shim = shutil.which("opencode") or shutil.which("opencode.cmd")
    if shim:
        executable = Path(shim).parent / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
        if executable.is_file():
            return str(executable)
    return None


def summary(settings, cli):
    key_present = bool(settings.get("OFFICE_MODEL_KEY", "").strip())
    return {
        "provider": settings["OPENCODE_PROVIDER"],
        "base_url": settings["OPENCODE_BASE_URL"],
        "model": settings["OPENCODE_MODEL"],
        "small_model": settings["OPENCODE_SMALL_MODEL"],
        "key_present": key_present,
        "cli_available": bool(cli),
        "ready_for_opencode": key_present and bool(cli),
        "provider_access_verified": False,
        "office_model_enabled": settings.get("OFFICE_ENABLE_MODEL", "false").lower() == "true",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Check local settings only (the default).")
    mode.add_argument("--start", action="store_true", help="Start OpenCode explicitly; model use may incur charges.")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--project", type=Path, default=ROOT, help="Existing customer project directory.")
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.env_file)
    except (ValueError, OSError):
        # Config errors must never echo env contents, URL credentials or keys.
        print("Invalid OpenCode configuration. Check the provider, HTTPS /v1 URL and model IDs in .env.", file=sys.stderr)
        return 1
    cli = find_cli()
    state = summary(settings, cli)
    print(json.dumps(state, indent=2))
    if not args.start:
        return 0
    if not state["ready_for_opencode"]:
        print("Set OFFICE_MODEL_KEY in .env and install the OpenCode CLI before starting.", file=sys.stderr)
        return 1
    project = args.project.resolve()
    if not project.is_dir():
        print("The customer project directory must already exist.", file=sys.stderr)
        return 1
    try:
        return subprocess.run([cli, str(project)], cwd=project, env=settings, check=False).returncode
    except OSError:
        print("OpenCode could not start. Check its installation and executable permissions.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
