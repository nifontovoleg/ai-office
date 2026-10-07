"""Check repository documentation links and the staged publication boundary."""
import json
import hashlib
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
errors = []
documents = [ROOT / name for name in ("README.md", "VALIDATION.md", "CONTRIBUTING.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md", "CHANGELOG.md")]
documents += list((ROOT / "docs").glob("*.md"))
documents += [ROOT / "catalog/README.md"]
for path in documents:
    content = path.read_text(encoding="utf-8")
    links = re.findall(r"\]\(([^)]+)\)", content) + re.findall(r'(?:src|href)="([^"]+)"', content)
    for link in links:
        if link.startswith(("http:", "https:", "mailto:", "#")):
            continue
        target = link.split("#", 1)[0]
        if target and not (path.parent / target).exists():
            errors.append(f"Missing document target: {path.relative_to(ROOT)} -> {target}")
ElementTree.parse(ROOT / "docs/assets/banner.svg")
result = subprocess.run(["git", "ls-files", "--cached", "-z"], cwd=ROOT, capture_output=True, check=True)
paths = [name for name in result.stdout.decode("utf-8").split("\0") if name]
blocked = {".venv", ".qa-python", "node_modules", "data", ".repo-prep", "__pycache__"}
secret_patterns = [r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})", r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{40,}-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", r"\bAKIA[0-9A-Z]{16}\b", r"\bsk-proj-[A-Za-z0-9_-]{40,}\b"]
for name in paths:
    path = Path(name)
    if blocked.intersection(path.parts) or (path.name.startswith(".env") and path.name != ".env.example"):
        errors.append(f"Local-only file staged: {name}")
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".ico"}:
        continue
    text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
    if any(re.search(pattern, text.replace("\\n", "\n")) for pattern in secret_patterns):
        errors.append(f"Potential credential marker staged; inspect privately: {name}")
profiles = sum(name.startswith("catalog/profiles/") and name.endswith(".md") for name in paths)
if paths and profiles != 282:
    errors.append(f"Expected 282 staged source profiles; found {profiles}")
if paths:
    source = json.loads((ROOT / "catalog/agents.json").read_text(encoding="utf-8-sig"))
    records = source["agents"]
    refs = [":catalog/" + profile["profile_path"] for profile in records]
    blobs = subprocess.run(["git", "cat-file", "--batch"], cwd=ROOT, input=("\n".join(refs) + "\n").encode(), capture_output=True, check=True).stdout
    offset = 0
    for profile in records:
        end = blobs.index(b"\n", offset)
        header = blobs[offset:end].split()
        if len(header) != 3 or header[1] != b"blob":
            errors.append(f"Missing staged source blob: {profile['id']}")
            break
        size = int(header[2])
        payload = blobs[end + 1:end + 1 + size]
        if hashlib.sha256(payload).hexdigest() != profile["source_sha256"]:
            errors.append(f"Staged source checksum differs: {profile['id']}")
        offset = end + 1 + size + 1
if errors:
    for error in errors:
        print(error)
    raise SystemExit(1)
print(json.dumps({"documents": len(documents), "links": "passed", "banner_xml": "passed", "staged_files": len(paths), "staged_profiles": profiles, "source_checksums": "passed", "publication_boundary": "passed"}))
