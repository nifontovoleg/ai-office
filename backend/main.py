import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware


class InputBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def meaningful_strings(cls, value):
        if isinstance(value, str) and value and not value.strip():
            raise ValueError("Поле не может состоять из пробелов")
        return value

from .store import ROOT, DATA_DIR, Store, TOOLS, now, uid
from .runtime import Engine, model_config
from .localization import localized_profile


class ProjectBody(InputBody):
    name: str = Field(min_length=1, max_length=120)
    context: str = Field(default="", max_length=20000)


class TaskBody(InputBody):
    title: str = Field(min_length=1, max_length=180)
    goal: str = Field(min_length=1, max_length=20000)
    priority: Literal["low", "normal", "high"] = "normal"
    agents: list[str] = Field(default_factory=list, max_length=100)
    material_ids: list[str] = Field(default_factory=list, max_length=100)
    stage_names: list[str] = Field(default_factory=list, max_length=100)
    completion: str = Field(default="Все этапы завершены и результат согласован владельцем", min_length=1, max_length=20000)
    scheduled_at: str | None = None


class ActionBody(InputBody):
    action: Literal["start", "play", "next", "approve", "reject", "reset", "pause", "cancel"]
    mode: Literal["demo", "model"] = "demo"
    comment: str = Field(default="", max_length=20000)


class MemberBody(InputBody):
    display_name_ru: str = Field(default="", max_length=100)
    autonomy: Literal["confirm", "task", "schedule"] = "task"
    tools: list[str] = Field(default_factory=lambda: ["project_context", "previous_materials", "material_export"], max_length=5)
    manager_id: str | None = "agents-orchestrator"


class MaterialBody(InputBody):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=100000)


class ModeBody(InputBody):
    mode: Literal["demo", "model"]


class BulkMemberBody(InputBody):
    pass


class PreferenceBody(BaseModel):
    motion: bool | None = None
    view: Literal["radial", "graph", "department", "hierarchy"] | None = None
    category: str | None = Field(default=None, max_length=100)
    graph_filters: list[str] | None = Field(default=None, max_length=10)


def create_app(store=None):
    fresh_default = store is None and not (DATA_DIR / "office.db").exists()
    database = store or Store()
    if fresh_default:
        database.add_all_profiles("project-main")
    engine = Engine(database)
    for project in database.rows("projects"):
        engine.ensure_demo(project["id"])
    # Recover interrupted stages without silently resuming paid provider calls.
    for task in database.rows("tasks"):
        interrupted = any(stage["status"] == "running" for stage in task["stages"])
        if task.get("auto") or interrupted:
            task["auto"] = False
            if interrupted and task["status"] != "cancelled":
                task["status"] = "error"
                task["stages"][task["cursor"]].update(status="error", error="Сервер перезапущен во время этапа. Повторный вызов требует явного запуска.", finished_at=now())
            database.save("tasks", task)
            database.emit(task["project_id"], "recovered", "Автозапуск приостановлен после перезапуска сервера", task["id"])

    @asynccontextmanager
    async def lifespan(app):
        scheduler = asyncio.create_task(engine.schedule_loop())
        yield
        scheduler.cancel()
        await asyncio.gather(scheduler, return_exceptions=True)
        await engine.shutdown()

    app = FastAPI(title="AI Office", lifespan=lifespan)
    app.state.store, app.state.engine = database, engine
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])

    @app.middleware("http")
    async def local_request_boundary(request, call_next):
        # Local single-user app: prevent a remote page from mutating loopback data.
        from fastapi.responses import JSONResponse
        origin = request.headers.get("origin")
        allowed = {"http://localhost:4197", "http://127.0.0.1:4197", "http://localhost:5173", "http://127.0.0.1:5173", str(request.base_url).rstrip("/")}
        allowed.update(v.strip() for v in os.getenv("OFFICE_ALLOWED_ORIGINS", "").split(",") if v.strip())
        if origin and origin not in allowed:
            return JSONResponse(status_code=403, content={"detail": "Запрос с этого Origin запрещён для локального офиса"})
        if request.method in ("POST", "PUT", "PATCH") and request.url.path.startswith("/api/"):
            if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                return JSONResponse(status_code=415, content={"detail": "API принимает application/json"})
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/api/health")
    def health():
        return {"status": "ok", "executor": database.setting("mode", "demo"), "model": model_config()}

    @app.get("/api/catalog")
    def catalog():
        agents = [{k: v for k, v in localized_profile(p).items() if k != "instructions_md"} for p in database.rows("profiles")]
        return {"agents": agents, "categories": database.rows("categories"), "agent_count": len(agents), "source": database.setting("catalog_source")}

    @app.get("/api/profiles/{profile_id}")
    def profile(profile_id: str):
        return localized_profile(database.get("profiles", profile_id))

    @app.post("/api/catalog/import")
    async def import_catalog(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 20_000_000:
                raise HTTPException(413, "Каталог превышает 20 МБ")
        try:
            data = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(422, "Некорректный JSON")
        result = database.import_catalog(data)
        for project in database.rows("projects"):
            database.emit(project["id"], "catalog_imported", f"Обновлено профилей: {result['imported']}; настройки команды сохранены")
        return result

    @app.get("/api/state/{project_id}")
    def state(project_id: str):
        project = database.get("projects", project_id)
        tasks = database.rows("tasks", project_id)
        mode = database.setting("mode", "demo")
        members = database.members(project_id)
        for member in members:
            member["status"] = "free" if mode == "demo" or model_config()["available"] else "disconnected"
            member["task_id"] = None
            for task in tasks:
                if task["status"] in ("running", "awaiting_approval", "error"):
                    index = min(task["cursor"], len(task["stages"]) - 1)
                    if task["stages"][index]["agent_id"] == member["profile_id"]:
                        member["task_id"] = task["id"]
                        member["status"] = "approval" if task["status"] == "awaiting_approval" else "error" if task["status"] == "error" else "working" if task["stages"][index]["status"] == "running" else "queued"
                        break
        public_tasks = []
        for task in tasks:
            public_tasks.append({**task, "stages": [{k: v for k, v in s.items() if k not in ("demo_content", "input")} for s in task["stages"]], "history": [{"run_id": h["run_id"], "status": h["status"], "finished_at": h["finished_at"]} for h in task["history"]]})
        return {"project": project, "projects": database.rows("projects"), "members": members, "tasks": public_tasks, "materials": database.rows("materials", project_id), "events": database.events(project_id), "tools": TOOLS, "mode": mode, "model": model_config(), "preferences": database.setting("preferences:" + project_id, {})}

    @app.post("/api/projects")
    def create_project(body: ProjectBody):
        project = database.create_project(body.name, body.context)
        engine.ensure_demo(project["id"])
        return project

    @app.put("/api/projects/{project_id}")
    def update_project(project_id: str, body: ProjectBody):
        project = database.get("projects", project_id)
        project.update(name=body.name, context=body.context)
        database.save("projects", project)
        database.emit(project_id, "project_changed", "Настройки проекта сохранены")
        return project

    @app.put("/api/projects/{project_id}/members/{profile_id}")
    def save_member(project_id: str, profile_id: str, body: MemberBody):
        result = database.save_member(project_id, profile_id, body.model_dump())
        database.emit(project_id, "team_changed", "Настройки участника сохранены", agent_id=profile_id)
        return result

    @app.delete("/api/projects/{project_id}/members/{profile_id}")
    def remove_member(project_id: str, profile_id: str):
        database.remove_member(project_id, profile_id)
        return {"ok": True}

    @app.post("/api/projects/{project_id}/members/import-all")
    def add_all_members(project_id: str, body: BulkMemberBody):
        return database.add_all_profiles(project_id)

    @app.post("/api/projects/{project_id}/tasks")
    def create_task(project_id: str, body: TaskBody):
        if body.priority not in ("low", "normal", "high"):
            raise ValueError("Некорректный приоритет")
        return engine.create_task(project_id, **body.model_dump())

    @app.get("/api/tasks/{task_id}")
    def task_detail(task_id: str):
        return database.get("tasks", task_id)

    @app.post("/api/tasks/{task_id}/action")
    async def task_action(task_id: str, body: ActionBody):
        return await engine.action(task_id, **body.model_dump())

    @app.post("/api/projects/{project_id}/materials")
    def create_material(project_id: str, body: MaterialBody):
        database.get("projects", project_id)
        material = {"id": uid("mat"), "project_id": project_id, "task_id": None, "title": body.title, "content": body.content, "kind": "source", "example": False, "created_at": now(), "agent_id": None}
        database.save("materials", material)
        database.emit(project_id, "material_added", "Добавлен исходный материал: " + body.title, material_id=material["id"])
        return material

    @app.get("/api/materials/{material_id}/download")
    def download_material(material_id: str):
        from fastapi.responses import Response
        material = database.get("materials", material_id)
        return Response(material["content"], media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{material_id}.md"'})

    @app.put("/api/settings/mode")
    async def set_mode(body: ModeBody):
        mode = body.mode
        if mode == "model" and not model_config()["available"]:
            raise ValueError("Модель не подключена. Настройте .env сервера; ключ хранится только на сервере.")
        return database.set_setting("mode", mode)

    @app.put("/api/projects/{project_id}/preferences")
    async def preferences(project_id: str, body: PreferenceBody):
        database.get("projects", project_id)
        clean = {**database.setting("preferences:" + project_id, {}), **body.model_dump(exclude_unset=True)}
        return database.set_setting("preferences:" + project_id, clean)

    @app.get("/api/projects/{project_id}/events")
    def events(project_id: str, after: int = Query(default=0, ge=0)):
        database.get("projects", project_id)
        return database.events(project_id, after)

    @app.get("/api/projects/{project_id}/stream")
    async def stream(project_id: str, request: Request, after: int = Query(default=0, ge=0)):
        database.get("projects", project_id)
        try:
            cursor = max(after, 0, int(request.headers.get("Last-Event-ID", "0")))
        except ValueError:
            cursor = after
        async def generate():
            nonlocal cursor
            yield "retry: 2000\n\n"
            beats = 0
            while not await request.is_disconnected():
                for event in database.events(project_id, cursor, replay=True):
                    if event["seq"] > cursor:
                        cursor = event["seq"]
                        yield f"id: {cursor}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                beats += 1
                if beats % 12 == 0:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(0.5)
        return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    dist = ROOT / "frontend" / "dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
        @app.get("/{path:path}")
        def frontend(path: str):
            first_segment = path.split("/", 1)[0]
            if path.startswith("api/") or first_segment.startswith(".") or first_segment in ("catalog", "data", "backend", "tests", "output"):
                raise HTTPException(404)
            return FileResponse(dist / "index.html")
    return app


app = create_app()
