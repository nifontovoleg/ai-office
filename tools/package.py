"""Make a portable source + built UI archive, excluding local credentials/data."""
import hashlib
import os
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root.parent / "AI-Office.zip"
excluded = {"node_modules", ".venv", ".qa-python", ".repo-prep", ".git", "__pycache__", "data"}
files = []
for directory, dirs, names in os.walk(root):
    dirs[:] = [name for name in dirs if name not in excluded]
    for name in names:
        path = Path(directory) / name
        private_environment = (name == ".env" or name.startswith(".env.")) and name != ".env.example"
        private_credentials = name.endswith((".pem", ".key")) or (name.startswith("credentials") and name.endswith(".json"))
        if private_environment or private_credentials or name.endswith((".pyc", ".tsbuildinfo", "failure.png")) or name == "initial-dom.txt":
            continue
        files.append(path)
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in sorted(files):
        archive.write(path, "ai-office/" + path.relative_to(root).as_posix())
with zipfile.ZipFile(target) as archive:
    assert archive.testzip() is None
    names = archive.namelist()
    assert "ai-office/frontend/dist/index.html" in names
    assert "ai-office/ЗАПУСТИТЬ.cmd" in names
    assert sum(name.startswith("ai-office/catalog/profiles/") and name.endswith(".md") for name in names) == 282
    assert not any("/node_modules/" in name or "/.venv/" in name or "/data/" in name or ((Path(name).name == ".env" or Path(name).name.startswith(".env.")) and Path(name).name != ".env.example") for name in names)
print({"archive": str(target), "files": len(files), "bytes": target.stat().st_size, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "crc": "passed", "profiles": 282})
