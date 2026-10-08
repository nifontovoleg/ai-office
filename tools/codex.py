"""Check saved Codex ChatGPT login or explicitly open a customer coding session."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.codex import check_login, child_environment, find_cli, model_option


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Inspect installation and saved login without model inference.")
    mode.add_argument("--start", action="store_true", help="Explicitly open an interactive coding session.")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--project", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        settings = {key: value for key, value in (dotenv_values(args.env_file, interpolate=False) if args.env_file.is_file() else {}).items() if value is not None}
        settings.update(os.environ)
        model_args = model_option(settings)
    except (ValueError, OSError):
        print("Invalid local Codex settings. Check the model and env file.", file=sys.stderr)
        return 1
    cli = find_cli(settings)
    login = check_login(cli, settings)
    ready = bool(cli) and login == "chatgpt"
    print(json.dumps({"cli_available": bool(cli), "login_method": login, "ready_for_codex": ready, "model": settings.get("OFFICE_MODEL_NAME") or "CLI default", "office_protocol": settings.get("OFFICE_MODEL_PROTOCOL", "chat_completions"), "provider_access_verified": False, "api_key_required": False}, indent=2))
    if not args.start:
        return 0
    if not ready:
        print("Install Codex CLI and complete codex login with ChatGPT before starting.", file=sys.stderr)
        return 1
    project = args.project.resolve()
    if not project.is_dir():
        print("The project directory must already exist.", file=sys.stderr)
        return 1
    command = [cli, "--cd", str(project), "--sandbox", "workspace-write", "--ask-for-approval", "on-request", "--config", 'forced_login_method="chatgpt"'] + model_args
    try:
        return subprocess.run(command, cwd=project, env=child_environment(settings), check=False).returncode
    except OSError:
        print("Codex could not start. Check its installation and permissions.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
