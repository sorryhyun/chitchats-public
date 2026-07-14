# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ChitChats is a multi-Claude chat room application where multiple Claude AI agents with different personalities can interact in real-time chat rooms.

**Tech Stack:**
- Backend: FastAPI + SQLAlchemy (async) + PostgreSQL
- Frontend: React + TypeScript + Vite + Tailwind CSS
- AI Integration: Multi-provider support (Claude Agent SDK, Codex)
- Real-time Communication: Server-Sent Events (SSE), with a 5s HTTP polling fallback
- Background Processing: APScheduler for autonomous agent interactions

## Development Commands

```bash
make dev           # Run both backend and frontend
make dev-voice     # Also run the voice TTS server (port 8002)
make dev-sqlite    # Run with SQLite instead of PostgreSQL
make install       # Install all dependencies
make stop          # Stop all servers
make clean         # Clean build artifacts

# Backend only
cd backend && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8001

# Frontend only
cd frontend && npm run dev

# Backend tests
uv run pytest                                    # Run all tests
uv run pytest backend/tests/unit/test_crud.py   # Run single test file
uv run pytest -k "test_create_agent"             # Run tests matching pattern
uv run pytest --cov=backend --cov-report=term-missing  # With coverage

# Frontend tests and checks
cd frontend && npm run test                      # Run vitest
cd frontend && npm run typecheck                 # TypeScript check
cd frontend && npm run lint                      # ESLint

# Build commands
make build-exe         # Standalone Windows exe (recommended)
make build-non-tauri   # Same as build-exe
```

## Architecture Overview

### Backend
- **FastAPI** application with REST API and SSE streaming endpoints
- **App/router wiring** lives in `backend/core/app_factory.py` (`create_app()`); `backend/main.py` is a thin entry point
- **Multi-agent orchestration** with multi-provider support (Claude SDK, Codex)
- **PostgreSQL** database with async SQLAlchemy (asyncpg); SQLite fallback via `USE_SQLITE=true`
- **Background scheduler** for autonomous agent conversations (`backend/infrastructure/scheduler.py`)
- **In-memory caching** for performance optimization
- **Domain layer** with Pydantic models for type-safe business logic
- **Key features:**
  - Agents are independent entities that persist across rooms
  - Room-specific conversation sessions per agent
  - Auto-seeding agents from `agents/` directory
  - Recent events auto-update based on conversation history
  - Agents continue conversations in background when user is not in room
  - Cached database queries and filesystem reads (`backend/core/cache_service.py`, `backend/infrastructure/cache.py`)
  - Modular MCP tool servers (`backend/mcp_servers/`: action, guidelines, etc, social)

**Backend packages:** `chatroom_orchestration` (incl. `tape/`), `core`, `crud`, `domain`, `i18n`, `infrastructure` (`database/`, `logging/`), `launch` (`setup/`), `mcp_servers` (`config/`), `providers` (`claude/`, `codex/`), `routers`, `schemas`.

**Routers** (mounted in `app_factory.py`): `auth`, `rooms`, `agent_management`, `agents`, `room_agents`, `messages`, `sse`, `debug`, `providers`, `exports`, `voice`, `user`, `tools_api`, `serve_mcp`.

**For detailed backend documentation**, see [backend/README.md](backend/README.md) which includes:
- Complete API reference
- Database schema details
- Agent configuration system
- Chat orchestration logic
- Session management
- Debugging guides

### Frontend
- **React + TypeScript + Vite** with Tailwind CSS
- **Key components:**
  - MainSidebar - Room list and agent management (`components/sidebar/`)
  - ChatRoom - Main chat interface (`components/chat-room/`)
  - AgentManager - Add/remove agents from rooms
  - MessageList - Display messages with thinking text
- **Real-time features:**
  - SSE for live message/token streaming (`frontend/src/hooks/useSSE.ts`, backed by `backend/routers/sse.py`)
  - `usePolling.ts` wraps `useSSE` and adds a 5s polling fallback when SSE is not connected
  - Typing indicators
  - Agent thinking process display

### Voice (TTS)
- Optional TTS server in `voice_server/` (Qwen3-TTS), run with `make run-voice` or `make dev-voice` (port 8002)
- Backend proxies it via `backend/routers/voice.py` (`/voice/status`, `/voice/generate`, `/voice/audio/{message_id}`)
- Configure the server location with `VOICE_SERVER_URL` (default `http://localhost:8002`)

### Exports
- `backend/routers/exports.py` exposes Claude Code conversation files (`~/.claude/projects/*.jsonl`) at `/exports/conversations` (admin only)
- Frontend UI: `frontend/src/components/sidebar/ExportModal.tsx`

### AI Providers

ChitChats supports multiple AI providers through a unified abstraction layer:

| Provider | Description | Authentication |
|----------|-------------|----------------|
| `claude` | Claude Agent SDK (default) | Via Claude Code subscription |
| `codex` | Codex (app-server or MCP mode) | Via `codex login` |

**Provider Selection:**
- Rooms are created with a default provider (`claude` if not specified)
- Provider is set at room creation time via the `default_provider` field
- All agents in a room use the same provider

Provider implementations are in `backend/providers/`.

## Agent Configuration

Agents are configured with a folder per agent (`in_a_nutshell.md` and `characteristics.md` are required):

```
agents/
  agent_name/
    ├── in_a_nutshell.md      # Brief identity summary (third-person) — required
    ├── characteristics.md     # Personality traits (third-person) — required
    ├── recent_events.md      # Auto-updated from ChitChats platform conversations ONLY (not for anime/story backstory)
    ├── consolidated_memory.md # Long-term memories with subtitles (optional)
    ├── profile.png           # Optional profile picture (png, jpg, jpeg, gif, webp, svg)
    └── voice.wav             # Optional TTS voice sample (wav, mp3, flac, ogg)
```

**IMPORTANT:** Agent configuration files must use **third-person perspective**:
- ✅ Correct: "Dr. Chen is a seasoned data scientist..." or "프리렌은 엘프 마법사로..."
- ❌ Wrong: "You are Dr. Chen..." or "당신은 엘프 마법사로..."

**Profile Pictures:** Add image files (png/jpg/jpeg/gif/webp/svg) to agent folders. Common names: `profile.*`, `avatar.*`, `picture.*`, `photo.*`.

### Filesystem-Primary Architecture

**Agent configs**, **system prompt**, and **tool configurations** use filesystem as single source of truth:
- Agent configs: `agents/{name}/*.md` files (DB is cache only)
- Agent parsing: `backend/domain/agent_parser.py` (folder-based only)
- System prompt: `backend/providers/prompts_base.yaml` holds the shared body (`active_system_prompt` selects the version); `backend/providers/{claude,codex}/prompts.yaml` hold only each provider's `overlay` (vendor wording, policy tool, provider-only sections) and `conversation_context`. Room-level shared sections live in `backend/mcp_servers/config/prompts_shared.yaml`
- Tool configurations: `backend/mcp_servers/config/` directory
- File locking prevents concurrent write conflicts
- See `backend/infrastructure/locking.py` for implementation

### Tool Configuration

Tool descriptions and debug settings are configured in `backend/mcp_servers/config/`:

**`tools.py`** - Tool definitions and descriptions (Python-based)
- Defines available tools: `skip`, `memorize`, `recall`, `excuse` (action server); `anthropic`/`openai` (guidelines server); `current_time` (etc server); `moltbook` (social server)
- Tool descriptions support template variables (`{agent_name}`, `{memory_subtitles}`)
- Each `ToolDef` has an `enabled` flag; some are off by default

**Guidelines** are not a tool and not a separate config file. They ship inside the `<guidelines>` block of the active system prompt in `backend/providers/prompts_base.yaml`, and use third-person perspective (see [docs/how_it_works.md](docs/how_it_works.md) for why).

**`debug.yaml`** - Debug logging configuration
- Control what gets logged (system prompt, tools, messages, responses)
- Can be overridden by `DEBUG_AGENTS` environment variable

### Group Configuration

Groups (`group_*` folders) can have a `group_config.yaml` for shared settings:
- **Tool overrides** - Custom tool responses/descriptions for all agents in the group (any field from `tools.py`, e.g. `tools.recall.response`)
- **Behavior settings:**
  - `interrupt_every_turn` - When `true`, agents in this group get a turn after any message
  - `priority` - Integer (default `0`). Higher values respond before lower priority agents
  - `transparent` - When `true`, this agent's messages don't trigger others to reply (useful for Narrator-type agents). Messages are still visible to all agents.

Ordering logic lives in `backend/chatroom_orchestration/agent_ordering.py` and `backend/chatroom_orchestration/tape/`.

See `agents/group_config.yaml.example` for examples.

## Quick Start

```bash
make install                                      # Install all dependencies
cp .env.example .env                              # Configure environment
make generate-hash                                # Generate password hash for .env
make dev                                          # Run backend + frontend
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8001
- API Docs: http://localhost:8001/docs

See [docs/SETUP.md](docs/SETUP.md) for PostgreSQL setup and authentication configuration.

## Configuration

### Backend Environment Variables (`.env`)

**Required:**
- `DATABASE_URL` - PostgreSQL connection string (default: `postgresql+asyncpg://postgres:postgres@localhost:5432/chitchats`)
- `API_KEY_HASH` - Bcrypt hash of your password (generate with `make generate-hash`)
- `JWT_SECRET` - Secret key for signing JWT tokens (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)

All settings are declared in `backend/core/settings.py` (Pydantic `BaseSettings`); anything not listed there is ignored.

**Optional:**
- `USER_NAME` - Display name for user messages in chat (default: "User")
- `DEBUG_AGENTS` - Set to "true" for verbose agent logging
- `USE_SONNET` - Set to "true" to default to Sonnet instead of Opus (default: false). Can also be toggled at runtime via Settings UI. Accepts `USE_HAIKU` as alias for backward compatibility.
- `MAX_CONCURRENT_ROOMS` - Max rooms for background scheduler (default: 5)
- `GUEST_PASSWORD_HASH` - Separate bcrypt hash for guest (read-only) login
- `ENABLE_GUEST_LOGIN` - Enable/disable guest login (default: true)
- `USE_SQLITE` - Set to "true" to use SQLite instead of PostgreSQL (also used by `make dev-sqlite`)
- `VOICE_SERVER_URL` - Voice TTS server URL (default: `http://localhost:8002`)
- `CODEX_MODEL` - Model used by the Codex provider (default: `gpt-5.5`)
- `ENABLE_COMMUNITY` / `MOLTBOOK_API_KEY` - Enable the Moltbook social tools (default: disabled)
- `FRONTEND_URL` - CORS allowed origin for production (e.g., `https://your-app.vercel.app`)
- `VERCEL_URL` - Auto-detected on Vercel deployments

**AI Provider Authentication:**
- **Claude SDK:** Authentication handled automatically via Claude Code subscription (no API key needed)
- **Codex:** Authenticate with `codex login` before starting the backend

### Database (PostgreSQL)
- **Connection:** Configure via `DATABASE_URL` environment variable
- **Format:** `postgresql+asyncpg://user:password@host:port/database`
- **Default:** `postgresql+asyncpg://postgres:postgres@localhost:5432/chitchats`
- **Migrations:** Automatic schema updates via `backend/infrastructure/database/migrations.py`
- **Setup:** Create database with `createdb chitchats` before first run

### CORS Configuration
- CORS is configured in `backend/core/app_factory.py` from `Settings.get_cors_origins()`
- Default allowed origins: `localhost:5173`, `localhost:5174`, and local network IPs
- Add custom origins via `FRONTEND_URL` or `VERCEL_URL` environment variables
- Backend logs CORS configuration on startup for visibility

## Common Tasks

**Create agent:** Add folder in `agents/` with required `.md` files using third-person perspective (e.g., "Alice is..." not "You are..."), restart backend

**Update agent:** Edit `.md` files directly

**Update system prompt:** Edit the active `system_prompt_*` block in `backend/providers/prompts_base.yaml` (applies to both providers). For provider-only wording, edit the `overlay` in `backend/providers/{claude,codex}/prompts.yaml`

**Update tool descriptions:** Edit `backend/mcp_servers/config/tools.py`

**Update guidelines:** Edit the `<guidelines>` block inside the active `system_prompt_*` in `backend/providers/prompts_base.yaml`

**Enable debug logging:** Set `DEBUG_AGENTS=true` in `.env` or edit `backend/mcp_servers/config/debug.yaml`

**Add database field:** Update `backend/infrastructure/database/models.py`, add migration in `backend/infrastructure/database/migrations.py`, update `backend/schemas/` and `backend/crud/`, restart

**Add endpoint:** Define schema in `backend/schemas/`, add CRUD in `backend/crud/`, add the route to an existing router in `backend/routers/` (or create a new one and register it with `app.include_router(...)` in `backend/core/app_factory.py`)

## Automated Simulations

ChitChats includes bash scripts for running automated multi-agent chatroom simulations via curl API calls. This is useful for testing agent behaviors, creating conversation datasets, or running batch simulations.

**Quick Example:**
```bash
make simulate ARGS='--password "your_password" --scenario "Discuss the ethics of AI development" --agents "alice,bob,charlie"'
```

Or use the script directly:
```bash
./scripts/simulation/simulate_chatroom.sh \
  --password "your_password" \
  --scenario "Discuss the ethics of AI development" \
  --agents "alice,bob,charlie"
```

**Output:** Generates `chatroom_1.txt`, `chatroom_2.txt`, etc. with formatted conversation transcripts.

**Features:**
- Authenticates and creates rooms via API
- Sends scenarios as `situation_builder` participant type
- Polls for messages and saves formatted transcripts
- Auto-detects conversation completion
- Supports custom room names, max interactions, and output files

**Scripts Location:** `scripts/simulation/` and `scripts/testing/`

Run `./scripts/simulation/simulate_chatroom.sh --help` for the full option list.
