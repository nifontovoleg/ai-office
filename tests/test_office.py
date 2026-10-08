"""Contract, integration and security tests; no network and no real data changes."""
import asyncio
import copy
import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx

# Importing ASGI main creates its default app. Isolate even that bootstrap DB.
# Other suites may have imported Store before this module, so patch its cached path too.
from backend import store as store_module
_bootstrap = tempfile.TemporaryDirectory(prefix="office-bootstrap-")
with patch.dict(os.environ, {"OFFICE_DATA_DIR": _bootstrap.name}), patch.object(store_module, "DATA_DIR", Path(_bootstrap.name)):
    from backend.main import create_app, app as bootstrap_app
    from backend.runtime import Engine, DemoAdapter, ModelAdapter, DEMO_PLAN, model_config
    from backend.store import Store, ROOT, uid, now
bootstrap_app.state.store.close()
_bootstrap.cleanup()

CATALOG = ROOT / "catalog"
FIRST = "agents-orchestrator"
SECOND = "design-ux-researcher"
DEFAULT_TOOLS = ["project_context", "previous_materials", "material_export"]
MODEL_ENV = {"OFFICE_ENABLE_MODEL": "true", "OFFICE_MODEL_PROTOCOL": "chat_completions", "OFFICE_MODEL_URL": "https://model.example/v1/chat/completions", "OFFICE_MODEL_NAME": "test-model", "OFFICE_MODEL_KEY": "SECRET-DO-NOT-LEAK", "OFFICE_MODEL_TIMEOUT_SECONDS": "120", "OFFICE_MODEL_MAX_TOKENS": "8192"}
from backend.localization import ROLE_NAMES_RU, ROLE_DESCRIPTIONS_RU, localized_profile


class ImmediateAdapter:
    async def execute(self, payload, stage):
        return {"content": stage.get("demo_content") or "Готово", "usage": None, "cost": None}


class GateAdapter:
    def __init__(self, error=None):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.error = error

    async def execute(self, payload, stage):
        self.started.set()
        await self.release.wait()
        if self.error:
            raise self.error
        return {"content": "Результат вызова", "usage": None, "cost": None}


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="office-test-")
        self.store = Store(self.temp.name, CATALOG)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_catalog_has_282_original_profiles_18_categories_and_matching_hashes(self):
        data = json.loads((CATALOG / "agents.json").read_text(encoding="utf-8"))
        self.assertEqual(len(self.store.rows("profiles")), 282)
        self.assertEqual(len(self.store.rows("categories")), 18)
        for source in data["agents"]:
            saved = self.store.get("profiles", source["id"])
            self.assertEqual(saved, source)
            raw = (CATALOG / source["profile_path"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), source["source_sha256"])
            # Source includes YAML metadata; catalog instructions contain its unchanged body.
            source_text = raw.decode("utf-8")
            if source_text.startswith("---\n"):
                source_text = source_text.split("\n---\n", 1)[1].lstrip("\n")
            self.assertEqual(source_text, saved["instructions_md"])

    def test_russian_display_layer_covers_all_282_roles_without_changing_sources(self):
        profiles = self.store.rows("profiles")
        ids = {profile["id"] for profile in profiles}
        self.assertEqual(set(ROLE_NAMES_RU), ids)
        self.assertEqual(set(ROLE_DESCRIPTIONS_RU), ids)
        for profile in profiles:
            before = copy.deepcopy(profile)
            localized = localized_profile(profile)
            self.assertEqual(profile, before)
            self.assertEqual({key: localized[key] for key in before}, before)
            self.assertRegex(localized["display_name_ru"], r"[А-Яа-яЁё]")
            self.assertLessEqual(len(localized["display_name_ru"]), 100)
            self.assertRegex(localized["description_ru"], r"[А-Яа-яЁё]")
            self.assertGreater(len(localized["description_ru"]), 25)
        self.assertEqual(ROLE_NAMES_RU["engineering-frontend-developer"], "Разработчик клиентской части")
        self.assertEqual(ROLE_NAMES_RU["engineering-backend-architect"], "Архитектор серверной части")
        unknown = {"id": "custom-role", "name": "Custom source role", "description": "Custom description", "instructions_md": "Original custom instructions"}
        self.assertEqual(localized_profile(unknown)["display_name_ru"], unknown["name"])
        self.assertEqual(localized_profile(unknown)["description_ru"], unknown["description"])

    def test_all_new_members_have_russian_defaults_and_custom_names_survive_updates(self):
        self.store.add_all_profiles("project-main")
        for member in self.store.members("project-main"):
            self.assertEqual(member["display_name_ru"], ROLE_NAMES_RU[member["profile_id"]])
        self.store.save_member("project-main", SECOND, {"display_name_ru": "Research Lead", "autonomy": "confirm", "tools": ["material_export"]})
        self.store.save_member("project-main", SECOND, {"manager_id": "project-management-project-shepherd"})
        custom = self.store.member("project-main", SECOND)
        self.assertEqual(custom["display_name_ru"], "Research Lead")
        self.assertEqual(custom["autonomy"], "confirm")
        self.assertEqual(custom["tools"], ["material_export"])
        self.assertEqual(self.store.localize_default_member_names(), 0)
        self.store.add_all_profiles("project-main")
        self.assertEqual(self.store.member("project-main", SECOND), custom)

    def test_legacy_names_migrate_once_on_restart_preserving_custom_settings_and_events(self):
        frontend = "engineering-frontend-developer"
        backend = "engineering-backend-architect"
        for profile_id, label in [(frontend, "Frontend-разработчик"), (backend, self.store.get("profiles", backend)["name"])]:
            member = self.store.member("project-main", profile_id)
            member.update(display_name_ru=label, autonomy="confirm", tools=["material_export"])
            self.store.db.execute("UPDATE members SET body=? WHERE project_id=? AND profile_id=?", (json.dumps(member, ensure_ascii=False), "project-main", profile_id))
        self.store.db.commit()
        self.store.save_member("project-main", SECOND, {"display_name_ru": "My research team", "autonomy": "schedule", "tools": ["previous_materials", "material_export"]})
        custom = self.store.member("project-main", SECOND)
        events = self.store.events("project-main")
        sources = self.store.rows("profiles")
        self.store.close()
        self.store = Store(self.temp.name, CATALOG)
        for profile_id in (frontend, backend):
            member = self.store.member("project-main", profile_id)
            self.assertEqual(member["display_name_ru"], ROLE_NAMES_RU[profile_id])
            self.assertEqual(member["autonomy"], "confirm")
            self.assertEqual(member["tools"], ["material_export"])
            self.assertEqual(member["manager_id"], FIRST)
        self.assertEqual(self.store.member("project-main", SECOND), custom)
        self.assertEqual(self.store.localize_default_member_names(), 0)
        self.assertEqual(self.store.events("project-main"), events)
        self.assertEqual(self.store.rows("profiles"), sources)

    def test_catalog_reimport_preserves_members_and_updates_profile_atomically(self):
        self.store.save_member("project-main", SECOND, {"autonomy": "confirm", "display_name_ru": "Мой исследователь", "tools": ["material_export"]})
        before = self.store.member("project-main", SECOND)
        data = json.loads((CATALOG / "agents.json").read_text(encoding="utf-8"))
        data["agents"][0]["vibe"] = "Обновлённое необязательное поле"
        self.assertEqual(self.store.import_catalog(data)["imported"], 282)
        self.assertEqual(self.store.member("project-main", SECOND), before)
        self.assertEqual(self.store.get("profiles", data["agents"][0]["id"])["vibe"], data["agents"][0]["vibe"])
        snapshot = self.store.rows("profiles")
        data["agents"].append(copy.deepcopy(data["agents"][0]))
        data["agent_count"] += 1
        with self.assertRaisesRegex(ValueError, "Повторяющийся"):
            self.store.import_catalog(data)
        self.assertEqual(self.store.rows("profiles"), snapshot)

    def test_catalog_rejects_bad_schema_count_required_fields_and_categories(self):
        data = json.loads((CATALOG / "agents.json").read_text(encoding="utf-8"))
        for mutate in [lambda d: d.update(schema_version=2), lambda d: d.update(agent_count=0), lambda d: d["agents"][0].update(name=""), lambda d: d["agents"][0].update(category="unknown"), lambda d: d["categories"].append(d["categories"][0])]:
            with self.subTest(mutate=mutate):
                invalid = copy.deepcopy(data)
                mutate(invalid)
                with self.assertRaises(ValueError):
                    self.store.import_catalog(invalid)
        self.assertEqual(len(self.store.rows("profiles")), 282)

    def test_starter_team_and_project_membership_are_independent(self):
        self.assertEqual(len(self.store.members("project-main")), 8)
        project = self.store.create_project("Второй", "Другой контекст")
        self.store.save_member(project["id"], SECOND, {"display_name_ru": "Вторая роль"})
        self.assertNotEqual(self.store.member("project-main", SECOND)["display_name_ru"], self.store.member(project["id"], SECOND)["display_name_ru"])
        self.store.remove_member(project["id"], SECOND)
        self.assertEqual(len(self.store.members(project["id"])), 7)
        self.assertEqual(len(self.store.members("project-main")), 8)
        self.assertEqual(self.store.get("profiles", SECOND)["id"], SECOND)

    def test_hierarchy_rejects_cycles_unknown_managers_and_clears_removed_links(self):
        with self.assertRaisesRegex(ValueError, "собой"):
            self.store.save_member("project-main", SECOND, {"manager_id": SECOND})
        with self.assertRaisesRegex(ValueError, "участником"):
            self.store.save_member("project-main", SECOND, {"manager_id": "nobody"})
        with self.assertRaisesRegex(ValueError, "цикл"):
            self.store.save_member("project-main", FIRST, {"manager_id": SECOND})
        self.store.remove_member("project-main", FIRST)
        self.assertTrue(all(m["manager_id"] is None for m in self.store.members("project-main")))

    def test_events_have_unique_identifiers_ordered_replay_and_project_isolation(self):
        other = self.store.create_project("Другой")
        for i in range(175):
            self.store.emit("project-main", "test", str(i), task_id="task-example", agent_id=FIRST)
        self.store.emit(other["id"], "private", "Другой проект")
        first = self.store.events("project-main", replay=True)
        self.assertEqual(len(first), 150)
        self.assertEqual(first[0]["action"], "project_created")
        following = self.store.events("project-main", first[-1]["seq"], replay=True)
        all_events = first + following
        self.assertEqual(len(all_events), 176)
        self.assertEqual(len({e["id"] for e in all_events}), len(all_events))
        self.assertEqual([e["seq"] for e in all_events], sorted(e["seq"] for e in all_events))
        self.assertTrue(all(e["project_id"] == "project-main" and "time" in e for e in all_events))
        self.assertEqual(self.store.events("project-main", all_events[-1]["seq"]), [])

    def test_settings_members_materials_events_survive_store_restart(self):
        self.store.set_setting("preferences:project-main", {"motion": False})
        self.store.save_member("project-main", SECOND, {"autonomy": "confirm"})
        events = self.store.events("project-main")
        self.store.close()
        self.store = Store(self.temp.name, CATALOG)
        self.assertEqual(self.store.setting("preferences:project-main"), {"motion": False})
        self.assertEqual(self.store.member("project-main", SECOND)["autonomy"], "confirm")
        self.assertEqual(self.store.events("project-main"), events)
        self.assertEqual(len(self.store.rows("materials", "project-main")), 1)

    def test_import_all_adds_282_unique_members_and_preserves_original_profiles_configs(self):
        self.store.save_member("project-main", SECOND, {"autonomy": "confirm", "tools": ["material_export"], "display_name_ru": "Мой UX", "manager_id": "project-management-project-shepherd"})
        original_members = {member["profile_id"]: member for member in self.store.members("project-main")}
        original_profiles = self.store.rows("profiles")
        result = self.store.add_all_profiles("project-main")
        self.assertEqual(result, {"added": 274, "total": 282, "categories": 18})
        members = self.store.members("project-main")
        self.assertEqual(len(members), 282)
        self.assertEqual({member["profile_id"] for member in members}, {profile["id"] for profile in original_profiles})
        self.assertEqual(len({member["profile_id"] for member in members}), len(members))
        for member in members:
            if member["profile_id"] in original_members:
                self.assertEqual(member, original_members[member["profile_id"]])
            else:
                self.assertEqual(member["autonomy"], "task")
                self.assertEqual(member["tools"], DEFAULT_TOOLS)
                self.assertEqual(member["manager_id"], FIRST)
        self.assertEqual(self.store.rows("profiles"), original_profiles)
        self.assertEqual(len([event for event in self.store.events("project-main") if event["action"] == "team_imported"]), 1)
        self.assertFalse(any(event["action"] in ("stage_started", "tool_used") for event in self.store.events("project-main")))
        self.assertEqual(self.store.rows("tasks"), [])

    def test_import_all_is_idempotent_project_isolated_and_restores_valid_coordinator(self):
        project = self.store.create_project("Новый проект")
        self.store.remove_member("project-main", FIRST)
        result = self.store.add_all_profiles("project-main")
        self.assertEqual(result["total"], 282)
        self.assertIsNone(self.store.member("project-main", FIRST)["manager_id"])
        self.assertEqual(len(self.store.members(project["id"])), 8)
        self.store.save_member("project-main", SECOND, {"autonomy": "schedule"})
        members = self.store.members("project-main")
        events = self.store.events("project-main")
        repeated = self.store.add_all_profiles("project-main")
        self.assertEqual(repeated, {"added": 0, "total": 282, "categories": 18})
        self.assertEqual(self.store.members("project-main"), members)
        self.assertEqual(self.store.events("project-main"), events)
        self.assertEqual(len(self.store.members(project["id"])), 8)

    def test_import_all_rolls_back_members_and_event_on_partial_failure(self):
        before = self.store.members("project-main")
        events = self.store.events("project-main")
        save = self.store._save_member
        calls = []
        def fail_second(project_id, profile_id, config, commit=True):
            calls.append(profile_id)
            if len(calls) == 2:
                raise ValueError("Тестовая ошибка массового добавления")
            return save(project_id, profile_id, config, commit=commit)
        with patch.object(self.store, "_save_member", fail_second):
            with self.assertRaises(ValueError):
                self.store.add_all_profiles("project-main")
        self.assertEqual(self.store.members("project-main"), before)
        self.assertEqual(self.store.events("project-main"), events)

    def test_fresh_production_app_has_full_primary_team_and_restart_preserves_edits(self):
        fresh_directory = Path(self.temp.name) / "production-data"
        with patch("backend.main.DATA_DIR", fresh_directory), patch("backend.store.DATA_DIR", fresh_directory):
            production = create_app()
            database = production.state.store
            try:
                self.assertEqual(len(database.members("project-main")), 282)
                task = database.rows("tasks", "project-main")[0]
                self.assertEqual(len({stage["agent_id"] for stage in task["stages"]}), 8)
                self.assertEqual(task["status"], "pending")
                self.assertEqual(database.get("profiles", SECOND), self.store.get("profiles", SECOND))
                project = database.create_project("Обычный новый проект")
                self.assertEqual(len(database.members(project["id"])), 8)
                database.save_member("project-main", SECOND, {"autonomy": "confirm", "display_name_ru": "Моя настройка"})
                removed = next(member["profile_id"] for member in database.members("project-main") if member["profile_id"] not in {stage["agent_id"] for stage in task["stages"]})
                database.remove_member("project-main", removed)
            finally:
                database.close()
            restarted = create_app()
            try:
                self.assertEqual(len(restarted.state.store.members("project-main")), 281)
                self.assertFalse(any(member["profile_id"] == removed for member in restarted.state.store.members("project-main")))
                self.assertEqual(restarted.state.store.member("project-main", SECOND)["autonomy"], "confirm")
                self.assertEqual(restarted.state.store.member("project-main", SECOND)["display_name_ru"], "Моя настройка")
                self.assertEqual(len(restarted.state.store.members(project["id"])), 8)
                self.assertEqual(len([event for event in restarted.state.store.events("project-main") if event["action"] == "team_imported"]), 1)
            finally:
                restarted.state.store.close()

    def test_create_app_with_explicit_store_preserves_eight_member_starter(self):
        application = create_app(self.store)
        self.assertIs(application.state.store, self.store)
        self.assertEqual(len(self.store.members("project-main")), 8)
        self.assertFalse(any(event["action"] == "team_imported" for event in self.store.events("project-main")))


class RuntimeCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="office-runtime-")
        self.store = Store(self.temp.name, CATALOG)
        self.engine = Engine(self.store)
        self.engine.adapter["demo"] = ImmediateAdapter()
        self.engine.step_delay = .001
        self.engine.schedule_interval = .001

    async def asyncTearDown(self):
        await self.engine.shutdown()
        self.store.close()
        self.temp.cleanup()

    def make_task(self, agents=None, **kwargs):
        return self.engine.create_task("project-main", "Проверяемая задача", "Проверяемая цель", agents=agents or [FIRST, SECOND], **kwargs)

    async def test_default_task_stages_use_russian_member_labels_and_explicit_names_survive(self):
        task = self.make_task(agents=["engineering-frontend-developer", "engineering-backend-architect"])
        self.assertEqual([stage["name"] for stage in task["stages"]], ["Этап 1: Разработчик клиентской части", "Этап 2: Архитектор серверной части"])
        self.store.save_member("project-main", SECOND, {"display_name_ru": "Мой исследователь"})
        custom = self.make_task(agents=[SECOND])
        self.assertEqual(custom["stages"][0]["name"], "Этап 1: Мой исследователь")
        explicit = self.make_task(agents=[SECOND], stage_names=["Проверить особенный сценарий"])
        self.assertEqual(explicit["stages"][0]["name"], "Проверить особенный сценарий")

    async def finish(self, task):
        for _ in range(30):
            task = self.store.get("tasks", task["id"])
            if task["status"] != "running":
                return task
            await self.engine.next(task["id"])
        self.fail("Задача не завершила этапы")

    async def test_manual_full_demo_revision_handoffs_outputs_and_owner_approval(self):
        self.engine.ensure_demo("project-main")
        task = self.store.rows("tasks")[0]
        self.engine.start(task["id"])
        final = await self.finish(task)
        self.assertEqual(final["cursor"], len(DEMO_PLAN))
        self.assertEqual(final["status"], "awaiting_approval")
        self.assertEqual(final["approval"]["kind"], "final")
        materials = self.store.rows("materials", "project-main")
        self.assertEqual(len([m for m in materials if m["kind"] == "result"]), 10)
        self.assertTrue(all(m["example"] for m in materials if m["kind"] == "result"))
        for i, stage in enumerate(final["stages"]):
            self.assertIsNotNone(stage["started_at"])
            self.assertIsNotNone(stage["finished_at"])
            self.assertEqual(stage["status"], "completed")
            self.assertEqual(stage["input"]["instructions_md"], self.store.get("profiles", stage["agent_id"])["instructions_md"])
            if i:
                previous_id = final["stages"][i - 1]["output_id"]
                self.assertEqual(stage["input"]["materials"][-1]["id"], previous_id)
                self.assertEqual(stage["input"]["materials"][-1]["content"], self.store.get("materials", previous_id)["content"])
        events = self.store.events("project-main")
        handoffs = [e for e in events if e["action"] == "handoff"]
        self.assertEqual(len(handoffs), 9)
        self.assertTrue(any(e["action"] == "revision" and "label" in e["text"] for e in events))
        self.assertEqual([(e["agent_id"], e["target_agent_id"], e["material_id"]) for e in handoffs], [(a["agent_id"], b["agent_id"], a["output_id"]) for a, b in zip(final["stages"], final["stages"][1:])])
        completed = await self.engine.action(task["id"], "approve")
        self.assertEqual(completed["status"], "completed")
        self.assertTrue(all(s["usage"] is None and s["cost"] is None for s in completed["stages"]))

    async def test_auto_runs_to_final_approval_without_auto_approving(self):
        task = self.make_task()
        self.engine.start(task["id"], auto=True)
        runner = self.engine.runners[task["id"]]
        await asyncio.wait_for(runner, 2)
        task = self.store.get("tasks", task["id"])
        self.assertEqual(task["status"], "awaiting_approval")
        self.assertFalse(task["auto"])

    async def test_confirm_autonomy_requires_explicit_approval_for_each_stage(self):
        self.store.save_member("project-main", FIRST, {"autonomy": "confirm"})
        task = self.make_task([FIRST, FIRST])
        self.engine.start(task["id"])
        task = await self.engine.next(task["id"])
        self.assertEqual(task["approval"]["kind"], "stage")
        with self.assertRaises(ValueError):
            await self.engine.next(task["id"])
        await self.engine.action(task["id"], "approve")
        await self.engine.next(task["id"])
        await self.engine.next(task["id"])
        task = await self.engine.next(task["id"])
        self.assertEqual(task["approval"]["kind"], "stage")
        self.assertEqual(task["cursor"], 1)

    async def test_schedule_autonomy_datetime_validation_and_due_launch(self):
        self.store.save_member("project-main", FIRST, {"autonomy": "schedule"})
        for invalid in ["broken", "2026-10-07T10:00:00"]:
            with self.assertRaises(ValueError):
                self.make_task([FIRST], scheduled_at=invalid)
        task = self.make_task([FIRST])
        self.engine.start(task["id"])
        with self.assertRaisesRegex(ValueError, "расписанию"):
            await self.engine.next(task["id"])
        await self.engine.action(task["id"], "cancel")
        task = self.make_task([FIRST], scheduled_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
        loop = asyncio.create_task(self.engine.schedule_loop())
        try:
            for _ in range(100):
                await asyncio.sleep(.002)
                if self.store.get("tasks", task["id"])["status"] == "awaiting_approval":
                    break
            self.assertEqual(self.store.get("tasks", task["id"])["status"], "awaiting_approval")
            self.assertTrue(self.store.get("tasks", task["id"])["schedule_started"])
        finally:
            loop.cancel()
            await asyncio.gather(loop, return_exceptions=True)

    async def test_cancel_retains_completed_materials_and_prevents_next_stage(self):
        task = self.make_task()
        self.engine.start(task["id"])
        await self.engine.next(task["id"])
        task = await self.engine.next(task["id"])
        material_id = task["stages"][0]["output_id"]
        await self.engine.action(task["id"], "cancel")
        with self.assertRaises(ValueError):
            await self.engine.next(task["id"])
        self.assertEqual(self.store.get("materials", material_id)["content"], "Готово")
        self.assertEqual(self.store.get("tasks", task["id"])["stages"][1]["status"], "pending")

    async def test_inflight_cancel_preserves_output_and_reset_is_blocked(self):
        gate = GateAdapter()
        self.engine.adapter["demo"] = gate
        task = self.make_task()
        self.engine.start(task["id"])
        await self.engine.next(task["id"])
        future = asyncio.create_task(self.engine.next(task["id"]))
        await gate.started.wait()
        with self.assertRaisesRegex(ValueError, "сбросом"):
            await self.engine.action(task["id"], "reset")
        with self.assertRaisesRegex(ValueError, "выполняется"):
            self.engine.start(task["id"], auto=True)
        with self.assertRaisesRegex(ValueError, "выполняется"):
            await self.engine.next(task["id"])
        await self.engine.action(task["id"], "cancel")
        gate.release.set()
        result = await future
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["cursor"], 1)
        self.assertEqual(self.store.get("materials", result["stages"][0]["output_id"])["content"], "Результат вызова")
        self.assertFalse(any(e["action"] == "handoff" for e in self.store.events("project-main")))

    async def test_permissions_rechecked_before_call_and_after_inflight_revocation(self):
        task = self.make_task([FIRST])
        self.engine.start(task["id"])
        await self.engine.next(task["id"])
        self.store.save_member("project-main", FIRST, {"tools": ["project_context"]})
        result = await self.engine.next(task["id"])
        self.assertEqual(result["status"], "error")
        self.assertIsNone(result["stages"][0]["output_id"])
        self.store.save_member("project-main", FIRST, {"tools": DEFAULT_TOOLS})
        self.engine.start(task["id"])
        await self.engine.next(task["id"])
        gate = GateAdapter()
        self.engine.adapter["demo"] = gate
        future = asyncio.create_task(self.engine.next(task["id"]))
        await gate.started.wait()
        self.store.save_member("project-main", FIRST, {"tools": ["project_context"]})
        gate.release.set()
        result = await future
        self.assertEqual(result["status"], "error")
        self.assertIsNone(result["stages"][0]["output_id"])
        self.assertIn("отозвано", result["stages"][0]["error"])

    async def test_missing_previous_permission_stops_handoff_reader(self):
        task = self.make_task()
        self.store.save_member("project-main", SECOND, {"tools": ["material_export"]})
        self.engine.start(task["id"])
        await self.engine.next(task["id"])
        await self.engine.next(task["id"])
        with self.assertRaisesRegex(ValueError, "предыдущего"):
            await self.engine.next(task["id"])

    async def test_reject_final_adds_revision_then_reset_keeps_history_and_materials(self):
        task = self.make_task([FIRST])
        self.engine.start(task["id"])
        await self.finish(task)
        revised = await self.engine.action(task["id"], "reject", comment="Добавить контакты")
        self.assertEqual(len(revised["stages"]), 2)
        self.assertIn("Добавить контакты", revised["goal"])
        await self.finish(revised)
        completed = await self.engine.action(task["id"], "approve")
        output_ids = [s["output_id"] for s in completed["stages"]]
        reset = await self.engine.action(task["id"], "reset")
        self.assertNotEqual(reset["run_id"], completed["run_id"])
        self.assertEqual(reset["history"][0]["stages"], completed["stages"])
        self.assertEqual(reset["status"], "pending")
        self.assertEqual(reset["goal"], task["goal"])
        self.assertEqual(len(reset["stages"]), 1)
        self.assertNotIn("finished_at", reset)
        self.assertTrue(all(s["output_id"] is None for s in reset["stages"]))
        self.assertTrue(all(self.store.get("materials", mid) for mid in output_ids))

    async def test_active_member_removal_blocked_and_no_terminal_state_mutation(self):
        task = self.make_task()
        self.engine.start(task["id"])
        with self.assertRaises(ValueError):
            self.store.remove_member("project-main", SECOND)
        await self.engine.action(task["id"], "cancel")
        with self.assertRaises(ValueError):
            await self.engine.action(task["id"], "pause")
        self.store.remove_member("project-main", SECOND)
        await self.engine.action(task["id"], "reset")
        with self.assertRaises(ValueError):
            self.engine.start(task["id"])

    async def test_cross_project_material_and_foreign_team_member_rejected(self):
        project = self.store.create_project("Другой", "SECRET-CONTEXT-OTHER-PROJECT")
        foreign = self.store.rows("materials", project["id"])[0]
        with self.assertRaisesRegex(ValueError, "другому"):
            self.make_task(material_ids=[foreign["id"]])
        with self.assertRaisesRegex(ValueError, "команде"):
            self.make_task(["design-brand-guardian"])

    async def test_stage_names_validation_and_exact_order(self):
        task = self.make_task(stage_names=["Мой бриф", "Моя проверка"])
        self.assertEqual([s["name"] for s in task["stages"]], ["Мой бриф", "Моя проверка"])
        for bad in [["Один"], [" ", "Два"], ["x" * 181, "Два"]]:
            with self.assertRaises(ValueError):
                self.make_task(stage_names=bad)

    async def test_restart_interrupts_stage_and_disables_auto_without_provider_call(self):
        task = self.make_task()
        self.engine.start(task["id"])
        await self.engine.next(task["id"])
        current = self.store.get("tasks", task["id"])
        current["auto"] = True
        self.store.save("tasks", current)
        restarted = create_app(self.store)
        recovered = self.store.get("tasks", task["id"])
        self.assertEqual(recovered["status"], "error")
        self.assertFalse(recovered["auto"])
        self.assertEqual(recovered["stages"][0]["status"], "error")
        self.assertIsNone(recovered["stages"][0]["output_id"])
        self.assertEqual(restarted.state.engine.runners, {})
        self.engine.start(task["id"])
        self.assertEqual(self.store.get("tasks", task["id"])["stages"][0]["status"], "pending")

    async def test_real_mode_never_falls_back_to_demo(self):
        task = self.make_task([FIRST])
        with patch.dict(os.environ, {"OFFICE_ENABLE_MODEL": "false"}):
            with self.assertRaisesRegex(ValueError, "вместо"):
                self.engine.start(task["id"], "model")
        self.assertEqual(self.store.get("tasks", task["id"])["status"], "pending")
        self.assertEqual(len(self.store.rows("materials")), 1)

    async def test_actual_demo_adapter_marks_example_without_invented_usage(self):
        payload = {"task": {"goal": "Проверить пример"}}
        result = await DemoAdapter().execute(payload, {"name": "Проверка"})
        self.assertIn("Демонстрационный пример", result["content"])
        self.assertIsNone(result["usage"])
        self.assertIsNone(result["cost"])

    async def test_stage_result_and_events_roll_back_atomically_on_commit_failure(self):
        task = self.make_task()
        self.engine.start(task["id"])
        await self.engine.next(task["id"])
        emit = self.store.emit
        def failing_emit(project_id, action, text, *args, **kwargs):
            if action == "handoff":
                raise ValueError("Тестовая ошибка сохранения события")
            return emit(project_id, action, text, *args, **kwargs)
        with patch.object(self.store, "emit", failing_emit):
            result = await self.engine.next(task["id"])
        self.assertEqual(result["status"], "error")
        self.assertIsNone(result["stages"][0]["output_id"])
        self.assertEqual(len(self.store.rows("materials")), 1)
        self.assertFalse(any(e["action"] == "material_created" for e in self.store.events("project-main")))

    async def test_auto_waits_for_concurrent_manual_step_instead_of_corrupting_run(self):
        task = self.make_task([FIRST])
        self.engine.start(task["id"])
        await self.engine.next(task["id"])
        gate = GateAdapter()
        self.engine.adapter["demo"] = gate
        future = asyncio.create_task(self.engine.next(task["id"]))
        await gate.started.wait()
        current = self.store.get("tasks", task["id"])
        current["auto"] = True
        self.store.save("tasks", current)
        self.engine.run_auto(task["id"])
        runner = self.engine.runners[task["id"]]
        await asyncio.sleep(.01)
        self.assertEqual(self.store.get("tasks", task["id"])["status"], "running")
        gate.release.set()
        await future
        await asyncio.wait_for(runner, 1)
        self.assertEqual(self.store.get("tasks", task["id"])["status"], "awaiting_approval")

    async def test_mock_model_payload_selected_role_context_isolation_usage_and_no_secrets(self):
        source = self.store.rows("materials", "project-main")[0]
        self.store.create_project("Другой", "SECRET-OTHER-PROJECT")
        self.store.save_member("project-main", FIRST, {"tools": DEFAULT_TOOLS + ["browser"]})
        task = self.make_task([FIRST], material_ids=[source["id"]])
        sent = []
        def responder(request):
            sent.append(json.loads(request.content))
            self.assertEqual(request.headers["authorization"], "Bearer SECRET-DO-NOT-LEAK")
            return httpx.Response(200, json={"choices": [{"message": {"content": "Ответ реального протокола"}}], "usage": {"prompt_tokens": 25, "completion_tokens": 10, "total_tokens": 35, "bad": "SECRET-DO-NOT-LEAK"}})
        self.engine.adapter["model"] = ModelAdapter(httpx.MockTransport(responder))
        with patch.dict(os.environ, MODEL_ENV):
            self.engine.start(task["id"], "model")
            finished = await self.finish(task)
        body = sent[0]
        self.assertEqual(body["model"], "test-model")
        self.assertEqual(body["messages"][1]["content"], self.store.get("profiles", FIRST)["instructions_md"])
        self.assertEqual(len(body["messages"]), 3)
        user_payload = json.loads(body["messages"][2]["content"])
        self.assertEqual(user_payload["materials"][0]["id"], source["id"])
        self.assertNotIn("browser", user_payload["allowed_tools"])
        serialized = json.dumps(body)
        self.assertNotIn("SECRET-OTHER-PROJECT", serialized)
        self.assertNotIn("SECRET-DO-NOT-LEAK", serialized)
        self.assertEqual(finished["stages"][0]["usage"], {"prompt_tokens": 25, "completion_tokens": 10, "total_tokens": 35})
        output = self.store.get("materials", finished["stages"][0]["output_id"])
        self.assertFalse(output["example"])
        self.assertEqual(output["content"], "Ответ реального протокола")

    async def test_codex_stage_persists_output_and_hands_it_to_next_role(self):
        task = self.make_task([FIRST, SECOND])
        payloads = []
        async def runner(command, directory, env, timeout, prompt=None):
            self.assertNotIn("SECRET-DO-NOT-LEAK", str(env))
            if command[1:3] == ["login", "status"]:
                return 0, b"Logged in using ChatGPT", b""
            payloads.append(json.loads(prompt))
            text = "Codex stage " + str(len(payloads))
            events = [{"type": "item.completed", "item": {"type": "agent_message", "text": text}}, {"type": "turn.completed", "usage": {"input_tokens": 15, "cached_input_tokens": 10, "output_tokens": 5}}]
            return 0, ("\n".join(json.dumps(event) for event in events)).encode(), b""
        self.engine.adapter["model"] = ModelAdapter()
        with patch.dict(os.environ, {**MODEL_ENV, "OFFICE_MODEL_PROTOCOL": "codex_cli", "OFFICE_CODEX_TIMEOUT_SECONDS": "300"}), patch("backend.runtime.find_codex", return_value="codex"), patch("backend.codex.find_cli", return_value="codex"), patch("backend.codex.run_cli", side_effect=runner):
            self.engine.start(task["id"], "model")
            finished = await self.finish(task)
        self.assertEqual(len(payloads), 2)
        self.assertEqual(payloads[0]["instructions_md"], self.store.get("profiles", FIRST)["instructions_md"])
        self.assertEqual(payloads[1]["instructions_md"], self.store.get("profiles", SECOND)["instructions_md"])
        self.assertIn("Codex stage 1", json.dumps(payloads[1]["materials"]))
        for stage in finished["stages"]:
            output = self.store.get("materials", stage["output_id"])
            self.assertFalse(output["example"])
            self.assertEqual(stage["usage"]["total_tokens"], 20)
        self.assertNotIn("SECRET-DO-NOT-LEAK", json.dumps(self.store.events("project-main")))

    async def test_claude_native_stage_persists_text_usage_and_handoff(self):
        task = self.make_task([FIRST])
        def responder(request):
            self.assertEqual(request.headers["x-api-key"], "SECRET-DO-NOT-LEAK")
            self.assertNotIn("SECRET-DO-NOT-LEAK", request.content.decode())
            return httpx.Response(200, json={"content": [{"type": "text", "text": "Результат Claude"}], "usage": {"input_tokens": 12, "output_tokens": 8}, "stop_reason": "end_turn"})
        self.engine.adapter["model"] = ModelAdapter(httpx.MockTransport(responder))
        with patch.dict(os.environ, {**MODEL_ENV, "OFFICE_MODEL_PROTOCOL": "anthropic_messages", "OFFICE_MODEL_URL": "https://api.anthropic.com/v1/messages", "OFFICE_MODEL_NAME": "claude-sonnet-5-5"}):
            self.engine.start(task["id"], "model")
            finished = await self.finish(task)
        stage = finished["stages"][0]
        self.assertEqual(stage["usage"]["total_tokens"], 20)
        output = self.store.get("materials", stage["output_id"])
        self.assertFalse(output["example"])
        self.assertEqual(output["content"], "Результат Claude")
        self.assertNotIn("SECRET-DO-NOT-LEAK", json.dumps(self.store.events("project-main")))

    async def test_model_errors_redirect_bad_json_and_network_are_safe(self):
        cases = [httpx.Response(401, text="SECRET-DO-NOT-LEAK"), httpx.Response(302, headers={"location": "https://other.example/SECRET-DO-NOT-LEAK"}), httpx.Response(200, text="SECRET-DO-NOT-LEAK"), httpx.Response(200, json={"choices": []}), httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})]
        task = self.make_task([FIRST])
        for response in cases:
            with self.subTest(status=response.status_code, body=response.text):
                self.engine.adapter["model"] = ModelAdapter(httpx.MockTransport(lambda request: response))
                with patch.dict(os.environ, MODEL_ENV):
                    self.engine.start(task["id"], "model")
                    result = await self.finish(task)
                self.assertEqual(result["status"], "error")
                self.assertNotIn("SECRET-DO-NOT-LEAK", json.dumps(result))
                self.assertIsNone(result["stages"][0]["output_id"])
        def failed(request):
            raise httpx.ConnectError("SECRET-DO-NOT-LEAK", request=request)
        self.engine.adapter["model"] = ModelAdapter(httpx.MockTransport(failed))
        with patch.dict(os.environ, MODEL_ENV):
            self.engine.start(task["id"], "model")
            result = await self.finish(task)
        self.assertEqual(result["status"], "error")
        self.assertNotIn("SECRET-DO-NOT-LEAK", json.dumps(self.store.events("project-main")))

    async def test_model_requires_secure_url_and_context_permission(self):
        task = self.make_task([FIRST])
        self.store.save_member("project-main", FIRST, {"tools": ["material_export"]})
        payload = self.engine.build_input(task, task["stages"][0], self.store.member("project-main", FIRST))
        self.assertIsNone(payload["project"]["context"])
        self.assertEqual(payload["materials"], [])
        for url in ["http://remote.example/v1", "https://user:SECRET-DO-NOT-LEAK@model.example/v1", "file:///secret", "https://model.example/v1#secret"]:
            with patch.dict(os.environ, {**MODEL_ENV, "OFFICE_MODEL_URL": url}):
                with self.assertRaises(ValueError) as error:
                    await ModelAdapter(httpx.MockTransport(lambda request: self.fail("Network must not be called"))).execute(payload, task["stages"][0])
                self.assertNotIn("SECRET-DO-NOT-LEAK", str(error.exception))


class ApiCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="office-api-")
        self.store = Store(self.temp.name, CATALOG)
        self.app = create_app(self.store)
        self.app.state.engine.adapter["demo"] = ImmediateAdapter()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://localhost:4197")

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.app.state.engine.shutdown()
        self.store.close()
        self.temp.cleanup()

    async def test_health_catalog_state_and_profile_contract(self):
        health = (await self.client.get("/api/health")).json()
        self.assertEqual(health["executor"], "demo")
        catalog = (await self.client.get("/api/catalog")).json()
        self.assertEqual(catalog["agent_count"], 282)
        self.assertEqual(len(catalog["categories"]), 18)
        self.assertTrue(all("instructions_md" not in p for p in catalog["agents"]))
        profile = (await self.client.get("/api/profiles/" + FIRST)).json()
        self.assertEqual(profile["instructions_md"], self.store.get("profiles", FIRST)["instructions_md"])
        state = (await self.client.get("/api/state/project-main")).json()
        self.assertEqual(len(state["members"]), 8)
        self.assertEqual(len(state["tasks"]), 1)
        self.assertNotIn("demo_content", state["tasks"][0]["stages"][0])

    async def test_catalog_and_each_profile_expose_russian_descriptions_preserving_originals(self):
        response = await self.client.get("/api/catalog")
        self.assertEqual(response.status_code, 200)
        catalog = response.json()
        self.assertEqual(len(catalog["agents"]), 282)
        for summary in catalog["agents"]:
            source = self.store.get("profiles", summary["id"])
            self.assertEqual(summary["display_name_ru"], ROLE_NAMES_RU[source["id"]])
            self.assertEqual(summary["description_ru"], ROLE_DESCRIPTIONS_RU[source["id"]])
            self.assertEqual({key: summary[key] for key in source if key != "instructions_md"}, {key: value for key, value in source.items() if key != "instructions_md"})
            full = (await self.client.get("/api/profiles/" + source["id"])).json()
            self.assertEqual(full, localized_profile(source))
            self.assertEqual(full["instructions_md"], source["instructions_md"])
            self.assertEqual(full["source_sha256"], source["source_sha256"])

    async def test_bulk_team_api_requires_empty_body_and_keeps_demo_team_workflow(self):
        route = "/api/projects/project-main/members/import-all"
        for invalid in [{"tools": ["browser"]}, [], {"autonomy": "schedule"}]:
            self.assertEqual((await self.client.post(route, json=invalid)).status_code, 422)
        task = self.store.rows("tasks", "project-main")[0]
        response = await self.client.post(route, json={})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"added": 274, "total": 282, "categories": 18})
        state = (await self.client.get("/api/state/project-main")).json()
        self.assertEqual(len(state["members"]), 282)
        self.assertEqual(len({self.store.get("profiles", member["profile_id"])["category"] for member in state["members"]}), 18)
        self.assertTrue(all(member["status"] == "free" for member in state["members"]))
        self.assertEqual(self.store.get("tasks", task["id"]), task)
        self.assertEqual(len({stage["agent_id"] for stage in task["stages"]}), 8)
        self.assertEqual((await self.client.post(route, json={})).json()["added"], 0)
        project = (await self.client.post("/api/projects", json={"name": "Стартовая команда"})).json()
        self.assertEqual(len(self.store.members(project["id"])), 8)

    async def test_api_create_project_task_custom_stage_material_download_and_preferences(self):
        project = (await self.client.post("/api/projects", json={"name": "Тестовый", "context": "Бриф"})).json()
        pid = project["id"]
        material = (await self.client.post(f"/api/projects/{pid}/materials", json={"title": "Исходник", "content": "<script>alert(1)</script>"})).json()
        task_response = await self.client.post(f"/api/projects/{pid}/tasks", json={"title": "Проверка", "goal": "Собрать результат", "agents": [FIRST], "material_ids": [material["id"]], "stage_names": ["Особенный этап"]})
        self.assertEqual(task_response.status_code, 200)
        tid = task_response.json()["id"]
        self.assertEqual(task_response.json()["stages"][0]["name"], "Особенный этап")
        for action in ["start", "next", "next", "approve"]:
            response = await self.client.post(f"/api/tasks/{tid}/action", json={"action": action})
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "completed")
        download = await self.client.get(f"/api/materials/{material['id']}/download")
        self.assertIn("attachment", download.headers["content-disposition"])
        self.assertIn("text/markdown", download.headers["content-type"])
        self.assertEqual(download.text, "<script>alert(1)</script>")
        await self.client.put(f"/api/projects/{pid}/preferences", json={"motion": False, "view": "graph"})
        await self.client.put(f"/api/projects/{pid}/preferences", json={"category": "design"})
        state = (await self.client.get(f"/api/state/{pid}")).json()
        self.assertEqual(state["preferences"], {"motion": False, "view": "graph", "category": "design"})

    async def test_malformed_input_is_4xx_and_does_not_mutate(self):
        cases = [("/api/projects", {"name": "   "}), ("/api/projects", {"name": "x" * 121}), ("/api/projects", {"name": "Имя", "unexpected": True}), ("/api/projects/project-main/tasks", {"title": "x", "goal": "x", "agents": [FIRST], "priority": "urgent"}), ("/api/projects/project-main/tasks", {"title": "x", "goal": "x", "agents": [FIRST], "stage_names": [" "]}), ("/api/tasks/unknown/action", {"action": "shell", "comment": "rm -rf"})]
        for path, body in cases:
            with self.subTest(path=path, body=body):
                response = await self.client.post(path, json=body)
                self.assertTrue(400 <= response.status_code < 500, response.text)
        for path in ["/api/settings/mode", "/api/projects/project-main/preferences"]:
            for body in ["[1,2]", "{broken"]:
                response = await self.client.put(path, content=body, headers={"content-type": "application/json"})
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(len(self.store.rows("projects")), 1)
        self.assertEqual((await self.client.get("/api/projects/project-main/events?after=-1")).status_code, 422)

    async def test_catalog_invalid_json_oversize_and_duplicate_import_are_rejected(self):
        bad = await self.client.post("/api/catalog/import", content="broken", headers={"content-type": "application/json"})
        self.assertEqual(bad.status_code, 422)
        oversized = await self.client.post("/api/catalog/import", content=b" " * 20_000_001, headers={"content-type": "application/json"})
        self.assertEqual(oversized.status_code, 413)
        data = json.loads((CATALOG / "agents.json").read_text(encoding="utf-8"))
        data["agents"].append(data["agents"][0])
        data["agent_count"] += 1
        self.assertEqual((await self.client.post("/api/catalog/import", json=data)).status_code, 409)
        self.assertEqual(len(self.store.rows("profiles")), 282)

    async def test_local_host_origin_and_json_boundary_protect_mutations(self):
        for origin in ["https://evil.example", "null", "http://localhost.evil.example:4197"]:
            response = await self.client.post("/api/projects", json={"name": "Атака"}, headers={"origin": origin})
            self.assertEqual(response.status_code, 403)
        self.assertEqual((await self.client.get("/api/health", headers={"host": "evil.example:4197"})).status_code, 400)
        self.assertEqual((await self.client.post("/api/catalog/import", content='{}', headers={"content-type": "text/plain"})).status_code, 415)
        self.assertEqual((await self.client.get("/api/health", headers={"origin": "http://localhost:5173"})).status_code, 200)
        self.assertEqual(len(self.store.rows("projects")), 1)

    async def test_secret_health_and_error_responses_do_not_expose_env_or_provider(self):
        with patch.dict(os.environ, MODEL_ENV):
            response = await self.client.get("/api/health")
            self.assertTrue(response.json()["model"]["available"])
            self.assertNotIn("SECRET-DO-NOT-LEAK", response.text)
            self.assertNotIn("model.example", response.text)
        response = await self.client.get("/api/profiles/%27%20OR%201%3D1--")
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("SELECT", response.text)
        for path in ["/api/profiles/..%2F..%2F.env", "/api/materials/..%2F..%2F.env/download", "/.env", "/catalog/agents.json", "/data/office.db"]:
            response = await self.client.get(path)
            self.assertIn(response.status_code, [404, 409])
            self.assertNotIn("SECRET-DO-NOT-LEAK", response.text)

    async def test_sse_last_event_id_replay_deduplicates_and_has_identifiers(self):
        first = self.store.emit("project-main", "a", "Первое", task_id="task-a", agent_id=FIRST)
        second = self.store.emit("project-main", "b", "Второе", task_id="task-a", agent_id=SECOND)
        route = next(r for r in self.app.routes if getattr(r, "path", "") == "/api/projects/{project_id}/stream")
        class FakeRequest:
            headers = {"Last-Event-ID": str(first["seq"])}
            def __init__(self):
                self.calls = 0
            async def is_disconnected(self):
                self.calls += 1
                return self.calls > 1
        response = await route.endpoint("project-main", FakeRequest(), after=0)
        chunks = [chunk async for chunk in response.body_iterator]
        text = "".join(chunks)
        self.assertIn("retry: 2000", text)
        self.assertIn("id: " + str(second["seq"]), text)
        self.assertNotIn('"id": "' + first["id"] + '"', text)
        self.assertEqual(text.count(second["id"]), 1)
        self.assertIn('"project_id": "project-main"', text)


if __name__ == "__main__":
    unittest.main()
