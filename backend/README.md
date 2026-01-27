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
├── main.py                 # FastAPI entry point
├── schemas/                # Pydantic request/response models
├── core/                   # App factory, auth, settings, AgentManager
├── crud/                   # Database operations
├── domain/                 # Domain models (AgentConfigData, agent_parser)
│   └── agent_parser.py     # Agent config parsing from filesystem
├── mcp_servers/            # MCP server tools and config
│   └── config/
│       ├── tools.py        # Python tool registry (ToolDef, input models)
│       ├── guidelines.yaml # System prompt & behavioral guidelines
│       ├── debug.yaml      # Debug logging configuration
│       └── loaders.py      # Config file loaders
├── orchestration/          # Multi-agent conversation orchestration
├── providers/              # AI provider abstraction (Claude, Codex)
│   ├── claude/             # Claude SDK provider
│   └── codex/              # Codex MCP provider
│       ├── events.py       # Event types and factory functions
│       └── parser.py       # Simplified stream parser
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

## Tool Configuration

Tools are defined in Python (`mcp_servers/config/tools.py`) with a `ToolDef` dataclass:

```python
@dataclass
class ToolDef:
    name: str           # Full MCP name (e.g., "mcp__action__skip")
    group: str          # Tool group ("action", "guidelines", "etc")
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
- `recall` - Retrieve long-term memories by subtitle
- `anthropic`/`openai` - Policy compliance check (provider-specific)

**Guidelines** are loaded from `mcp_servers/config/guidelines.yaml` with separate Claude and Codex variants.

## System Prompt

System prompts are defined in `mcp_servers/config/guidelines.yaml` with provider variants:

- `system_prompt.claude` - Concise structured prompt for Claude
- `system_prompt.codex` - Frame-based prompt for Codex/GPT

Change active prompt via `active_system_prompt` key.

## Key Concepts

- **Filesystem-Primary:** Agent configs loaded from `agents/` directory, DB is cache
- **Third-Person Configs:** Agent files use third-person ("프리렌은..."), system prompt uses `{agent_name}` placeholders
- **Session Isolation:** Each agent has separate SDK session per room
- **Memory System:** Short-term (`recent_events.md`) + long-term (`consolidated_memory.md`)
- **Provider Abstraction:** Unified interface for Claude SDK and Codex MCP

## Providers

| Provider | Description | Parser |
|----------|-------------|--------|
| `claude` | Claude Agent SDK | `providers/claude/parser.py` |
| `codex` | Codex MCP Server | `providers/codex/parser.py` (simplified) |

The Codex parser uses clean event types from `providers/codex/events.py`:
- `EventType`: `THREAD_STARTED`, `ITEM_COMPLETED`, `ERROR`
- `ItemType`: `AGENT_MESSAGE`, `REASONING`, `MCP_TOOL_CALL`

## Debugging

Enable with `DEBUG_AGENTS=true` in `.env` or edit `mcp_servers/config/debug.yaml`.

For caching details, see [CACHING.md](CACHING.md).
