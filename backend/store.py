"""SQLite catalog, project configuration and durable event log."""
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .localization import member_name_ru

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("OFFICE_DATA_DIR", str(ROOT / "data")))
CATALOG_DIR = Path(os.getenv("OFFICE_CATALOG_DIR", str(ROOT / "catalog")))
COLORS = {
    "specialized": "#ef8a98", "project-management": "#83a9ef",
    "design": "#e8bf70", "engineering": "#a394ef", "testing": "#7bc8b1",
    "sales": "#f080a5", "marketing": "#e4c469", "finance": "#74d5a0",
    "support": "#6bcddc", "academic": "#caa980", "game-development": "#b8a0eb",
    "gis": "#87c6af", "healthcare": "#8fcab6", "paid-media": "#e2ab78",
    "product": "#9ca9f0", "research": "#8cb8d5", "security": "#c68aae",
    "spatial-computing": "#a1b8d8",
}
TOOLS = [
    {"id": "project_context", "name": "Контекст проекта", "description": "Чтение явно выбранных исходных материалов", "connected": True, "kind": "local"},
    {"id": "previous_materials", "name": "Материалы этапов", "description": "Чтение результата предыдущего этапа", "connected": True, "kind": "local"},
    {"id": "material_export", "name": "Сохранение результата", "description": "Запись Markdown-материала в проект", "connected": True, "kind": "local"},
    {"id": "browser", "name": "Браузер", "description": "Внешняя интеграция не подключена", "connected": False, "kind": "external"},
    {"id": "github", "name": "GitHub", "description": "Внешняя интеграция не подключена", "connected": False, "kind": "external"},
]


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def dumps(data):
    return json.dumps(data, ensure_ascii=False)


class Store:
    def __init__(self, directory=None, catalog_dir=None):
        self.directory = Path(directory or DATA_DIR)
        self.catalog_dir = Path(catalog_dir or CATALOG_DIR)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.directory / "office.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS categories(id TEXT PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS members(project_id TEXT, profile_id TEXT, body TEXT NOT NULL,
          PRIMARY KEY(project_id,profile_id), FOREIGN KEY(project_id) REFERENCES projects(id),
          FOREIGN KEY(profile_id) REFERENCES profiles(id));
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, project_id TEXT, body TEXT NOT NULL,
          FOREIGN KEY(project_id) REFERENCES projects(id));
        CREATE TABLE IF NOT EXISTS materials(id TEXT PRIMARY KEY, project_id TEXT, task_id TEXT, body TEXT NOT NULL,
          FOREIGN KEY(project_id) REFERENCES projects(id));
        CREATE INDEX IF NOT EXISTS idx_materials_project ON materials(project_id);
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE,
          project_id TEXT, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, body TEXT NOT NULL);
        """)
        self.import_catalog(json.loads((self.catalog_dir / "agents.json").read_text(encoding="utf-8")))
        if not self.rows("projects"):
            self.create_project("Лендинг AI-студии", "Создать понятный лендинг услуги разработки с ИИ. Аудитория: малый бизнес. Язык: русский.", "project-main")
        self.localize_default_member_names()
        self.db.commit()

    def rows(self, table, project_id=None):
        # Table names are internal constants, never supplied by clients.
        with self.lock:
            sql = f"SELECT body FROM {table}"
            params = ()
            if project_id is not None:
                sql += " WHERE project_id=?"
                params = (project_id,)
            return [json.loads(r["body"]) for r in self.db.execute(sql, params).fetchall()]

    def get(self, table, id):
        with self.lock:
            row = self.db.execute(f"SELECT body FROM {table} WHERE id=?", (id,)).fetchone()
            if row is None:
                raise ValueError("Объект не найден")
            return json.loads(row["body"])

    def save(self, table, obj, commit=True):
        with self.lock:
            if table in ("tasks", "materials"):
                if table == "materials":
                    self.db.execute("INSERT OR REPLACE INTO materials VALUES(?,?,?,?)", (obj["id"], obj["project_id"], obj.get("task_id"), dumps(obj)))
                else:
                    self.db.execute("INSERT OR REPLACE INTO tasks VALUES(?,?,?)", (obj["id"], obj["project_id"], dumps(obj)))
            else:
                self.db.execute(f"INSERT OR REPLACE INTO {table} VALUES(?,?)", (obj["id"], dumps(obj)))
            if commit:
                self.db.commit()
        return obj

    def setting(self, key, default=None):
        with self.lock:
            row = self.db.execute("SELECT body FROM settings WHERE key=?", (key,)).fetchone()
            return json.loads(row["body"]) if row else default

    def set_setting(self, key, value):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, dumps(value)))
            self.db.commit()
        return value

    def import_catalog(self, data):
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("Нужна схема каталога версии 1")
        agents, categories = data.get("agents"), data.get("categories")
        if not isinstance(agents, list) or not agents or not isinstance(categories, list):
            raise ValueError("Каталог должен содержать agents и categories")
        category_ids, ids = set(), set()
        for cat in categories:
            if not isinstance(cat, dict) or not isinstance(cat.get("id"), str) or not cat["id"] or cat["id"] in category_ids:
                raise ValueError("Некорректный или повторяющийся идентификатор категории")
            category_ids.add(cat["id"])
        for profile in agents:
            if not isinstance(profile, dict) or any(not isinstance(profile.get(k), str) or not profile[k].strip() for k in ("id", "name", "category", "instructions_md")):
                raise ValueError("Обязательные поля: id, name, category, instructions_md")
            if profile["id"] in ids:
                raise ValueError(f"Повторяющийся id: {profile['id']}")
            if profile["category"] not in category_ids:
                raise ValueError(f"Неизвестная категория: {profile['category']}")
            ids.add(profile["id"])
        if data.get("agent_count") != len(agents):
            raise ValueError("agent_count не совпадает с количеством профилей")
        # Validate everything first, then upsert atomically; membership stays intact.
        with self.lock, self.db:
            for cat in categories:
                self.db.execute("INSERT INTO categories VALUES(?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body", (cat["id"], dumps({**cat, "ui_color": COLORS.get(cat["id"], "#8cb8d5")})))
            for profile in agents:
                self.db.execute("INSERT INTO profiles VALUES(?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body", (profile["id"], dumps(profile)))
            self.db.execute("INSERT OR REPLACE INTO settings VALUES('catalog_source',?)", (dumps(data.get("source", {})),))
        return {"imported": len(agents), "categories": len(categories)}

    def emit(self, project_id, action, text, task_id=None, agent_id=None, commit=True, **extra):
        event = {"id": uid("evt"), "time": now(), "project_id": project_id, "task_id": task_id, "agent_id": agent_id, "action": action, "text": text, **extra}
        with self.lock:
            cursor = self.db.execute("INSERT INTO events(id,project_id,body) VALUES(?,?,?)", (event["id"], project_id, dumps(event)))
            event["seq"] = cursor.lastrowid
            self.db.execute("UPDATE events SET body=? WHERE seq=?", (dumps(event), event["seq"]))
            if commit:
                self.db.commit()
        return event

    def find_source_duplicate(self, project_id, filename=None, sha256=None, source_url=None, title=None):
        with self.lock:
            for material in self.rows("materials", project_id):
                if material.get("kind") != "source":
                    continue
                attachment = material.get("attachment") or {}
                if filename is not None and attachment.get("filename") == filename and attachment.get("sha256") == sha256:
                    return material
                if source_url is not None and material.get("source_url") == source_url and material.get("title") == title:
                    return material
        return None

    def add_source_material(self, material):
        """Deduplicate and persist the source plus its event in one transaction."""
        with self.lock, self.db:
            self.get("projects", material["project_id"])
            attachment = material.get("attachment")
            duplicate = None
            if attachment:
                duplicate = self.find_source_duplicate(material["project_id"], filename=attachment["filename"], sha256=attachment["sha256"])
            elif material.get("source_url"):
                duplicate = self.find_source_duplicate(material["project_id"], source_url=material["source_url"], title=material["title"])
            if duplicate:
                return duplicate, False
            self.save("materials", material, commit=False)
            self.emit(material["project_id"], "material_added", "Добавлен исходный материал: " + material["title"], material_id=material["id"], commit=False)
            return material, True

    def events(self, project_id, after=0, limit=150, replay=False):
        with self.lock:
            if after or replay:
                rows = self.db.execute("SELECT body FROM events WHERE project_id=? AND seq>? ORDER BY seq LIMIT ?", (project_id, after, limit)).fetchall()
            else:
                rows = self.db.execute("SELECT body FROM events WHERE project_id=? ORDER BY seq DESC LIMIT ?", (project_id, limit)).fetchall()[::-1]
        return [json.loads(r["body"]) for r in rows]

    def members(self, project_id):
        return self.rows("members", project_id)

    def localize_default_member_names(self):
        """Idempotently migrate default labels while retaining all user settings."""
        with self.lock, self.db:
            profiles = {profile["id"]: profile for profile in self.rows("profiles")}
            changed = 0
            for member in self.rows("members"):
                name = member_name_ru(profiles[member["profile_id"]], member.get("display_name_ru", ""))
                if name != member.get("display_name_ru", ""):
                    member["display_name_ru"] = name
                    self.db.execute("UPDATE members SET body=? WHERE project_id=? AND profile_id=?", (dumps(member), member["project_id"], member["profile_id"]))
                    changed += 1
            return changed

    def member(self, project_id, profile_id):
        member = next((m for m in self.members(project_id) if m["profile_id"] == profile_id), None)
        if not member:
            raise ValueError("Агент не добавлен в команду проекта")
        return member

    def save_member(self, project_id, profile_id, config):
        with self.lock:
            return self._save_member(project_id, profile_id, config)

    def _save_member(self, project_id, profile_id, config, commit=True):
        self.get("projects", project_id)
        profile = self.get("profiles", profile_id)
        old = next((m for m in self.members(project_id) if m["profile_id"] == profile_id), {})
        obj = {"profile_id": profile_id, "project_id": project_id, "display_name_ru": "", "autonomy": "task", "tools": ["project_context", "previous_materials", "material_export"], "manager_id": "agents-orchestrator", **old, **config}
        obj["display_name_ru"] = member_name_ru(profile, obj["display_name_ru"])
        if obj["autonomy"] not in ("confirm", "task", "schedule"):
            raise ValueError("Неизвестный уровень автономности")
        if not isinstance(obj["tools"], list) or any(t not in {t["id"] for t in TOOLS} for t in obj["tools"]):
            raise ValueError("Неизвестный инструмент")
        if obj.get("manager_id") == profile_id:
            raise ValueError("Агент не может руководить собой")
        if obj.get("manager_id") and obj["manager_id"] not in {m["profile_id"] for m in self.members(project_id)}:
            raise ValueError("Руководитель должен быть участником команды проекта")
        # Prevent hierarchy cycles, including indirect cycles.
        managers = {m["profile_id"]: m.get("manager_id") for m in self.members(project_id)}
        managers[profile_id] = obj.get("manager_id")
        seen, parent = {profile_id}, obj.get("manager_id")
        while parent:
            if parent in seen:
                raise ValueError("В иерархии обнаружен цикл")
            seen.add(parent)
            parent = managers.get(parent)
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO members VALUES(?,?,?)", (project_id, profile_id, dumps(obj)))
            if commit:
                self.db.commit()
        return obj

    def add_all_profiles(self, project_id):
        """Add the complete library atomically, preserving every existing member setting."""
        with self.lock, self.db:
            self.get("projects", project_id)
            profiles = self.rows("profiles")
            existing = {member["profile_id"] for member in self.members(project_id)}
            coordinator = "agents-orchestrator" if any(profile["id"] == "agents-orchestrator" for profile in profiles) else None
            # A manager must exist before its reports are inserted.
            profiles.sort(key=lambda profile: (profile["id"] != coordinator, profile["id"]))
            added = 0
            for profile in profiles:
                if profile["id"] not in existing:
                    self._save_member(project_id, profile["id"], {"manager_id": None if profile["id"] == coordinator else coordinator}, commit=False)
                    added += 1
            total = len(self.members(project_id))
            categories = len({profile["category"] for profile in profiles})
            if added:
                self.emit(project_id, "team_imported", f"Добавлено участников: {added}. В команде {total} профиля из {categories} отделов; настройки существующих участников сохранены.", added=added, total=total, categories=categories, commit=False)
            return {"added": added, "total": total, "categories": categories}

    def remove_member(self, project_id, profile_id):
        self.member(project_id, profile_id)
        for task in self.rows("tasks", project_id):
            if task["status"] in ("running", "awaiting_approval") and any(s["agent_id"] == profile_id for s in task["stages"]):
                raise ValueError("Сначала завершите или отмените активную задачу агента")
        with self.lock:
            self.db.execute("DELETE FROM members WHERE project_id=? AND profile_id=?", (project_id, profile_id))
            for member in self.members(project_id):
                if member.get("manager_id") == profile_id:
                    member["manager_id"] = None
                    self.db.execute("UPDATE members SET body=? WHERE project_id=? AND profile_id=?", (dumps(member), project_id, member["profile_id"]))
            self.db.commit()
        self.emit(project_id, "team_changed", "Агент удалён из команды; профиль сохранён в каталоге", agent_id=profile_id)

    def create_project(self, name, context="", project_id=None):
        project = {"id": project_id or uid("project"), "name": name, "context": context, "owner": "Владелец проекта", "created_at": now()}
        self.save("projects", project)
        starter = json.loads((self.catalog_dir / "starter-team.json").read_text(encoding="utf-8"))
        for member in starter["members"]:
            self.save_member(project["id"], member["profile_id"], {**member, "manager_id": None if member["profile_id"] == "agents-orchestrator" else "agents-orchestrator"})
        self.save("materials", {"id": uid("mat"), "project_id": project["id"], "task_id": None, "title": "Бриф проекта", "content": context or "Добавьте контекст проекта.", "kind": "source", "example": False, "created_at": now(), "agent_id": None})
        self.emit(project["id"], "project_created", "Проект создан. Стартовая команда добавлена.")
        return project

    def close(self):
        with self.lock:
            self.db.close()
