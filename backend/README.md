# Backend Documentation

ChitChats backend: FastAPI application with SQLAlchemy (async) + PostgreSQL for multi-agent chat orchestration using the Anthropic Claude Agent SDK.

## Quick Start

```bash
# From project root
make install  # Install dependencies with uv
make dev      # Run both backend and frontend

# Backend only
cd backend && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run tests
uv run pytest --cov=backend --cov-report=term-missing
```

See [../SETUP.md](../SETUP.md) for authentication setup.

## Architecture Overview

**Core Stack:**
- FastAPI + SQLAlchemy (async) + PostgreSQL (asyncpg)
- Claude Agent SDK for AI interactions
- APScheduler for background autonomous conversations
- HTTP polling for real-time updates

**Key Features:**
- Filesystem-primary configuration with hot-reloading
- Multi-agent orchestration with interruption support
- Room-specific conversation sessions per agent
- In-memory caching (70-90% performance improvement)

**For caching details**, see [CACHING.md](CACHING.md).

## Directory Structure

```
backend/
├── main.py                        # FastAPI application entry point
├── database.py                    # SQLAlchemy async setup (PostgreSQL)
├── models.py                      # ORM models
├── crud.py                        # Database operations
├── schemas.py                     # Pydantic models
├── auth.py                        # JWT authentication
├── dependencies.py                # Dependency injection
├── background_scheduler.py        # APScheduler for autonomous chats
├── config/                        # Configuration system
│   ├── config_loader.py          # YAML hot-reloading with file locking
│   ├── parser.py                 # Agent config parser
│   └── tools/                    # YAML configuration files
│       ├── tools.yaml            # Tool definitions
│       ├── guidelines_3rd.yaml   # System prompt template (current)
│       ├── guidelines_v2.yaml    # Legacy v2 guidelines
│       ├── conversation_context.yaml # Conversation context template
│       └── debug.yaml            # Debug logging config
├── domain/                        # Domain models
│   ├── task_identifier.py        # TaskIdentifier dataclass (Phase 5)
│   ├── agent_config.py           # AgentConfigData
│   └── contexts.py               # Context dataclasses
├── orchestration/                 # Multi-agent conversation orchestration
│   ├── orchestrator.py           # ChatOrchestrator
│   ├── response_generator.py     # Response generation
│   ├── context.py                # Conversation context builder
│   └── handlers.py               # Typing indicators, broadcasting
├── routers/                       # REST API endpoints
│   ├── auth.py                   # Authentication
│   ├── rooms.py                  # Room management
│   ├── agents.py                 # Agent information
│   ├── agent_management.py       # Agent CRUD
│   ├── room_agents.py            # Room-agent associations
│   └── messages.py               # Messaging and polling
├── sdk/                           # Claude SDK integration (Phase 5 refactored)
│   ├── manager.py                # AgentManager (orchestration)
│   ├── client_pool.py            # ClientPool (lifecycle management)
│   └── config/                   # Tool configuration (YAML loading)
├── mcp_servers/                   # Standalone MCP servers (used by both providers)
│   ├── action_server.py          # skip, memorize, recall tools
│   └── guidelines_server.py      # guidelines read tool
├── services/                      # Business logic layer
│   ├── agent_service.py          # Agent business logic
│   └── agent_config_service.py   # Config file I/O
├── infrastructure/                # Infrastructure utilities
│   ├── cache.py                  # In-memory caching
│   ├── images.py                 # WebP image compression
│   ├── locking.py                # Cross-platform file locking
│   ├── database/
│   │   └── migrations.py         # Automatic schema migrations
│   └── logging/
│       ├── agent_logger.py       # Agent debug logging
│       └── formatters.py         # Debug message formatting
├── i18n/                          # Internationalization
│   ├── korean.py                 # Korean particle support (은/는, 이/가)
│   ├── serializers.py            # Datetime/bool serialization
│   └── timezone.py               # UTC/KST conversion
└── tests/                         # Test suite
    ├── unit/                     # Unit tests
    └── integration/              # Integration tests
```

## Core Components

### 1. FastAPI Application (`main.py`)

**Middleware:**
- JWT authentication via `X-API-Key` header (exempts `/auth/*`, `/health`, `/docs`)
- Rate limiting: login 20/min, polling 60-120/min, send 30/min
- Dynamic CORS from env vars (`FRONTEND_URL`, `VERCEL_URL`)

**Startup:**
- Auto-seeds agents from `agents/` directory
- Enables background scheduler for autonomous conversations

### 2. Database Layer

**Database:** PostgreSQL with asyncpg, async sessions, connection pooling

**Automatic Migrations:** Schema changes handled automatically via `infrastructure/database/migrations.py`. No manual database deletion needed.

**Models:**
- `Room`: Many-to-many with agents, `max_interactions`, `is_paused`, `last_read_at`, computed `has_unread`
- `Agent`: Independent entities, `group` field, filesystem-primary config loading
- `Message`: User/assistant role, `participant_type` (user, agent, situation_builder), optional thinking text
- `RoomAgentSession`: Composite key `(room_id, agent_id)` for SDK session isolation

**Key CRUD Operations:**
- `create_agent()`, `update_agent()`: Parse filesystem config, cache in DB
- `get_or_create_direct_room()`: 1-on-1 rooms named `"Direct: {agent_name}"`
- `seed_agents_from_configs()`: Auto-sync from filesystem on startup
- `append_agent_memory()`: Write to `recent_events.md` with file locking

### 3. Configuration System (`config/`)

**Filesystem-Primary:** All configurations loaded from filesystem with hot-reloading. Changes apply immediately.

**YAML Configuration Files (`config/tools/`):**
- `tools.yaml`: Tool definitions (skip, memorize, recall, guidelines, configuration)
- `guidelines_3rd.yaml`: System prompt template with `{agent_name}` placeholders
- `debug.yaml`: Debug logging configuration

**Agent Configuration:**

*Folder-based (recommended):*
```
agents/
  agent_name/
    ├── in_a_nutshell.md      # Brief identity (third-person)
    ├── characteristics.md     # Personality traits (third-person)
    ├── recent_events.md      # Auto-updated
    ├── consolidated_memory.md # Long-term memories (optional)
    └── profile.png           # Profile picture (optional)
```

**Third-Person Perspective:**
- Agent configs describe character in third-person: "프리렌은..." not "당신은..."
- System prompt uses `{agent_name}` placeholders
- Runtime substitution with Korean particle support (은/는, 이/가)

**File Locking:** Cross-platform (`fcntl`/`msvcrt`) prevents concurrent write conflicts

### 4. Claude SDK Integration (`sdk/`) - Phase 5 Refactored

**Architecture:**
```
AgentManager (445 lines) - Orchestrates responses and interruption
  ├── ClientPool (250 lines) - SDK client lifecycle management
  ├── StreamParser (60 lines) - Stream message parsing
  └── TaskIdentifier (60 lines) - Structured task IDs
```

**AgentManager (`sdk/manager.py`):**
- **Client Management:** Uses ClientPool with `TaskIdentifier(room_id, agent_id)` keys
- **Interruption Support:** `interrupt_all()`, `interrupt_room()`, `interrupt_agent()`
- **Response Generation:** `generate_sdk_response()` yields stream events
- Model: `claude-opus-4-5-20251101` (default) or `claude-haiku-4-5-20251001` (with `USE_HAIKU=true`), 32K thinking tokens

**ClientPool (`sdk/client_pool.py`):**
- **SDK Best Practices:** Reuse clients within sessions, connection locking, exponential backoff retry
- **Lifecycle Management:** `get_or_create()`, `cleanup()`, `cleanup_room()`, `shutdown_all()`
- **Background Disconnect:** Avoids cancel scope violations

**StreamParser (`sdk/stream_parser.py`):**
- **Structured Parsing:** Returns `ParsedStreamMessage` dataclass instead of tuples
- **SDK Types:** Leverages `AssistantMessage`, `TextBlock`, `ThinkingBlock`, `ToolUseBlock`

**MCP Tools:**
- **Action Tools:** `skip`, `memorize` (append to recent_events.md), `recall` (retrieve long-term memories)
- **Config Tools:** `guidelines`, `configuration`

### 5. Chat Orchestration (`orchestration/`)

**ChatOrchestrator (`orchestrator.py`):**
- **Multi-round conversations:** Initial responses (concurrent), follow-up rounds (sequential, shuffled)
- **Limits:** Max 5 follow-up rounds, 30 messages total
- **Interruption handling:** Tracks `active_room_tasks`, cancels on new user message
- **Background autonomous chats:** APScheduler every 2s for rooms with recent activity

**ResponseGenerator (`response_generator.py`):**
- **Context building:** `build_conversation_context()` with message filtering
- **Interruption checks:** Compares timestamps before saving

### 6. Authentication (`auth.py`)

**Dual Role System:** Admin (`API_KEY_HASH`) + optional Guest (`GUEST_PASSWORD_HASH`)

**JWT Tokens:** 7-day expiration, signed with `JWT_SECRET`

**Middleware:** Validates `X-API-Key` header, exempts `/auth/*`, `/health`, `/docs`

**Rate Limits:** Login 20/min, polling 60-120/min, send 30/min

See [../SETUP.md](../SETUP.md) for details.

## Memory System

### Two-Tier Memory

**1. Recent Events (Short-term)**
- Storage: `agents/{name}/recent_events.md`
- Format: `- [2025-11-18] Event description - emotional core`
- Updates: Agents use `memorize` tool

**2. Long-term Memory**
- Storage: `agents/{name}/consolidated_memory.md` (or `long_term_memory.md`)
- Format: `## Subtitle\nMemory content...`
- Retrieval: On-demand via `recall` tool - agents actively fetch specific memories by subtitle

## API Endpoints

### Authentication
```
POST   /auth/login                 # Login with password, returns JWT
GET    /auth/verify                # Verify JWT token
GET    /health                     # Health check (no auth)
```

### Room Management
```
GET    /rooms                      # List all rooms
POST   /rooms                      # Create room
GET    /rooms/{id}                 # Get room with agents and messages
PATCH  /rooms/{id}                 # Update room
POST   /rooms/{id}/pause           # Pause room and interrupt agents
POST   /rooms/{id}/resume          # Resume room
POST   /rooms/{id}/mark-read       # Mark as read
DELETE /rooms/{id}                 # Delete room (Admin only)
```

### Agent Management
```
GET    /agents                     # List all agents
GET    /agents/configs             # List available config files
POST   /agents                     # Create agent
GET    /agents/{id}                # Get agent
PATCH  /agents/{id}                # Update agent (Admin only)
POST   /agents/{id}/reload         # Reload from filesystem (Admin only)
DELETE /agents/{id}                # Delete agent (Admin only)
GET    /agents/{id}/direct-room    # Get/create 1-on-1 room
GET    /agents/{name}/profile-pic  # Serve profile picture
```

### Room-Agent Association
```
GET    /rooms/{room_id}/agents              # List agents in room
POST   /rooms/{room_id}/agents/{agent_id}   # Add agent to room
DELETE /rooms/{room_id}/agents/{agent_id}   # Remove agent (Admin only)
```

### Messages & Polling
```
GET    /rooms/{room_id}/messages              # Get all messages
GET    /rooms/{room_id}/messages/poll         # Poll for new messages
GET    /rooms/{room_id}/chatting-agents       # Get chatting agents
POST   /rooms/{room_id}/messages/send         # Send user message
DELETE /rooms/{room_id}/messages              # Clear messages (Admin only)
GET    /rooms/{room_id}/critic-messages       # Get critic feedback
```

All endpoints except `/auth/*`, `/health`, `/docs`, and profile pictures require `X-API-Key` header.

## Configuration

### Environment Variables (`.env`)

**Required:**
- `API_KEY_HASH` - Bcrypt hash of admin password
- `JWT_SECRET` - Secret for JWT signing (auto-generates if not provided)

**Optional:**
- `USER_NAME` - Display name for user messages (default: "User")
- `DEBUG_AGENTS` - "true" for verbose logging
- `RECALL_MEMORY_FILE` - Memory file for recall tool: `consolidated_memory` (default) or `long_term_memory`
- `READ_GUIDELINE_BY` - Guideline delivery mode: `active_tool` (default) or `description`
- `USE_HAIKU` - "true" to use Haiku model instead of Opus (default: false)
- `PRIORITY_AGENTS` - Comma-separated agent names for priority responding
- `MAX_CONCURRENT_ROOMS` - Max rooms for background scheduler (default: 5)
- `ENABLE_GUEST_LOGIN` - "true"/"false" to enable/disable guest login (default: true)
- `FRONTEND_URL` - CORS allowed origin
- `VERCEL_URL` - Auto-detected on Vercel
- `GUEST_PASSWORD_HASH` - Optional guest access

### Database

**Connection:** PostgreSQL via `DATABASE_URL` environment variable

**Format:** `postgresql+asyncpg://user:password@host:port/database`

**Features:** Connection pooling, automatic migrations, no manual schema changes needed

**Complete Reset:**
1. Drop and recreate the database: `dropdb chitchats && createdb chitchats`
2. Restart backend
3. Agents re-seeded from `agents/` directory

## Development Patterns

### Adding Features

**Add DB field:**
1. Update `models.py`
2. Add migration in `infrastructure/database/migrations.py`
3. Update `schemas.py` and `crud.py`
4. Restart (migration runs automatically)

**Add endpoint:**
1. Define schemas in `schemas.py`
2. Add business logic to `services/`
3. Add CRUD to `crud.py` if needed
4. Create router endpoint in `routers/`

**Add MCP tool:**
1. Define in `mcp_servers/action_server.py` or `mcp_servers/guidelines_server.py`
2. Add config to `config/tools/tools.yaml`

**Update system prompt/guidelines:**
1. Edit `config/tools/guidelines_3rd.yaml`
2. Changes apply immediately (hot-reloading)

### Architecture Patterns

**Filesystem-Primary:**
- Agent configs, YAML settings loaded from filesystem
- Database is cache only
- Hot-reloading: changes apply immediately
- File locking prevents conflicts

**Session Management:**
- Each agent has separate SDK session per room
- Session ID tracked in `RoomAgentSession`
- SDK auto-manages conversation history

**Interruption Handling:**
- New user messages cancel ongoing processing
- `last_user_message_time` timestamp comparison
- Background tasks tracked per room

## Debugging

### Debug Logging

**Enable:**
- `DEBUG_AGENTS=true` in `.env`
- Edit `config/tools/debug.yaml`

**Output Includes:**
- System prompt, tools, messages, responses
- Session IDs, tool calls, memory selections
- Interruption events

**Granular Controls (`debug.yaml`):**
```yaml
debug:
  enabled: true
  output_file: "debug.txt"
  include:
    system_prompt: true
    tools: true
    messages: true
    response: true
```

### Common Issues

**Agent not responding:**
- Check if agent used `skip` tool
- Verify session persistence
- Check if room is paused

**Memory not working:**
- Check long-term memory file exists for `recall`

**Connection pool exhaustion:**
- Check `pool_size` and `max_overflow` in `database.py`
- Current defaults: pool_size=10, max_overflow=20
- Consider increasing for high-traffic deployments

## Dependencies

**Package Manager:** uv (Python 3.11+)

**Core:** FastAPI, uvicorn, APScheduler, SQLAlchemy, asyncpg

**AI:** claude-agent-sdk

**Security:** bcrypt, PyJWT, slowapi

**Utils:** python-dotenv, pydantic, ruamel.yaml

---

**For detailed refactoring documentation**, see [../plan.md](../plan.md) (Phase 5: AgentManager Split).
