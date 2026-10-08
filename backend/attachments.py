"""Bounded local attachments; originals never enter the model payload."""
import asyncio
import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import subprocess
import sys
import unicodedata
import uuid
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from fastapi import HTTPException

from .store import now

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_EXTRACT_BYTES = 10 * 1024 * 1024
MAX_CONTENT_CHARS = 100_000
EXTRACTION_TIMEOUT_SECONDS = 15
EXTRACTION_STATUSES = {"extracted", "truncated", "empty", "unsupported", "failed"}
PREVIEW_MIME_TYPES = {
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp", "image/avif",
    "video/mp4", "video/quicktime", "video/webm", "video/ogg",
    "audio/mpeg", "audio/mp4", "audio/ogg", "audio/wav", "audio/flac", "audio/aac",
}
PUBLIC_ATTACHMENT_FIELDS = ("filename", "size", "mime_type", "sha256", "extraction_status", "extraction_note")
TEXT_SUFFIXES = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl", ".xml", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".log", ".py", ".js", ".jsx", ".ts", ".tsx", ".html",
    ".htm", ".css", ".scss", ".less", ".sql", ".sh", ".ps1", ".bat", ".cmd", ".c", ".h",
    ".cpp", ".hpp", ".rs", ".go", ".java", ".kt", ".swift", ".php", ".rb", ".r", ".svg",
    ".ipynb", ".env", ".gitignore", ".dockerignore", ".srt", ".vtt", ".tex",
}
_MATERIAL_ID = re.compile(r"mat-[0-9a-f]{12}(?:[0-9a-f]{20})?\Z")
_RESERVED_NAME = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.IGNORECASE)


def validate_filename(filename):
    filename = unicodedata.normalize("NFC", filename)
    if (not filename or len(filename) > 200 or len(filename.encode("utf-8", errors="replace")) > 600
            or filename != filename.strip() or filename.endswith(".")
            or filename in (".", "..") or _RESERVED_NAME.match(filename)
            or any(char in '/\\<>:"|?*' or unicodedata.category(char).startswith("C") for char in filename)):
        raise HTTPException(422, "Нужно безопасное имя файла без пути и управляющих символов (до 200 символов)")
    return filename


def validate_link(url):
    if (not url or len(url) > 4096
            or any(char.isspace() or unicodedata.category(char).startswith("C") or char == "\\" for char in url)):
        raise ValueError("Ссылка должна быть корректным HTTP/HTTPS URL без пробелов и управляющих символов")
    if (re.search(r"%(?![0-9a-fA-F]{2})", url)
            or any(unicodedata.category(char).startswith("C") for char in unquote(url))):
        raise ValueError("Ссылка содержит некорректное кодирование или управляющие символы")
    try:
        target = urlsplit(url)
        if target.scheme not in ("http", "https") or not target.hostname or target.username is not None or target.password is not None:
            raise ValueError
        hostname = target.hostname
        if "%" in hostname or target.netloc.endswith(":"):
            raise ValueError
        # Accessing .port validates both its syntax and the allowed range.
        target.port
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            ascii_host = hostname.encode("idna").decode("ascii").rstrip(".")
            labels = ascii_host.split(".")
            if len(ascii_host) > 253 or any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels):
                raise ValueError
        if ":" in hostname and not re.fullmatch(r"\[[0-9A-Fa-f:.]+\](?::[0-9]+)?", target.netloc):
            raise ValueError
    except (ValueError, UnicodeError):
        raise ValueError("Разрешены корректные HTTP/HTTPS ссылки с именем хоста, без логина и пароля") from None
    return url


def attachment_directory(store):
    root = store.directory.resolve()
    directory = root / "attachments"
    directory.mkdir(exist_ok=True)
    if directory.is_symlink() or directory.resolve().parent != root:
        raise ValueError("Каталог вложений должен находиться внутри данных офиса")
    return directory


def attachment_path(store, material):
    material_id = material.get("id", "")
    if not material.get("attachment") or not _MATERIAL_ID.fullmatch(material_id):
        raise HTTPException(404, "У материала нет файла")
    path = attachment_directory(store) / material_id
    if path.is_symlink() or not path.is_file():
        raise HTTPException(404, "Оригинал файла не найден")
    return path


def sniff_mime(path, filename):
    with path.open("rb") as stream:
        head = stream.read(4096)
    suffix = Path(filename).suffix.lower()
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head.startswith(b"BM"):
        return "image/bmp"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "audio/wav"
    if head[4:8] == b"ftyp":
        brands = head[8:32]
        if b"avif" in brands or b"avis" in brands:
            return "image/avif"
        if b"qt  " in brands:
            return "video/quicktime"
        if suffix in (".m4a", ".m4b") or b"M4A " in brands:
            return "audio/mp4"
        return "video/mp4"
    if head.startswith(b"\x1aE\xdf\xa3") and suffix == ".webm":
        return "video/webm"
    if head.startswith(b"OggS"):
        return "video/ogg" if suffix == ".ogv" else "audio/ogg"
    if head.startswith(b"fLaC"):
        return "audio/flac"
    if head.startswith(b"ID3") or (suffix == ".mp3" and len(head) > 1 and head[0] == 255 and head[1] & 0xE0 == 0xE0):
        return "audio/mpeg"
    if suffix == ".aac" and len(head) > 1 and head[0] == 255 and head[1] & 0xF6 == 0xF0:
        return "audio/aac"
    if b"%PDF-" in head[:1024]:
        return "application/pdf"
    if suffix == ".docx" and head.startswith(b"PK"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if suffix in TEXT_SUFFIXES or filename.lower() in ("dockerfile", "makefile", "license", "readme"):
        return mimetypes.guess_type(filename)[0] or "text/plain"
    guessed = mimetypes.guess_type(filename)[0]
    # A filename alone cannot turn HTML or arbitrary bytes into a previewable resource.
    return guessed if guessed and guessed not in PREVIEW_MIME_TYPES else "application/octet-stream"


def extraction_kind(filename, mime_type):
    suffix = Path(filename).suffix.lower()
    if mime_type == "application/pdf" or suffix == ".pdf":
        return "pdf"
    if suffix == ".docx":
        return "docx"
    if (suffix in TEXT_SUFFIXES or mime_type.startswith("text/")
            or mime_type in ("application/json", "application/xml")
            or filename.lower() in ("dockerfile", "makefile", "license", "readme")):
        return "text"
    return None


def reference_content(filename, size, mime_type, note):
    return f"Файл: {filename}\nТип: {mime_type}\nРазмер: {size} байт.\n\n{note}\n\nОригинал сохранён. В контекст этапа передаются только это описание и метаданные файла; двоичное содержимое не передаётся модели."


def parser_environment():
    # Do not inherit OFFICE_MODEL_KEY, provider keys, proxies, or user credentials.
    allowed = {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL"}
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def stop_parser(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        # A Windows venv executable may be a launcher whose child owns the pipes.
        # Restrict tree termination to the PID returned by this exact Popen call.
        taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
        if taskkill.is_absolute() and taskkill.is_file():
            try:
                subprocess.run(
                    [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    env=parser_environment(), timeout=5, check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
    if process.poll() is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass


async def extract_file(path, filename, size, mime_type):
    kind = extraction_kind(filename, mime_type)
    if not size:
        return {"status": "empty", "note": "Файл пустой; текст отсутствует.", "text": ""}
    if not kind:
        return {"status": "unsupported", "note": "Этот формат сохранён без распознавания содержимого. Извлечение текста, OCR и расшифровка медиа для него не выполнялись.", "text": ""}
    if size > MAX_EXTRACT_BYTES:
        return {"status": "unsupported", "note": "Извлечение пропущено: файл больше 10 МБ. Оригинал сохранён полностью.", "text": ""}
    script = Path(__file__).with_name("extract_attachment.py").resolve()
    process = subprocess.Popen(
        [sys.executable, "-I", str(script), str(path.resolve()), kind],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env=parser_environment(), cwd=str(script.parent),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    communication = asyncio.create_task(asyncio.to_thread(process.communicate, timeout=EXTRACTION_TIMEOUT_SECONDS))
    try:
        output, _ = await asyncio.shield(communication)
        if process.returncode or len(output) > MAX_CONTENT_CHARS * 6 + 10_000:
            raise ValueError("Invalid parser output")
        result = json.loads(output)
        if (not isinstance(result, dict) or result.get("status") not in EXTRACTION_STATUSES
                or not isinstance(result.get("text"), str) or len(result["text"]) > MAX_CONTENT_CHARS
                or not isinstance(result.get("note"), str) or len(result["note"]) > 2000):
            raise ValueError("Invalid parser output")
        return result
    except asyncio.CancelledError:
        raise
    except subprocess.TimeoutExpired:
        return {"status": "failed", "note": "Извлечение остановлено по тайм-ауту (15 секунд). Оригинал сохранён.", "text": ""}
    except (ValueError, UnicodeError):
        return {"status": "failed", "note": "Не удалось безопасно извлечь текст. Оригинал сохранён.", "text": ""}
    finally:
        if process.poll() is None:
            await asyncio.to_thread(stop_parser, process)
        # A cancelled HTTP request must not leave a parser process behind.
        await asyncio.gather(communication, return_exceptions=True)
        # After a timed out communicate(), drain/close its pipes and reap the child.
        await asyncio.to_thread(process.communicate)


async def upload_material(store, project_id, request, filename, extraction_slots):
    try:
        store.get("projects", project_id)
    except ValueError:
        raise HTTPException(404, "Проект не найден") from None
    filename = validate_filename(filename)
    length = request.headers.get("content-length")
    if length is not None:
        try:
            length = int(length)
            if length < 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "Некорректный Content-Length") from None
        if length > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Максимальный размер файла — 50 МБ")
    material_id = "mat-" + uuid.uuid4().hex
    directory = attachment_directory(store)
    partial = directory / (material_id + ".partial")
    original = directory / material_id
    retained = False
    digest = hashlib.sha256()
    size = 0
    try:
        with partial.open("xb") as stream:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Максимальный размер файла — 50 МБ")
                stream.write(chunk)
                digest.update(chunk)
        if length is not None and size != length:
            raise HTTPException(400, "Размер полученного файла не совпадает с Content-Length")
        partial.replace(original)
        sha256 = digest.hexdigest()
        duplicate = store.find_source_duplicate(project_id, filename=filename, sha256=sha256)
        if duplicate:
            return duplicate
        mime_type = sniff_mime(original, filename)
        try:
            async with extraction_slots:
                result = await extract_file(original, filename, size, mime_type)
        except OSError:
            result = {"status": "failed", "note": "Процесс извлечения недоступен. Оригинал сохранён.", "text": ""}
        attachment = {"filename": filename, "size": size, "mime_type": mime_type, "sha256": sha256,
                      "extraction_status": result["status"], "extraction_note": result["note"]}
        material = {"id": material_id, "project_id": project_id, "task_id": None, "title": filename,
                    "content": result["text"] or reference_content(filename, size, mime_type, result["note"]),
                    "kind": "source", "example": False, "created_at": now(), "agent_id": None,
                    "attachment": attachment}
        saved, created = store.add_source_material(material)
        retained = created
        return saved
    finally:
        partial.unlink(missing_ok=True)
        if not retained:
            original.unlink(missing_ok=True)


def content_disposition(filename, disposition="attachment"):
    suffix = Path(filename).suffix.lower()
    fallback = "file" + (suffix if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix) else ".bin")
    return f'{disposition}; filename="{fallback}"; filename*=UTF-8\'\'{quote(filename, safe="")}'


def selected_material(material):
    """Only public metadata and extracted content can be passed to an executor."""
    result = {key: material[key] for key in ("id", "title", "content")}
    if material.get("source_url"):
        result["source_url"] = material["source_url"]
    if material.get("attachment"):
        result["attachment"] = {key: material["attachment"][key] for key in PUBLIC_ATTACHMENT_FIELDS if key in material["attachment"]}
    return result
