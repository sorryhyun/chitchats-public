# Backend Documentation

FastAPI + SQLAlchemy (async) + PostgreSQL backend for multi-agent chat orchestration.

## Quick Start

```bash
make install  # Install dependencies
make dev      # Run backend + frontend

# Backend only
cd backend && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

See [../SETUP.md](../SETUP.md) for authentication setup.

## Directory Structure

```
backend/
├── main.py                  # Entry point
├── core/                    # App core + agent infrastructure
│   ├── manager.py           # AgentManager
│   ├── client_pool.py       # Client lifecycle
│   ├── config/              # YAML config loading
│   └── memory/              # Memory parsing
├── config/tools/            # YAML configuration files
├── crud/                    # Database operations
├── domain/                  # Domain models
├── orchestration/           # Multi-agent conversation logic
├── routers/                 # REST API endpoints
├── providers/               # AI provider implementations
│   ├── claude/              # Claude SDK provider
│   └── codex/               # Codex CLI provider
├── mcp_servers/             # Standalone MCP servers
├── services/                # Business logic
├── infrastructure/          # Utilities (scheduler, cache, db)
└── tests/                   # Test suite
```

## Key Concepts

- **Filesystem-primary**: Agent configs loaded from `agents/` directory, DB is cache
- **Hot-reloading**: Config changes apply immediately
- **Multi-provider**: Supports Claude and Codex backends
- **Session isolation**: Each agent has separate session per room

## Configuration

**Environment variables** (`.env`):

| Variable | Required | Description |
|----------|----------|-------------|
| `API_KEY_HASH` | Yes | Bcrypt hash of admin password (`make generate-hash`) |
| `JWT_SECRET` | Yes | JWT signing secret |
| `DATABASE_URL` | No | PostgreSQL connection (default: `postgresql+asyncpg://postgres:postgres@localhost:5432/chitchats`) |
| `USER_NAME` | No | Display name for user messages (default: "User") |
| `DEBUG_AGENTS` | No | Enable verbose agent logging |
| `USE_HAIKU` | No | Use Haiku model instead of Opus |
| `PRIORITY_AGENTS` | No | Comma-separated agent names for priority responding |
| `MAX_CONCURRENT_ROOMS` | No | Max rooms for background scheduler (default: 5) |
| `ENABLE_GUEST_LOGIN` | No | Enable/disable guest login (default: true) |
| `FRONTEND_URL` | No | CORS allowed origin for production |

See [../SETUP.md](../SETUP.md) for authentication setup.

## Development

**Add DB field**: Update `infrastructure/database/models.py` + add migration

**Add endpoint**: Define schema → add CRUD → create router

**Update system prompt**: Edit `config/tools/guidelines_3rd.yaml`

## Caching

See [CACHING.md](CACHING.md) for in-memory caching details.
