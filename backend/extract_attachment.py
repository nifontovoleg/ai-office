"""Isolated, bounded parser. Run by absolute script path with Python -I."""
import json
import os
import re
import sys
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree

MAX_BYTES = 10 * 1024 * 1024
MAX_CHARS = 100_000
MAX_PDF_PAGES = 200
MAX_PDF_PAGE_BYTES = 5 * 1024 * 1024
MAX_PDF_DECODED_BYTES = 20 * 1024 * 1024
MAX_PROCESS_MEMORY = 512 * 1024 * 1024
MAX_ZIP_MEMBERS = 1000
MAX_ZIP_UNCOMPRESSED = 30 * 1024 * 1024
MAX_XML_BYTES = 5 * 1024 * 1024


def clean_text(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(char for char in text if char in "\n\t" or not unicodedata.category(char).startswith("C"))


def finish(text, truncated=False, note=""):
    text = clean_text(text)
    truncated = truncated or len(text) > MAX_CHARS
    text = text[:MAX_CHARS]
    if not text.strip():
        if truncated:
            return {"status": "truncated", "text": "", "note": note or "Извлечение остановлено на безопасном пределе объёма или страниц. В обработанной части текст не найден; оригинал сохранён полностью."}
        return {"status": "empty", "text": "", "note": note or "Текст не найден. Для сканированных страниц OCR не выполнялся."}
    return {"status": "truncated" if truncated else "extracted", "text": text,
            "note": note or ("Текст извлечён частично: достигнут лимит объёма или страниц. Оригинал сохранён полностью." if truncated else "Текст извлечён. Оригинал сохранён полностью.")}


def extract_text(path):
    raw = path.read_bytes()
    encodings = ["utf-8-sig"]
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings.insert(0, "utf-16")
    if raw.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        encodings.insert(0, "utf-32")
    encodings.append("cp1251")
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
        except UnicodeError:
            continue
        # Do not turn executables or other binary blobs with a text suffix into context.
        invalid = sum(char not in "\n\r\t" and unicodedata.category(char).startswith("C") for char in text)
        if "\x00" in text or invalid > max(2, len(text) // 100):
            continue
        return finish(text)
    return {"status": "failed", "text": "", "note": "Файл не удалось прочитать как безопасный текст в UTF-8, UTF-16/32 с BOM или Windows-1251."}


def extract_pdf(path):
    from pypdf import PdfReader, overwrite_configuration
    # Apply limits before reading objects or decompressing content streams. The
    # configured library itself stops expansion before allocating oversized data.
    overwrite_configuration(
        maximum_declared_stream_length=MAX_BYTES,
        array_based_stream_maximum_output_length=MAX_PDF_PAGE_BYTES,
        zlib_maximum_output_length=MAX_PDF_PAGE_BYTES,
        zlib_maximum_recovery_input_length=1_000_000,
        lzw_maximum_output_length=MAX_PDF_PAGE_BYTES,
        run_length_maximum_output_length=MAX_PDF_PAGE_BYTES,
        jbig2_maximum_output_length=MAX_PDF_PAGE_BYTES,
        image_maximum_buffer_size=MAX_PDF_PAGE_BYTES,
        flate_maximum_row_length=1_000_000,
        page_tree_maximum_entries=2000,
        page_tree_maximum_depth=30,
        xform_maximum_invocations_per_extraction=1000,
        jbig2dec_binary=None,
        disable_legacy_handling=True,
    )
    reader = PdfReader(path, strict=True)
    if reader.is_encrypted:
        return {"status": "failed", "text": "", "note": "PDF защищён паролем. Оригинал сохранён; извлечение не выполнено."}
    output = []
    chars = 0
    decoded_bytes = 0
    count = len(reader.pages)
    truncated = count > MAX_PDF_PAGES
    for index in range(min(count, MAX_PDF_PAGES)):
        page = reader.pages[index]
        content = page.get_contents()
        if content is not None:
            size = len(content.get_data())
            decoded_bytes += size
            if size > MAX_PDF_PAGE_BYTES or decoded_bytes > MAX_PDF_DECODED_BYTES:
                truncated = True
                break
        text = page.extract_text() or ""
        remaining = MAX_CHARS + 1 - chars
        output.append(text[:remaining])
        chars += len(output[-1]) + 2
        if chars > MAX_CHARS:
            truncated = True
            break
    return finish("\n\n".join(output), truncated)


def extract_docx(path):
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if (len(members) > MAX_ZIP_MEMBERS or sum(member.file_size for member in members) > MAX_ZIP_UNCOMPRESSED
                or any(member.flag_bits & 1 or member.file_size > MAX_ZIP_UNCOMPRESSED for member in members)):
            raise ValueError("Archive limits")
        names = [member.filename for member in members]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate archive members")
        chosen = [name for name in names if name == "word/document.xml" or re.fullmatch(r"word/(?:header|footer)\d+\.xml", name)]
        if "word/document.xml" not in chosen:
            raise ValueError("Not a DOCX document")
        chosen.sort(key=lambda name: (name != "word/document.xml", name))
        output = []
        chars = 0
        for name in chosen:
            member = archive.getinfo(name)
            if member.file_size > MAX_XML_BYTES or (member.compress_size and member.file_size > member.compress_size * 200):
                raise ValueError("XML limits")
            with archive.open(member) as stream:
                raw = stream.read(MAX_XML_BYTES + 1)
            if len(raw) > MAX_XML_BYTES:
                raise ValueError("XML limits")
            # ElementTree does not resolve external entities. Also reject DTD/internal
            # entities in any common XML encoding before allowing parsing.
            declaration_scan = raw.replace(b"\x00", b"").upper()
            if b"<!DOCTYPE" in declaration_scan or b"<!ENTITY" in declaration_scan:
                raise ValueError("XML declarations")
            root = ElementTree.fromstring(raw)
            for node in root.iter():
                tag = node.tag.rsplit("}", 1)[-1]
                text = (node.text or "") if tag == "t" else "\t" if tag == "tab" else "\n" if tag in ("br", "cr", "p") else ""
                remaining = MAX_CHARS + 1 - chars
                output.append(text[:remaining])
                chars += len(output[-1])
                if chars > MAX_CHARS:
                    return finish("".join(output), True)
            output.append("\n")
            chars += 1
        return finish("".join(output))


def resource_limits():
    if os.name != "nt":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (MAX_PROCESS_MEMORY, MAX_PROCESS_MEMORY))
        resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
        return None
    # A Job Object constrains all allocations in the Windows parser, including
    # cached PDF fonts/XObjects which do not count toward extracted text length.
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    api.CreateJobObjectW.restype = wintypes.HANDLE
    api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api.SetInformationJobObject.restype = wintypes.BOOL
    api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    api.AssignProcessToJobObject.restype = wintypes.BOOL
    api.GetCurrentProcess.argtypes = []
    api.GetCurrentProcess.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    job = api.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    # PROCESS_MEMORY | PROCESS_TIME | ACTIVE_PROCESS, no subprocess execution.
    limits.BasicLimitInformation.LimitFlags = 0x100 | 0x2 | 0x8
    limits.BasicLimitInformation.PerProcessUserTimeLimit = 12 * 10_000_000
    limits.BasicLimitInformation.ActiveProcessLimit = 1
    limits.ProcessMemoryLimit = MAX_PROCESS_MEMORY
    if (not api.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
            or not api.AssignProcessToJobObject(job, api.GetCurrentProcess())):
        error = ctypes.get_last_error()
        api.CloseHandle(job)
        raise ctypes.WinError(error)
    return api, job


def main():
    guard = None
    try:
        # Fail closed if the operating system cannot enforce the parser ceiling.
        guard = resource_limits()
        path = Path(sys.argv[1])
        kind = sys.argv[2]
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("Input limit")
        parser = {"pdf": extract_pdf, "docx": extract_docx, "text": extract_text}[kind]
        result = parser(path)
    except Exception:
        # Parser diagnostics may contain user data or internal paths; do not return them.
        result = {"status": "failed", "text": "", "note": "Не удалось безопасно извлечь текст в заданных пределах. Оригинал сохранён."}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    if guard:
        guard[0].CloseHandle(guard[1])


if __name__ == "__main__":
    main()
