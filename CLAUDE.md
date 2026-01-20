# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ChitChats is a multi-Claude chat room application where multiple Claude AI agents with different personalities can interact in real-time chat rooms.

**Tech Stack:**
- Backend: FastAPI + SQLAlchemy (async) + PostgreSQL
- Frontend: React + TypeScript + Vite + Tailwind CSS
- AI Integration: Multi-provider support (Claude Agent SDK, Codex MCP)
- Real-time Communication: HTTP Polling (2-second intervals)
- Background Processing: APScheduler for autonomous agent interactions

## Development Commands

```bash
make dev           # Run both backend and frontend
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

# Archived (not recommended for Windows)
make build-tauri-archived  # Tauri desktop app (see scripts/archive/)
```

## Architecture Overview

### Backend
- **FastAPI** application with REST API and polling endpoints
- **Multi-agent orchestration** with multi-provider support (Claude SDK, Codex MCP)
- **PostgreSQL** database with async SQLAlchemy (asyncpg)
- **Background scheduler** for autonomous agent conversations
- **In-memory caching** for performance optimization
- **Domain layer** with Pydantic models for type-safe business logic
- **Key features:**
  - Agents are independent entities that persist across rooms
  - Room-specific conversation sessions per agent
  - Auto-seeding agents from `agents/` directory
  - Recent events auto-update based on conversation history
  - Agents continue conversations in background when user is not in room
  - Cached database queries and filesystem reads (70-90% performance improvement)
  - Modular tool architecture (action_tools, guidelines_tools, brain_tools)

**For detailed backend documentation**, see [backend/README.md](backend/README.md) which includes:
- Complete API reference
- Database schema details
- Agent configuration system
- Chat orchestration logic
- Session management
- Phase 5 refactored SDK integration (AgentManager, ClientPool, StreamParser)
- Debugging guides

**For caching system details**, see [backend/CACHING.md](backend/CACHING.md).

### Frontend
- **React + TypeScript + Vite** with Tailwind CSS
- **Key components:**
  - MainSidebar - Room list and agent management
  - ChatRoom - Main chat interface with polling integration
  - AgentManager - Add/remove agents from rooms
  - MessageList - Display messages with thinking text
- **Real-time features:**
  - HTTP polling for live message updates (2-second intervals)
  - Typing indicators
  - Agent thinking process display

### AI Providers

ChitChats supports multiple AI providers through a unified abstraction layer:

| Provider | Description | Authentication |
|----------|-------------|----------------|
| `claude` | Claude Agent SDK (default) | Via Claude Code subscription |
| `codex` | Codex MCP Server | Via `codex login` |

**Provider Selection:**
- Rooms are created with a default provider (`claude` if not specified)
- Provider is set at room creation time via the `provider` field
- All agents in a room use the same provider

Provider implementations are in `backend/providers/`.

## Agent Configuration

Agents can be configured using folder-based structure (new) or single file (legacy):

**New Format (Preferred):**
```
agents/
  agent_name/
    ├── in_a_nutshell.md      # Brief identity summary (third-person)
    ├── characteristics.md     # Personality traits (third-person)
    ├── recent_events.md      # Auto-updated from ChitChats platform conversations ONLY (not for anime/story backstory)
    ├── consolidated_memory.md # Long-term memories with subtitles (optional)
    └── profile.png           # Optional profile picture (png, jpg, jpeg, gif, webp, svg)
```

**IMPORTANT:** Agent configuration files must use **third-person perspective**:
- ✅ Correct: "Dr. Chen is a seasoned data scientist..." or "프리렌은 엘프 마법사로..."
- ❌ Wrong: "You are Dr. Chen..." or "당신은 엘프 마법사로..."

**Profile Pictures:** Add image files (png/jpg/jpeg/gif/webp/svg) to agent folders. Common names: `profile.*`, `avatar.*`, `picture.*`, `photo.*`.

### Filesystem-Primary Architecture

**Agent configs**, **system prompt**, and **tool configurations** use filesystem as single source of truth:
- Agent configs: `agents/{name}/*.md` files (DB is cache only)
- System prompt: `backend/config/tools/guidelines_3rd.yaml` (`system_prompt` field)
- Tool configurations: `backend/config/tools/*.yaml` files
- File locking prevents concurrent write conflicts
- See `backend/infrastructure/locking.py` for implementation

### Tool Configuration (YAML-Based)

Tool descriptions and debug settings are configured via YAML files in `backend/config/tools/`:

**`tools.yaml`** - Tool definitions and descriptions
- Defines available tools (skip, memorize, guidelines, configuration)
- Tool descriptions support template variables (`{agent_name}`, `{config_sections}`)
- Enable/disable tools individually

### Group Configuration

Groups (`group_*` folders) can have a `group_config.yaml` for shared settings:
- **Tool overrides** - Custom tool responses/descriptions for all agents in the group
- **Behavior settings** - `interrupt_every_turn`, `priority`, `transparent`

See `agents/group_config.yaml.example` for examples.

**`guidelines_3rd.yaml`** - Role guidelines for agent behavior
- Defines system prompt template and behavioral guidelines
- Uses third-person perspective (see [docs/how_it_works.md](docs/how_it_works.md) for why)

**`debug.yaml`** - Debug logging configuration
- Control what gets logged (system prompt, tools, messages, responses)
- Can be overridden by `DEBUG_AGENTS` environment variable

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

See [SETUP.md](SETUP.md) for PostgreSQL setup and authentication configuration.

## Configuration

### Backend Environment Variables (`.env`)

**Required:**
- `DATABASE_URL` - PostgreSQL connection string (default: `postgresql+asyncpg://postgres:postgres@localhost:5432/chitchats`)
- `API_KEY_HASH` - Bcrypt hash of your password (generate with `make generate-hash`)
- `JWT_SECRET` - Secret key for signing JWT tokens (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)

**Optional:**
- `USER_NAME` - Display name for user messages in chat (default: "User")
- `DEBUG_AGENTS` - Set to "true" for verbose agent logging
- `RECALL_MEMORY_FILE` - Memory file for recall mode: `consolidated_memory` (default) or `long_term_memory`
- `USE_HAIKU` - Set to "true" to use Haiku model instead of Opus (default: false)
- `PRIORITY_AGENTS` - Comma-separated agent names for priority responding
- `MAX_CONCURRENT_ROOMS` - Max rooms for background scheduler (default: 5)
- `ENABLE_GUEST_LOGIN` - Enable/disable guest login (default: true)
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
- CORS is configured in `main.py` using environment variables
- Default allowed origins: `localhost:5173`, `localhost:5174`, and local network IPs
- Add custom origins via `FRONTEND_URL` or `VERCEL_URL` environment variables
- Backend logs CORS configuration on startup for visibility

## Common Tasks

**Create agent:** Add folder in `agents/` with required `.md` files using third-person perspective (e.g., "Alice is..." not "You are..."), restart backend

**Update agent:** Edit `.md` files directly

**Update system prompt:** Edit `system_prompt` section in `backend/config/tools/guidelines_3rd.yaml`

**Update tool descriptions:** Edit YAML files in `backend/config/tools/`

**Update guidelines:** Edit `v1/v2/v3.template` section in `backend/config/tools/guidelines_3rd.yaml`

**Enable debug logging:** Set `DEBUG_AGENTS=true` in `.env` or edit `backend/config/tools/debug.yaml`

**Add database field:** Update `models.py`, add migration in `backend/infrastructure/database/migrations.py`, update `schemas.py` and `crud.py`, restart

**Add endpoint:** Define schema in `schemas.py`, add CRUD in `crud.py`, add endpoint in `main.py`

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

**See [SIMULATIONS.md](SIMULATIONS.md) for complete guide.**
