# Backend Documentation

FastAPI + SQLAlchemy (async) + PostgreSQL backend for multi-agent chat orchestration.

## Quick Start

```bash
make install && make dev    # From project root

# Backend only
cd backend && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8001

# Tests
uv run pytest --cov=backend
```

## Directory Structure

```
backend/
├── main.py                 # FastAPI entry point
├── schemas.py              # Pydantic models
├── config/                 # YAML configs (tools.yaml, guidelines_3rd.yaml, debug.yaml)
├── core/                   # App factory, auth, settings, AgentManager
├── crud/                   # Database operations
├── domain/                 # Domain models (TaskIdentifier, AgentConfigData)
├── mcp_servers/            # MCP server tools and config
├── orchestration/          # Multi-agent conversation orchestration
├── providers/              # AI provider abstraction (Claude, Codex)
├── routers/                # REST API endpoints
├── infrastructure/         # Database, caching, logging utilities
└── tests/                  # Test suite
```

## API Endpoints

| Group | Endpoints |
|-------|-----------|
| Auth | `POST /auth/login`, `GET /auth/verify`, `GET /health` |
| Rooms | `GET/POST /rooms`, `GET/PATCH/DELETE /rooms/{id}`, `POST /rooms/{id}/pause\|resume` |
| Agents | `GET/POST /agents`, `GET/PATCH/DELETE /agents/{id}`, `POST /agents/{id}/reload` |
| Room-Agents | `GET/POST/DELETE /rooms/{room_id}/agents/{agent_id}` |
| Messages | `GET/POST /rooms/{room_id}/messages`, `GET /rooms/{room_id}/messages/poll` |

All endpoints except `/auth/*`, `/health`, `/docs` require `X-API-Key` header.

## Environment Variables

**Required:**
- `DATABASE_URL` - PostgreSQL connection (default: `postgresql+asyncpg://postgres:postgres@localhost:5432/chitchats`)
- `API_KEY_HASH` - Bcrypt hash of admin password
- `JWT_SECRET` - Secret for JWT signing

**Optional:**
- `DEBUG_AGENTS=true` - Verbose agent logging
- `USE_HAIKU=true` - Use Haiku instead of Opus
- `FRONTEND_URL` - CORS allowed origin

See [../SETUP.md](../SETUP.md) for full configuration.

## Key Concepts

- **Filesystem-Primary:** Agent configs loaded from `agents/` directory, DB is cache
- **Third-Person Configs:** Agent files use third-person ("프리렌은..."), system prompt uses `{agent_name}` placeholders
- **Session Isolation:** Each agent has separate SDK session per room
- **Memory System:** Short-term (`recent_events.md`) + long-term (`consolidated_memory.md`)

## Debugging

Enable with `DEBUG_AGENTS=true` in `.env` or edit `config/tools/debug.yaml`.

For caching details, see [CACHING.md](CACHING.md).
