# API reference

Base URL: `http://127.0.0.1:4197`. The running application's `/docs` and `/openapi.json` describe the exact typed contract. This document explains the supported workflow; it is not a substitute for the generated schema.

## Route map

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Health, selected executor and non-secret model configuration |
| GET | `/api/catalog` | Profiles without full instructions, Russian presentation fields, categories and provenance |
| GET | `/api/profiles/{profile_id}` | One full original profile with separate Russian presentation |
| POST | `/api/catalog/import` | Validate and transactionally import a catalog JSON object |
| GET | `/api/state/{project_id}` | Project snapshot: members, tasks, materials, events, tools, mode and preferences |
| POST | `/api/projects` | Create an isolated project with starter membership and its demo task |
| PUT | `/api/projects/{project_id}` | Update project name and context |
| PUT | `/api/projects/{project_id}/members/{profile_id}` | Add or update a member's configuration |
| DELETE | `/api/projects/{project_id}/members/{profile_id}` | Remove membership while retaining the catalog profile |
| POST | `/api/projects/{project_id}/members/import-all` | Add missing catalog members; preserve existing settings |
| POST | `/api/projects/{project_id}/tasks` | Create an ordered task |
| GET | `/api/tasks/{task_id}` | Full task detail and stage input/output references |
| POST | `/api/tasks/{task_id}/action` | Start, play, step, approve, reject, pause, cancel or reset |
| POST | `/api/projects/{project_id}/materials` | Add a source material |
| GET | `/api/materials/{material_id}/download` | Download stored content as an attachment |
| PUT | `/api/settings/mode` | Select `demo` or explicitly configured `model` mode |
| PUT | `/api/projects/{project_id}/preferences` | Save view, category, graph filters and motion preference |
| GET | `/api/projects/{project_id}/events` | Persisted event history |
| GET | `/api/projects/{project_id}/stream` | SSE replay and live events |

Mutating routes require JSON where applicable and reject unrelated origins. Most typed input bodies forbid extra fields. A valid profile ID does not grant membership in another project.

## Create a project

```http
POST /api/projects
Content-Type: application/json
```

```json
{"name":"Client proposal","context":"Prepare a proposal for a local service business."}
```

Use the returned project's `id` in subsequent routes. `project-main` is the primary office.

## Expand a team

```http
POST /api/projects/project-main/members/import-all
Content-Type: application/json
```

```json
{}
```

The result includes `added` and `total`. Repeating an already complete import returns `added: 0` without duplicate membership or repeat addition events.

## Configure a member

```json
{
  "display_name_ru":"Координатор",
  "autonomy":"confirm",
  "tools":["project_context","previous_materials","material_export"],
  "manager_id":null
}
```

Autonomy values: `confirm`, `task`, `schedule`. Manager cycles are rejected. The display name is user content; localization does not overwrite a custom name.

## Create an ordered task

```json
{
  "title":"Prepare a reviewed proposal",
  "goal":"Create a concise scope, implementation plan and review notes.",
  "priority":"normal",
  "agents":["agents-orchestrator","design-ux-researcher"],
  "stage_names":["Plan","Review user needs"],
  "material_ids":[],
  "completion":"All defined stages complete and the owner accepts the result.",
  "scheduled_at":null
}
```

Every executor must belong to the selected project. Materials must belong to the same project. When supplied, `stage_names` must match the executor list. Scheduled timestamps must include a timezone; they are normalized to UTC. Priority values: `low`, `normal`, `high`.

## Execute or review

```json
{"action":"start","mode":"demo","comment":""}
```

| Action | Behavior |
| --- | --- |
| `start` | Start a manual run using the requested mode |
| `play` | Start or continue automatic execution |
| `next` | Start a pending stage or execute/complete the active stage |
| `pause` | Stop automatic stepping |
| `approve` | Approve the pending stage or final result |
| `reject` | Return the current approval with a specific comment |
| `cancel` | Prevent further stages while preserving results |
| `reset` | Create a new run and preserve previous history/materials |

Only configured, enabled model mode can call a provider. A role prompt cannot enable model access or grant tools.

## SSE

```bash
curl -N http://127.0.0.1:4197/api/projects/project-main/stream
```

Reconnect with `Last-Event-ID` or an `after` sequence cursor. Events include their ID, sequence, time, project and available task/agent/material references. Deduplicate by event ID; do not infer multiple actions from duplicate delivery. The UI restores a state snapshot after reconnecting.

## Errors

| Status | Typical cause |
| --- | --- |
| 400 / 403 | Host or Origin boundary rejection |
| 404 | Unknown entity or denied static file path |
| 409 | Invalid action, concurrent completion, hierarchy conflict or an unavailable configured mode |
| 413 | Catalog import exceeds the 20 MB limit |
| 415 / 422 | Invalid content type or typed input |

Exact status/detail text is defined by the current handler and schema. Provider error details are sanitized; API responses never return model credentials. API messages intended for the interface are in Russian.
