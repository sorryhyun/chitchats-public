# ChitChats — Architecture Review

_Generated 2026-07-14. Scope: `backend/` (~28k LOC Python), `frontend/src` (~9.5k LOC TS/React), `scripts/`, `Makefile`._

> **Status:** P0 (the four auth holes, the dead `guidelines.yaml` system, the dropped `anthropic_calls`/`provider` columns, and the three frontend no-ops) was fixed and removed from this report on 2026-07-14. P1–P3 below are still open.

## Executive summary

The codebase does not primarily have a **duplication** problem — it has an **incomplete-refactor** problem. Several subsystems (the client pool, the agent-cleanup service, the caching layer) were rewritten, and the old implementations were never deleted. They are still exported, still reachable, and in three cases still referenced by code that would crash or silently no-op if it ran.

Two themes remain, in order of urgency:

1. **~1,500 lines of dead code**, some of it dangerous (a second `declarative_base()`, a module that opens a DB pool at import time, a dead fork that calls a nonexistent attribute).
2. **Inverted layering** — `core` has a bidirectional import dependency with *every* other package, papered over with 86 function-local imports.

A legend for confidence:

- **[V]** — I verified this directly (ran it, grepped it, or read the code myself).
- **[A]** — Reported by an audit agent; plausible and cited, but confirm before acting.

---

## P1 — Dead code (~1,500 lines, no behavior change)

Delete these. Three of them are actively hazardous, not merely unused.

### 10. `backend/crud/cleanup.py` (195 lines) — a stale fork that would crash **[V]**

It re-defines the same four functions as `backend/core/agent_service.py` (`delete_agent_with_cleanup`, `remove_agent_from_room_with_cleanup`, `delete_room_with_cleanup`, `clear_room_messages_with_cleanup`). All routers import the `core/agent_service.py` versions (`routers/rooms.py:16`, `routers/agents.py:8`, `routers/room_agents.py:8`, `routers/user.py:11`).

The dead fork calls `agent_manager.client_pool` at `cleanup.py:46, 48, 75, 118, 183`. **`AgentManager` has no `client_pool` attribute** — `core/manager.py:62` defines `self._client_pools` (a dict keyed by provider). Every one of those six lines is an `AttributeError` waiting to fire. It is still exported from `crud/__init__.py:37-42`.

Note the semantic drift too: the live version (`core/agent_service.py:39`) calls `agent_manager.get_keys_for_agent(...)`, which searches **all** provider pools; the dead one assumed a single pool and would leak Codex clients.

**Fix:** delete `backend/crud/cleanup.py` and its re-exports in `crud/__init__.py`.

### 11. `backend/core/client_pool.py` (301 lines) — pre-abstraction ancestor **[V]**

A near-verbatim ancestor of `providers/base_pool.py` (same fast-path session compare, same double-check-under-lock, same shielded background disconnect). Its only importer is `core/__init__.py:20`. The retry-on-`ProcessTransport` loop it contains now lives at `providers/claude/provider.py:71-94`.

**Fix:** delete the module, the `core/__init__.py` export, and `tests/unit/test_client_pool.py` (412 lines) — `BaseClientPool` already covers the behavior.

### 12. `backend/infrastructure/database/connection.py` (95 lines) — dangerous **[A]**

Unimported by anything. But `connection.py:14` calls `create_async_engine()` **at import time** against a hardcoded Postgres URL, and `connection.py:31` declares a **second `Base = declarative_base()`**. Any accidental import binds models to the wrong metadata and opens a connection pool.

**Fix:** delete it.

### 13. `ProviderType.CUSTOM` dispatches to a module that doesn't exist **[V]**

`backend/providers/factory.py:52` does `from .custom import CustomProvider`. `backend/providers/` contains only `claude/` and `codex/` — there is no `custom/`. Worse, `get_available_providers()` (`factory.py:91`) returns `list(ProviderType)`, so it **advertises `"custom"`** to any caller, who then gets an `ImportError` from `get_provider("custom")`.

**Fix:** drop `CUSTOM` from the enum and the factory branch.

### 14. `backend/routers/tools_api.py` and `backend/routers/user.py` — entire routers, zero callers **[A]**

Cross-referenced against `frontend/src/services/*`. `GET /tools` and everything in `user.py` have no frontend or MCP caller.

### 15. Frontend dead components **[V]** — verified zero importers by grep

| File | Lines |
|---|---|
| `components/ui/dropdown-menu.tsx` | 201 |
| `components/ui/dialog.tsx` | 120 (also redundant with `ui/modal.tsx`) |
| `components/sidebar/CreateRoomForm.tsx` | 103 (`MainSidebar` inlines its own form) |
| `components/ui/scroll-area.tsx` | 48 |
| `components/ui/separator.tsx` | 29 |
| `components/ui/skeleton.tsx` | 15 |
| `components/chat-room/header/SidebarToggle.tsx` | — (`App.tsx:140` inlines the button) |

Note `ui/card.tsx` **is** used (one importer) — keep it.

### 16. Other dead exports **[A]**

- `core/auth.py:493-519` — a second `ensure_room_access` with an incompatible signature and zero importers, shadowing the real one in `core/dependencies.py:29` by name.
- `chatroom_orchestration/agent_ordering.py:14` — `separate_priority_agents()`, no callers; `tape/generator.py:56` `_separate_by_priority()` is a strict superset.
- `mcp_servers/config/loaders.py:234` — `merge_tool_configs()`, the old override mechanism, zero callers.
- `providers/base.py` — `AIMessage`, `AIStreamEvent`, `AIClientOptions.extra_options`, `AIProvider.create_client()` — all abstractions with no production callers.
- `ChatOrchestrator.priority_agent_names` (`orchestrator.py:44`) is stored and never read. `core/app_factory.py:177` reads settings, passes it in, and logs `"🎯 Priority agents enabled: …"` — **the startup log is lying**; priority actually resolves from `agent.priority` inside `TapeGenerator`.
- `/auth/google` appears in `core/auth.py:331`'s excluded-paths list. **The endpoint does not exist.** `settings.google_client_id` is likewise referenced nowhere.
- CRUD: `voice_audio_exists`, `get_agents_by_ids`, `get_agent_cached`, `invalidate_messages_cache` — zero callsites, all in `__all__`.

---

## P2 — The layering problem

### 17. `core` has a bidirectional dependency with every other package **[V]**

I built the package-level import graph. Every single pair is cyclic:

```
routers <-> core, core <-> crud, core <-> chatroom_orchestration,
core <-> infrastructure, core <-> providers, core <-> domain,
core <-> mcp_servers, providers <-> domain, crud <-> infrastructure, ...
```

The symptom: **86 function-local imports** across the backend (imports inside function bodies, the standard workaround for a circular dependency). Worst offenders: `crud/agents.py` (7), `mcp_servers/config/loaders.py` (6), `mcp_servers/action_server.py` (6), `core/app_factory.py` (6).

Specific inversions worth fixing, in increasing order of effort:

- **`domain` should be a leaf.** It isn't: `domain/agent_parser.py:328` imports `core.settings`; `domain/__init__.py:32` imports `mcp_servers.config.tools`; `domain/streaming.py:14` imports `providers.base`.
- **`infrastructure` should be a leaf.** It isn't: `infrastructure/generated_images.py:16` imports `core`; `infrastructure/database/models.py:94` imports `core.AgentConfigService` — **a SQLAlchemy table class calling a service and doing blocking filesystem IO** (see #18).
- **`infrastructure/scheduler.py` is not infrastructure.** It imports `crud`, `core.manager`, and `chatroom_orchestration` (`scheduler.py:13-18`). It is application/orchestration logic filed in the wrong package. Move it to `chatroom_orchestration/`.
- **`crud` should only touch `infrastructure` + `schemas`.** It reaches up into `core`, `providers`, and `mcp_servers` at `crud/agents.py:40,51,177,195,225,249`, `crud/helpers.py:10`, `crud/messages.py:35`.

**Fix:** this is not a rewrite. Each back-edge is a small extraction — move the shared type down into `domain`, or invert the call with a callback/protocol. Pay them off one at a time; the deferred-import count is a good progress metric (target: zero).

### 18. SQLAlchemy models reach into the cache and the filesystem **[A]**

`infrastructure/database/models.py:67-124` — `Agent.get_config_data()` imports `infrastructure.cache`, imports `core.AgentConfigService`, performs **blocking filesystem IO**, and writes to a global cache. It's called from async request handlers (`routers/voice.py:133`) and from CRUD. An ORM entity has become the config-loading service.

**Fix:** move it to `core/agent_config_service.py` as `load_config_for(agent)`; leave `models.Agent` a dumb table.

### 19. `core/cache_service.py` and `infrastructure/cache.py` are not two systems **[A]**

`CacheService.__init__` (`core/cache_service.py:42`) does `self._cache = cache_manager or get_cache()` — **the same global singleton** everything else uses. `get/set/invalidate/clear/get_stats/...` are verbatim passthroughs. Its only value-add is four semantic invalidators (`invalidate_agent`, `invalidate_room`, `invalidate_room_agents`, `invalidate_room_messages`) — which have **zero callers**. Meanwhile ~10 CRUD sites inline `get_cache().invalidate(room_agents_key(id))` by hand.

The only live use of `CacheService` at all is `routers/debug.py` calling three passthrough methods.

**You are paying the cost of both layers and getting the benefit of neither. Pick one:**
- **Delete** `core/cache_service.py` (161 lines) and point `routers/debug.py` at `get_cache()`; or
- **Commit to it** — move the ~10 scattered inline invalidations into the semantic invalidators and have CRUD call `cache_service.invalidate_room(id)`.

### 20. The cache stores live SQLAlchemy ORM objects across sessions **[A]** — highest-risk item in the report

`crud/cached.py:40, 61, 82` cache the results of `get_agent`/`get_room`/`get_agents` — **detached ORM instances bound to a closed `AsyncSession`** — for 30–300 seconds. `crud/room_agents.py:17` even carries a comment admitting the workaround: _"Query agents directly via join to avoid detached instance issues with cached objects."_

Any lazy-load on a cached object across requests raises `DetachedInstanceError`/`MissingGreenlet`. It works today only because `expire_on_commit=False` and the relationships happen to be eager-loaded — an undocumented coupling one `selectinload` removal away from production breakage.

**Fix:** cache serialized Pydantic models (`schemas.Room` / `schemas.Agent`), never ORM entities.

---

## P3 — Genuine duplication

### 21. The four MCP servers are ~85% copy-paste **[A]**

Byte-identical across `action_server.py:93-139`, `guidelines_server.py:90-116`, `etc_server.py:67-93`, `social_server.py:70-96`: the whole `list_tools()` body, `_get_env_config()`, the `logging.basicConfig` preamble, and the `main()` + `stdio_server()` + `__main__` block. The only difference is a group string.

**Fix:** one `build_server(name, group, handlers, context)` + one `run_stdio(factory)` in a new `mcp_servers/base.py`. Each server file collapses to its handlers plus a short registration. **~250 lines removed.**

### 22. `claude/prompts.yaml` and `codex/prompts.yaml` are 62-of-69 lines identical **[A]**

The genuine deltas are 4 tokens: `Anthropic`→`OpenAI`, `Claude`→`GPT`, `mcp__guidelines__anthropic`→`mcp__guidelines__openai`, and `response_instruction`.

But Codex has **also drifted 15 lines ahead** (`codex:50-62` adds `<tool_grounding>`, `<korean_dialogue>`, `<output_format>`) that Claude never receives. Those are provider-agnostic style rules — this looks like accidental drift, not intent.

**Fix:** one shared base template with `{vendor}` / `{model_name}` / `{policy_tool}` substitution plus a thin per-provider overlay. Move `<korean_dialogue>` and `<output_format>` into the shared base so both providers get them. Note the `<guidelines>` block is now the *only* home for guidelines text, so it must survive this refactor intact in both providers.

### 23. `schemas/message.py` hand-maps 16 fields and throws away `from_attributes` **[A]**

`schemas/message.py:41-102` uses a `@model_validator(mode="before")` to rebuild the ORM row into a dict field-by-field. **This is why `anthropic_calls` and `provider` silently went unwritten for so long** — because the mapping is manual, a new column is invisible until someone remembers to edit this function. Two already slipped through (both now fixed, but the trap remains).

**Fix:** restore `from_attributes=True`; use per-field `@field_validator(mode="before")` for the three JSON columns and `AliasPath("agent", "name")` for the flattened agent fields.

### 24. Schema/model drift **[A]**

- `schemas/agent.py:46` declares `session_id`, which **does not exist** on `models.Agent` (sessions live in `RoomAgentSession`). Every `GET /agents` ships `"session_id": null` forever.
- `models.Agent.final_response` exists in the DB and the migration but is in **no schema** — hence `crud/agents.py:48` doing `getattr(agent, "final_response", False)` against a Pydantic model that structurally cannot have it. The API can never set it.
- `RoomUpdate.is_finished` is accepted by `PATCH /rooms/{id}`, returns 200, and is **silently ignored** — `crud/rooms.py:139` only handles `name`, `max_interactions`, `is_paused`.
- `Room` and `RoomSummary` (`schemas/room.py:28-57`) repeat 10 fields character-for-character. `class Room(RoomSummary): agents: list[Agent] = []; messages: list[Message] = []` is the entire delta.
- Frontend `types/index.ts:120` — `ParticipantType` is missing `'system'` and `'agent'`, both of which the backend enum has and `MessageRow.tsx:89` branches on. It only type-checks because the field is typed `string | null`.

### 25. Repeated backend idioms **[A]**

- `owner_id = "admin" if identity.role == "admin" else identity.user_id` — copy-pasted 5× (`routers/rooms.py:41`, `routers/agents.py:67`, `routers/serve_mcp.py:123,190,225`). Make it a property on `RequestIdentity` (`core/dependencies.py:17`).
- Chatting-agent serialization duplicated verbatim in `routers/messages.py:104-121` and `routers/sse.py:151-170` — **already diverged** (SSE dropped `profile_pic`). Extract one builder.
- Agent fuzzy-name lookup written 3× in `routers/serve_mcp.py` (`:112, :182, :233`), each loading the entire agents table into memory. Add `crud.find_agent_by_name(db, name)` doing it in SQL.
- Profile-pic discovery written 3× (`routers/agent_management.py:97`, `migrations.py:364, 386`), and `_get_work_dir()`/frozen-path resolution written 4× — despite `get_settings().work_dir` already existing.

### 26. Frontend duplication **[A]**

- `hooks/usePollingData.ts:36-59` and `:70-98` are the **same fetch function twice** — and the exported `refresh` is bound to the copy *without* the `isActive` guard, so a post-unmount refresh still calls `setData`.
- `ui/modal.tsx` exists with a focus trap and Escape handling, and exactly **one** of four modals uses it. `ExportModal`, `AgentProfileModal`, `HowToDocsModal`, and an inline 40-line dialog in `ChatRoom.tsx:331` each re-implement it (the ChatRoom one with no focus trap at all).
- `usePolling.ts:113-123` and `:179-189` — byte-identical 11-line chatting-state comparison.
- `useSSE.ts:89-100` and `:126-141` — reconnect-backoff logic written twice.

### 27. Frontend render cost **[A]**

- `ChatRoom.tsx:231` builds the `chatRoomControls` context value as a bare object literal (no `useMemo`) **containing `messages`**. Every streamed token → new context identity → every consumer re-renders. `ChatHeader` is wrapped in `memo()` and that memo is completely defeated.
- `hooks/useWhiteboard.ts:29` memoizes on `[messages]`, whose identity changes on every SSE delta — so it **replays every whiteboard diff from message 0 on every token.** O(n²) per response.

---

## Suggested order of attack

1. ~~**P0** — auth holes, the dead guidelines system, and the four silent no-ops.~~ **Done 2026-07-14.**
2. **P1 §10–16** — pure deletion, ~1,500 lines, zero behavior change. Do this *before* the refactors; it makes everything below legible.
3. **P3 §21–22** — the MCP server factory and the prompt unification. Highest duplication payoff, mechanical.
4. **P2 §17–18** — pay down the import cycles one back-edge at a time. Track progress by the deferred-import count (86 → 0).
5. **P2 §20** — ORM-objects-in-cache. Largest single piece of work, and the one most likely to bite under production concurrency.
6. **Migrations** — `infrastructure/database/migrations.py` is a hand-rolled 432-line pseudo-migrator with no version table, no downgrade, and no record of what ran. Adopt Alembic **before** the next schema change, not after. **[A]**

## Also worth knowing

- **There is no `make test` or `make lint` target**, despite `pyproject.toml` defining a test task and `.pre-commit-config.yaml` defining ruff. **[A]**
- `Makefile:95` advertises port 8000 for `dev-sqlite`; the backend binds **8001**. **[A]**
- `backend/i18n/serializers.py` is not i18n — it's Pydantic datetime/bool helpers. It belongs in `schemas/`. **[A]**
- An English-locale user still gets **KST timestamps** injected into every agent prompt (`response_generator.py:130` → hardcoded `KST = UTC+9` in `i18n/timezone.py:8`). The frontend has an `en` locale; the backend has no counterpart. **[A]**
- The **Moltbook / social** subsystem (`social_server.py`, 305 lines) is unreachable — `providers/mcp_config.py` only builds `action`, `guidelines`, `etc`, and `MOLTBOOK_API_KEY` is never passed into the subprocess env. Wire it up or delete it. **[A]**
