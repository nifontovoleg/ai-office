"""Project attachment workflows, extraction, permissions and hostile-input boundaries."""
import asyncio
import base64
import hashlib
import json
import os
import tempfile
import time
import subprocess
import unittest
from pathlib import Path
from urllib.parse import quote
from unittest.mock import patch

import httpx

from backend import store as store_module
from attachment_fixtures import docx_bytes, pdf_bytes, compressed_pdf_bytes

# main's import creates a default app; never let discovery touch a user's data.
_bootstrap = tempfile.TemporaryDirectory(prefix="attachments-bootstrap-")
with patch.dict(os.environ, {"OFFICE_DATA_DIR": _bootstrap.name}), patch.object(store_module, "DATA_DIR", Path(_bootstrap.name)):
    from backend.main import create_app, app as bootstrap_app
    from backend.store import Store, ROOT
bootstrap_app.state.store.close()
_bootstrap.cleanup()

FIRST = "agents-orchestrator"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII=")


class AttachmentCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="attachments-api-")
        self.store = Store(self.temp.name, ROOT / "catalog")
        self.app = create_app(self.store)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://localhost:4197")

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.app.state.engine.shutdown()
        self.store.close()
        self.temp.cleanup()

    async def upload(self, filename, content, pid="project-main", **kwargs):
        return await self.client.post(f"/api/projects/{pid}/materials/upload?filename={quote(filename, safe='')}", content=content, headers={"content-type": "application/octet-stream", **kwargs.pop("headers", {})}, **kwargs)

    def files(self):
        return {path.relative_to(self.store.directory) for path in self.store.directory.rglob("*") if path.is_file() and not path.name.startswith("office.db")}

    async def test_russian_text_upload_metadata_and_exact_original_download(self):
        data = "ТЗ: создать сайт автосервиса. Цвета: тёмный фон, розовый акцент.".encode()
        result = await self.upload("Техническое задание.txt", data)
        self.assertEqual(result.status_code, 200, result.text)
        material = result.json()
        self.assertEqual(material["kind"], "source")
        self.assertEqual(material["content"], data.decode())
        self.assertEqual(material["attachment"]["extraction_status"], "extracted")
        self.assertEqual(material["attachment"]["filename"], "Техническое задание.txt")
        self.assertEqual(material["attachment"]["size"], len(data))
        self.assertEqual(material["attachment"]["sha256"], hashlib.sha256(data).hexdigest())
        self.assertNotIn(self.temp.name, result.text)
        downloaded = await self.client.get(f"/api/projects/project-main/materials/{material['id']}/file")
        self.assertEqual(downloaded.content, data)
        self.assertIn("attachment", downloaded.headers["content-disposition"])
        self.assertIn("filename*=", downloaded.headers["content-disposition"])
        self.assertEqual(downloaded.headers.get("x-content-type-options"), "nosniff")
        markdown = await self.client.get(f"/api/materials/{material['id']}/download")
        self.assertEqual(markdown.text, data.decode())

    async def test_pdf_extracts_readable_requirements_and_retains_bytes(self):
        data = pdf_bytes()
        result = await self.upload("brief.pdf", data)
        self.assertEqual(result.status_code, 200, result.text)
        material = result.json()
        self.assertEqual(material["attachment"]["extraction_status"], "extracted")
        self.assertIn("Include booking and contacts", material["content"])
        self.assertEqual((await self.client.get(f"/api/projects/project-main/materials/{material['id']}/file")).content, data)
        self.assertEqual((await self.client.get(f"/api/projects/project-main/materials/{material['id']}/preview")).status_code, 415)

    async def test_docx_extracts_russian_paragraphs_and_table(self):
        result = await self.upload("ТЗ.docx", docx_bytes())
        self.assertEqual(result.status_code, 200, result.text)
        material = result.json()
        self.assertEqual(material["attachment"]["extraction_status"], "extracted")
        for text in ("Техническое задание", "запись онлайн", "владельцы автомобилей"):
            self.assertIn(text, material["content"])

    async def test_unsupported_binary_saved_without_fabricated_extraction(self):
        data = bytes(range(256))
        result = await self.upload("design-source.bin", data)
        self.assertEqual(result.status_code, 200, result.text)
        material = result.json()
        self.assertEqual(material["attachment"]["extraction_status"], "unsupported")
        self.assertRegex(material["attachment"]["extraction_note"], r"[А-Яа-я]")
        self.assertEqual((await self.client.get(f"/api/projects/project-main/materials/{material['id']}/file")).content, data)

    async def test_corrupt_pdf_and_docx_keep_original_with_failed_note(self):
        for filename in ("broken.pdf", "broken.docx"):
            result = await self.upload(filename, b"broken-data")
            self.assertEqual(result.status_code, 200, result.text)
            material = result.json()
            self.assertEqual(material["attachment"]["extraction_status"], "failed")
            self.assertNotIn(self.temp.name, json.dumps(material))
            self.assertEqual((await self.client.get(f"/api/projects/project-main/materials/{material['id']}/file")).content, b"broken-data")

    async def test_empty_original_retained_and_oversize_leaves_no_partial_file(self):
        empty = await self.upload("empty.txt", b"")
        self.assertEqual(empty.status_code, 200, empty.text)
        self.assertEqual(empty.json()["attachment"]["extraction_status"], "empty")
        mid = empty.json()["id"]
        self.assertEqual((await self.client.get(f"/api/projects/project-main/materials/{mid}/file")).content, b"")
        before = self.store.rows("materials", "project-main")
        files = self.files()
        async def oversized():
            for _ in range(51):
                yield b"x" * 1024 * 1024
        large = await self.upload("large.bin", oversized())
        self.assertEqual(large.status_code, 413, large.text)
        self.assertEqual(self.store.rows("materials", "project-main"), before)
        self.assertEqual(self.files(), files)

    async def test_filename_traversal_and_control_bytes_rejected(self):
        for filename in ("../.env", "..\\office.db", "C:\\secret.txt", "x\r\nHeader.txt", "nul\x00.txt", "a" * 256):
            result = await self.upload(filename, b"malicious")
            self.assertTrue(400 <= result.status_code < 500, (filename, result.text))
        self.assertEqual(self.files(), set())

    async def test_upload_exception_is_narrow_and_origin_guard_remains(self):
        for path in ("/api/projects", "/api/projects/project-main/materials", "/api/catalog/import"):
            result = await self.client.post(path, content=b"{}", headers={"content-type": "application/octet-stream"})
            self.assertEqual(result.status_code, 415, result.text)
        for mime in ("multipart/form-data", "text/plain", "application/json"):
            result = await self.client.post("/api/projects/project-main/materials/upload?filename=x.txt", content=b"{}", headers={"content-type": mime})
            self.assertEqual(result.status_code, 415, result.text)
        for origin in ("https://evil.example", "null", "http://localhost.evil.example:4197"):
            self.assertEqual((await self.upload("x.txt", b"text", headers={"origin": origin})).status_code, 403)
        self.assertEqual((await self.upload("x.txt", b"text", headers={"host": "evil.example:4197"})).status_code, 400)
        self.assertEqual(self.files(), set())

    async def test_cross_project_file_and_preview_scope_and_unknown_upload(self):
        material = (await self.upload("image.png", PNG)).json()
        pid = self.store.create_project("Другой проект", "Контекст")["id"]
        for suffix in ("file", "preview"):
            self.assertEqual((await self.client.get(f"/api/projects/{pid}/materials/{material['id']}/{suffix}")).status_code, 404)
            self.assertEqual((await self.client.get(f"/api/projects/project-main/materials/unknown/{suffix}")).status_code, 404)
        self.assertEqual((await self.upload("x.txt", b"text", pid="unknown")).status_code, 404)
        self.assertEqual(len(self.files()), 1)

    async def test_image_preview_and_active_content_download_boundary(self):
        image = (await self.upload("photo.png", PNG)).json()
        preview = await self.client.get(f"/api/projects/project-main/materials/{image['id']}/preview")
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.content, PNG)
        self.assertEqual(preview.headers["content-type"], "image/png")
        self.assertEqual(preview.headers.get("x-content-type-options"), "nosniff")
        for filename, data in (("evil.html", b"<script>alert(1)</script>"), ("evil.svg", b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>'), ("evil.js", b"alert(1)")):
            material = (await self.upload(filename, data)).json()
            self.assertEqual((await self.client.get(f"/api/projects/project-main/materials/{material['id']}/preview")).status_code, 415)
            downloaded = await self.client.get(f"/api/projects/project-main/materials/{material['id']}/file")
            self.assertEqual(downloaded.content, data)
            self.assertIn("attachment", downloaded.headers["content-disposition"])
            self.assertEqual(downloaded.headers.get("x-content-type-options"), "nosniff")

    async def test_concurrent_duplicate_upload_is_idempotent_including_events_and_files(self):
        results = await asyncio.gather(self.upload("brief.txt", b"same brief"), self.upload("brief.txt", b"same brief"))
        self.assertTrue(all(r.status_code == 200 for r in results))
        self.assertEqual(results[0].json()["id"], results[1].json()["id"])
        mid = results[0].json()["id"]
        self.assertEqual(len([e for e in self.store.events("project-main") if e.get("material_id") == mid]), 1)
        self.assertEqual(len(self.files()), 1)

    async def test_same_filename_with_changed_content_and_project_are_distinct(self):
        first = (await self.upload("brief.txt", b"first")).json()
        second = (await self.upload("brief.txt", b"second")).json()
        pid = self.store.create_project("Отдельный", "Контекст")["id"]
        third = (await self.upload("brief.txt", b"first", pid=pid)).json()
        self.assertEqual(len({first["id"], second["id"], third["id"]}), 3)
        self.assertEqual(len(self.files()), 3)

    async def test_link_validation_dedup_and_no_remote_fetch(self):
        url = "https://example.com/client-brief?language=ru#requirements"
        with patch.object(httpx.AsyncClient, "get", side_effect=AssertionError("Link insertion must not fetch a remote page")):
            result = await self.client.post("/api/projects/project-main/materials/link", json={"title": "Референс", "url": url})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["source_url"], url)
        self.assertIn(url, result.json()["content"])
        retry = await self.client.post("/api/projects/project-main/materials/link", json={"title": "Референс", "url": url})
        self.assertEqual(retry.json()["id"], result.json()["id"])
        for invalid in ("javascript:alert(1)", "file:///C:/secret.txt", "ftp://example.com", "https://", "https://user:pass@example.com", "https://example.com/\nInjected", "data:text/html,hello"):
            rejected = await self.client.post("/api/projects/project-main/materials/link", json={"title": "Ссылка", "url": invalid})
            self.assertTrue(400 <= rejected.status_code < 500, (invalid, rejected.text))
        self.assertEqual(self.files(), set())

    async def test_selected_document_text_reaches_stage_input_only_with_permission(self):
        selected = (await self.upload("brief.docx", docx_bytes())).json()
        unselected = (await self.upload("private.txt", b"UNSELECTED-PRIVATE-TEXT")).json()
        engine = self.app.state.engine
        task = engine.create_task("project-main", "Сайт", "Выполнить ТЗ", agents=[FIRST], material_ids=[selected["id"]])
        member = self.store.member("project-main", FIRST)
        payload = engine.build_input(task, task["stages"][0], member)
        self.assertEqual([m["id"] for m in payload["materials"]], [selected["id"]])
        self.assertIn("запись онлайн", payload["materials"][0]["content"])
        self.assertNotIn("UNSELECTED-PRIVATE-TEXT", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn(self.temp.name, json.dumps(payload))
        self.assertNotIn("storage_path", json.dumps(payload))
        captured = []
        class RecordingAdapter:
            async def execute(self, stage_payload, stage):
                captured.append(stage_payload)
                return {"content": "Требования приняты", "usage": None, "cost": None}
        engine.adapter["demo"] = RecordingAdapter()
        engine.start(task["id"], "demo")
        await engine.next(task["id"])
        await engine.next(task["id"])
        self.assertEqual(captured[0]["materials"], payload["materials"])
        persisted = self.store.get("tasks", task["id"])
        self.assertEqual(persisted["stages"][0]["input"]["materials"], payload["materials"])
        self.assertIsNotNone(persisted["stages"][0]["output_id"])
        member["tools"] = [tool for tool in member["tools"] if tool != "project_context"]
        self.assertEqual(engine.build_input(task, task["stages"][0], member)["materials"], [])
        pid = self.store.create_project("Другой", "Контекст")["id"]
        rejected = await self.client.post(f"/api/projects/{pid}/tasks", json={"title": "x", "goal": "x", "agents": [FIRST], "material_ids": [unselected["id"]]})
        self.assertEqual(rejected.status_code, 409)

    async def test_truncation_bounds_provider_text_without_losing_original(self):
        data = b"x" * 120_000
        material = (await self.upload("long.txt", data)).json()
        self.assertEqual(material["attachment"]["extraction_status"], "truncated")
        self.assertLessEqual(len(material["content"]), 100_000)
        self.assertEqual((await self.client.get(f"/api/projects/project-main/materials/{material['id']}/file")).content, data)

    async def test_docx_external_entities_are_not_expanded(self):
        secret = Path(self.temp.name) / "outside-secret.txt"
        secret.write_text("MUST-NOT-READ-SECRET", encoding="utf-8")
        document = f'''<?xml version="1.0"?><!DOCTYPE doc [<!ENTITY steal SYSTEM "{secret.as_uri()}">]><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>&steal;</w:t></w:r></w:p></w:body></w:document>'''
        result = await self.upload("hostile.docx", docx_bytes(document))
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["attachment"]["extraction_status"], "failed")
        self.assertNotIn("MUST-NOT-READ-SECRET", result.text)

    async def test_original_and_metadata_survive_database_reopen(self):
        data = docx_bytes()
        material = (await self.upload("ТЗ.docx", data)).json()
        self.store.close()
        self.store = Store(self.temp.name, ROOT / "catalog")
        self.assertEqual(self.store.get("materials", material["id"]), material)
        app = create_app(self.store)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:4197") as client:
            self.assertEqual((await client.get(f"/api/projects/project-main/materials/{material['id']}/file")).content, data)
        await app.state.engine.shutdown()

    async def test_pdf_decompression_per_page_and_aggregate_limits_keep_original(self):
        for filename, data, statuses in (
            ("aggregate.pdf", compressed_pdf_bytes(), {"truncated"}),
            ("page-limit.pdf", compressed_pdf_bytes(pages=1, page_bytes=6_000_000), {"failed"}),
        ):
            result = await self.upload(filename, data)
            self.assertEqual(result.status_code, 200, result.text)
            material = result.json()
            self.assertIn(material["attachment"]["extraction_status"], statuses)
            self.assertEqual((await self.client.get(f"/api/projects/project-main/materials/{material['id']}/file")).content, data)

    async def test_compressed_docx_exceeding_xml_budget_keeps_original(self):
        data = docx_bytes("<document>" + "a" * 6_000_000 + "</document>")
        result = await self.upload("compressed.docx", data)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["attachment"]["extraction_status"], "failed")

    async def test_database_event_failure_rolls_back_material_and_removes_file(self):
        before = self.store.rows("materials", "project-main")
        events = self.store.events("project-main")
        transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost:4197") as client:
            with patch.object(self.store, "emit", side_effect=RuntimeError("simulated event failure")):
                result = await client.post("/api/projects/project-main/materials/upload?filename=rollback.txt", content=b"safe text", headers={"content-type": "application/octet-stream"})
        self.assertEqual(result.status_code, 500)
        self.assertEqual(self.store.rows("materials", "project-main"), before)
        self.assertEqual(self.store.events("project-main"), events)
        self.assertEqual(self.files(), set())

    async def parser_lifecycle(self, cancel):
        from backend import attachments
        original_popen = subprocess.Popen
        processes = []
        observed_env = []
        started = asyncio.Event()
        def spawn(command, **kwargs):
            if "-I" not in command:
                return original_popen(command, **kwargs)
            observed_env.append(kwargs["env"])
            # Keep inherited stdout open so leaked descendants would block the caller.
            process = original_popen([command[0], "-I", "-c", "import time; time.sleep(20)"], **kwargs)
            processes.append(process)
            started.set()
            return process
        path = Path(self.temp.name) / "probe.txt"
        path.write_text("probe", encoding="utf-8")
        with patch.dict(os.environ, {"OFFICE_MODEL_KEY":"MUST-NOT-INHERIT", "ANTHROPIC_API_KEY":"MUST-NOT-INHERIT"}), patch.object(attachments.subprocess, "Popen", side_effect=spawn), patch.object(attachments, "EXTRACTION_TIMEOUT_SECONDS", .2 if not cancel else 2):
            task = asyncio.create_task(attachments.extract_file(path, path.name, 5, "text/plain"))
            await started.wait()
            began = time.monotonic()
            if cancel:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            else:
                result = await task
                self.assertEqual(result["status"], "failed")
            self.assertLess(time.monotonic() - began, 5, "Parser cancellation/timeout must not wait for the sleeping child")
        self.assertIsNotNone(processes[0].poll())
        self.assertNotIn("MUST-NOT-INHERIT", str(observed_env))

    async def test_real_parser_timeout_reaps_owned_process_without_credentials(self):
        await self.parser_lifecycle(cancel=False)

    async def test_real_parser_cancellation_reaps_owned_process_without_credentials(self):
        await self.parser_lifecycle(cancel=True)
