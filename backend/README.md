# Backend Documentation

FastAPI + SQLAlchemy (async) + PostgreSQL backend for multi-agent chat orchestration.

## Quick Start

```bash
make install && make dev    # From project root

# Backend only
cd backend && uv run uvicorn main:app --host 0.0.0.0 --port 8001

# Tests
uv run pytest --cov=backend
```

## Directory Structure

```
backend/
├── main.py                 # Entry point (delegates to core/app_factory.py)
├── schemas/                # Pydantic request/response models
├── core/                   # App factory, auth, settings, AgentManager, ClientPool, services
│   ├── app_factory.py      # create_app(): middleware, router wiring, lifespan
│   ├── auth.py             # JWT auth, AuthMiddleware, SSE tickets
│   └── settings.py         # Env-backed settings (pydantic-settings)
├── crud/                   # Database operations
├── domain/                 # Domain models (AgentConfigData, agent_parser)
│   └── agent_parser.py     # Agent config parsing from filesystem
├── mcp_servers/            # MCP server tools and config
│   └── config/
│       ├── tools.py        # Python tool registry (ToolDef, input models)
│       ├── prompts_shared.yaml # Shared templates (situation_builder, ...)
│       ├── debug.yaml      # Debug logging configuration
│       └── loaders.py      # Config file loaders
├── chatroom_orchestration/ # Multi-agent conversation orchestration
│   └── tape/               # Scripted turn sequences (generator, executor)
├── providers/              # AI provider abstraction (Claude, Codex)
│   ├── prompt_builder.py   # System prompt assembly
│   ├── claude/             # Claude Agent SDK provider (+ prompts.yaml)
│   └── codex/              # Codex MCP provider (+ prompts.yaml)
│       ├── parser.py       # Stream parser
│       └── constants.py    # Event / item types
├── routers/                # REST + SSE API endpoints
├── infrastructure/         # Database, caching, scheduler, locking, logging
│   ├── cache.py            # In-memory TTL cache (CacheManager)
│   ├── yaml_cache.py       # mtime-based YAML config cache
│   └── database/           # models.py, connection.py, migrations.py, write_queue.py
├── launch/                 # Bundled/desktop launcher (setup/)
├── i18n/                   # Translations
└── tests/                  # Test suite
```

Routers are wired in `core/app_factory.py` (`include_router` calls) — there is no monolithic `main.py`.

## API Endpoints

| Group | Endpoints |
|-------|-----------|
| Auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/verify`, `GET /auth/health`, `GET /auth/health/pool` |
| Rooms | `GET/POST /rooms`, `GET/PATCH/DELETE /rooms/{id}`, `POST /rooms/{id}/pause\|resume\|mark-read`, `DELETE /rooms/{id}/messages` |
| Agents | `GET/POST /agents`, `GET/DELETE /agents/{id}`, `PATCH /agents/{id}`, `POST /agents/{id}/reload`, `GET /agents/{id}/direct-room`, `GET /agents/configs`, `GET /agents/{name}/profile-pic` |
| Room-Agents | `GET /rooms/{room_id}/agents`, `POST/DELETE /rooms/{room_id}/agents/{agent_id}` |
| Messages | `GET /rooms/{room_id}/messages`, `POST /rooms/{room_id}/messages/send`, `GET /rooms/{room_id}/messages/poll`, `GET /rooms/{room_id}/chatting-agents`, `GET /rooms/{room_id}/critic-messages` |
| SSE | `POST /rooms/{room_id}/sse-ticket`, `GET /rooms/{room_id}/stream` |
| Providers / Tools | `GET /providers`, `GET /tools` |
| Voice | `GET /voice/status`, `POST /voice/generate`, `GET /voice/audio/{message_id}`, `GET /voice/exists/{message_id}` |
| Exports | `GET /exports/conversations`, `GET /exports/conversations/{project}/{conversation_id}` |
| Debug | `GET /debug/cache/stats`, `POST /debug/cache/cleanup`, `POST /debug/cache/clear` |
| MCP Tools | `GET /mcp-tools/agents`, `POST /mcp-tools/chat`, `GET /mcp-tools/conversation/{agent_name}`, `POST /mcp-tools/room`, `POST /mcp-tools/room/message` |

Auth: all endpoints require the `X-API-Key` header (JWT token) except `/`, `/auth/login`, `/auth/health`, `/docs`, `/openapi.json`, `/redoc`, and the `/mcp`, `/assets`, `/.well-known`, `/generated_images` prefixes. Admin-only routes additionally reject guest tokens.

## Real-Time Updates

Live message/typing/thinking updates use **Server-Sent Events** as the primary transport:

1. Client `POST /rooms/{room_id}/sse-ticket` with its JWT → short-lived (60s) room-scoped ticket.
2. Client opens `GET /rooms/{room_id}/stream?ticket=...` (EventSource can't send headers, hence the ticket).
3. `core/sse.py` broadcasts room events to connected clients.

HTTP polling remains as a **fallback** when SSE isn't connected: the frontend polls
`GET /rooms/{room_id}/messages/poll` and `GET /rooms/{room_id}/chatting-agents` every 5s
(`frontend/src/hooks/usePolling.ts`).

## Environment Variables

**Required:**
- `DATABASE_URL` - PostgreSQL connection (default: `postgresql+asyncpg://postgres:postgres@localhost:5432/chitchats`)
- `API_KEY_HASH` - Bcrypt hash of admin password
- `JWT_SECRET` - Secret for JWT signing

**Optional:**
- `USER_NAME` - Display name for user messages (default: `User`)
- `DEBUG_AGENTS=true` - Verbose agent logging
- `USE_SONNET=true` - Default to Sonnet instead of Opus (also toggleable via Settings UI; `USE_HAIKU` accepted as alias)
- `ENABLE_GUEST_LOGIN` / `GUEST_PASSWORD_HASH` - Guest login
- `PRIORITY_AGENTS` - Comma-separated agent names that respond first
- `MAX_CONCURRENT_ROOMS` - Background scheduler limit (default: 5)
- `CODEX_MODEL` - Model for the Codex provider (default: `gpt-5.5`)
- `VOICE_SERVER_URL` - Voice TTS server (default: `http://localhost:8002`)
- `FRONTEND_URL` / `VERCEL_URL` - Extra CORS allowed origins

See [../docs/SETUP.md](../docs/SETUP.md) for full configuration.

## Tool Configuration

Tools are defined in Python (`mcp_servers/config/tools.py`) with a `ToolDef` dataclass:

```python
@dataclass
class ToolDef:
    name: str           # Full MCP name (e.g., "mcp__action__skip")
    group: str          # Tool group ("action", "guidelines", "etc", "social")
    description: str    # Template with {agent_name}, {memory_subtitles}
    response: str       # Response template
    input_model: type[BaseModel]  # Pydantic input schema
    enabled: bool = True
    providers: list[str] | None = None  # None = all providers
    requires: list[str] = field(default_factory=list)
```

**Available tools:**
- `skip` - Skip turn when agent shouldn't respond
- `memorize` - Record significant events
- `recall` - Retrieve long-term memories by subtitle (`consolidated_memory.md`)
- `excuse` - Record the agent's raw inner reaction before responding
- `anthropic`/`openai` - Policy compliance check (provider-specific)
- `current_time` - Current time
- `moltbook` - Community/social tools (requires `ENABLE_COMMUNITY`)

**Guidelines** are not a tool. They are part of the system prompt, in the `<guidelines>` block of each provider's `prompts.yaml`.

## System Prompt

System prompts and behavioral guidelines live with each provider:

- `providers/claude/prompts.yaml` - Prompt for Claude
- `providers/codex/prompts.yaml` - Prompt for Codex/GPT

Each file selects its active prompt via the `active_system_prompt` key and is assembled by `providers/prompt_builder.py`, which injects the agent's parsed config sections (`in_a_nutshell`, `characteristics`, `recent_events`).

## Key Concepts

- **Filesystem-Primary:** Agent configs loaded from `agents/` directory, DB is cache
- **Third-Person Configs:** Agent files use third-person ("프리렌은..."), system prompt uses `{agent_name}` placeholders
- **Session Isolation:** Each agent has a separate provider session per room (`room_agent_sessions` table stores `claude_session_id` / `codex_thread_id`)
- **Memory System:** Short-term (`recent_events.md`) + long-term (`consolidated_memory.md`)
- **Provider Abstraction:** Unified interface for Claude SDK and Codex

## Database

PostgreSQL via async SQLAlchemy (asyncpg). Models in `infrastructure/database/models.py`:

| Table | Purpose |
|-------|---------|
| `rooms` | Room state (`is_paused`, `is_finished`, `max_interactions`, `default_provider`, `default_model`) |
| `agents` | Agent identity + cached config sections and behavior flags (`is_critic`, `priority`, `transparent`, ...) |
| `messages` | Chat messages (`role`, `participant_type`, `thinking`, `images`, `provider`) |
| `room_agents` | Room↔agent membership (association table) |
| `room_agent_sessions` | Per-room provider session IDs |
| `voice_audio` | Generated TTS audio per message |

Schema updates run automatically on startup via `infrastructure/database/migrations.py` (`run_migrations`).
Create the database once with `createdb chitchats` before the first run. A SQLite fallback exists
(`backend/database.py`, `make dev-sqlite` / `USE_SQLITE=true`, auto-selected on Windows).

## Caching

`infrastructure/cache.py` provides a thread-safe in-memory `CacheManager` with TTL expiry and manual
invalidation, used for hot DB reads (agent/room objects, room agents, room messages, chatting agents).
`infrastructure/yaml_cache.py` caches YAML config files, reloading only when their mtime changes.

Inspect or reset caches at runtime with the debug endpoints: `GET /debug/cache/stats`,
`POST /debug/cache/cleanup`, `POST /debug/cache/clear`.

## Providers

| Provider | Description | Parser |
|----------|-------------|--------|
| `claude` | Claude Agent SDK | `providers/claude/parser.py` |
| `codex` | Codex MCP | `providers/codex/parser.py` |

## Debugging

Enable with `DEBUG_AGENTS=true` in `.env` or edit `mcp_servers/config/debug.yaml`.
