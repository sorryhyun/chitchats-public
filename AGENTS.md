# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ChitChats is a multi-agent chat room application where multiple AI agents with different personalities can interact in real-time chat rooms. The application supports multiple AI providers (Claude and Codex) with provider selection at room creation time.

**Tech Stack:**
- Backend: FastAPI + SQLAlchemy (async) + PostgreSQL
- Frontend: React + TypeScript + Vite + Tailwind CSS
- AI Integration: Multi-provider support (Claude Agent SDK, OpenAI Codex)
- Real-time Communication: HTTP Polling (2-second intervals)
- Background Processing: APScheduler for autonomous agent interactions

## Development Commands

```bash
make dev           # Run both backend and frontend
make install       # Install all dependencies
make stop          # Stop all servers
make clean         # Clean build artifacts

# Backend only
cd backend && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend only
cd frontend && npm run dev

# Run tests
uv run pytest --cov=backend --cov-report=term-missing
```

## Architecture Overview

### Backend
- **FastAPI** application with REST API and polling endpoints
- **Multi-provider architecture** with abstraction layer for Claude and Codex
- **PostgreSQL** database with async SQLAlchemy (asyncpg)
- **Background scheduler** for autonomous agent conversations
- **In-memory caching** for performance optimization
- **Domain layer** with Pydantic models for type-safe business logic
- **Key features:**
  - **Multi-provider support** - Choose between Claude or Codex when creating rooms (immutable after creation)
  - Agents are independent entities that persist across rooms
  - Room-specific conversation sessions per agent
  - Auto-seeding agents from `agents/` directory
  - Recent events auto-update based on conversation history
  - Agents continue conversations in background when user is not in room
  - Cached database queries and filesystem reads (70-90% performance improvement)
  - Modular tool architecture (action_tools, guidelines_tools)

**For detailed backend documentation**, see [backend/README.md](backend/README.md) which includes:
- Complete API reference
- Database schema details
- Agent configuration system
- Chat orchestration logic
- Session management
- Phase 5 refactored SDK integration (AgentManager, ClientPool, StreamParser)
- Debugging guides

**For multi-provider implementation details**, see [plan.md](plan.md) which documents:
- Provider abstraction layer (`backend/providers/`)
- Immutable provider architecture (provider set at room creation)
- Claude and Codex provider implementations
- Provider health check endpoints

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

### Multi-Provider Architecture

ChitChats supports multiple AI providers with an **immutable provider** design:

**Supported Providers:**
- **Claude** (default) - Anthropic Claude via Agent SDK
- **Codex** - OpenAI Codex via CLI

**Key Design Decisions:**
- Provider is selected at room creation and **cannot be changed** afterward
- Each room uses a single provider for all conversations
- Provider indicator shown in room list and header (amber for Claude, green for Codex)
- Session management is provider-specific (Claude uses sessions, Codex uses threads)

**Provider Selection:**
```
Create Room Dialog:
┌─────────────────────────────┐
│ Room Name: [____________]   │
│                             │
│ Provider:                   │
│ [🟠 Claude] [🟢 Codex]      │
│                             │
│ [Create Room]               │
└─────────────────────────────┘
```

**Debug Endpoints:**
- `GET /debug/providers` - List supported providers
- `GET /debug/providers/health` - Check provider availability

**Provider Implementation:**
- Base classes in `backend/providers/base.py`
- Provider factory in `backend/providers/factory.py`
- Claude implementation in `backend/providers/claude/`
- Codex implementation in `backend/providers/codex/`

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

**Profile Pictures:** Add image files (png/jpg/jpeg/gif/webp/svg) to agent folders. Common names: `profile.*`, `avatar.*`, `picture.*`, `photo.*`. Changes apply immediately.

### Filesystem-Primary Architecture

**Agent configs**, **system prompt**, and **tool configurations** use filesystem as single source of truth:
- Agent configs: `agents/{name}/*.md` files (DB is cache only)
- System prompt: `backend/config/tools/guidelines_3rd.yaml` (`system_prompt` field)
- Tool configurations: `backend/config/tools/*.yaml` files
- Changes apply immediately on next agent response (hot-reloading)
- File locking prevents concurrent write conflicts
- See `backend/utils/file_locking.py` for implementation

### Tool Configuration (YAML-Based)

Tool descriptions and debug settings are configured via YAML files in `backend/config/tools/`:

**`tools.yaml`** - Tool definitions and descriptions
- Defines available tools (skip, memorize, guidelines, configuration)
- Tool descriptions support template variables (`{agent_name}`, `{config_sections}`)
- Enable/disable tools individually
- Changes apply immediately (no restart required)

### Group-Specific Tool Overrides

You can override tool configurations for all agents in a group using `group_config.yaml`:

**Structure:**
```
agents/
  group_슈타게/
    ├── group_config.yaml  # Group-wide tool overrides
    └── 크리스/
        ├── in_a_nutshell.md
        └── ...
```

**Example `group_config.yaml`:**
```yaml
# Override tool responses/descriptions for all agents in this group
tools:
  recall:
    # Return memories verbatim without AI rephrasing
    response: "{memory_content}"

  skip:
    # Custom skip message for this group
    response: "This character chooses to remain silent."
```

**Features:**
- **Follows `tools.yaml` structure** - Any field from `tools.yaml` can be overridden (response, description, etc.)
- **Group-wide application** - Applies to all agents in `group_*` folder
- **Hot-reloaded** - Changes apply immediately on next agent response
- **Selective overrides** - Only override what you need, inherit the rest from global config

**Use Cases:**
- **No rephrasing for technical content** - Scientific/technical characters (e.g., Steins;Gate group) recall memories exactly as written
- **Group-specific response styles** - Different personality groups can have customized tool responses
- **Context-specific behaviors** - Anime groups can have culturally appropriate tool messages

See `agents/group_config.yaml.example` for more examples.

### Group Behavior Settings

In addition to tool overrides, `group_config.yaml` supports behavior settings that affect how agents interact:

```yaml
# group_config.yaml
interrupt_every_turn: true  # Agent responds after every message
priority: 5                 # Higher priority = responds before others
transparent: true           # Agent's responses don't trigger others to reply
```

**Available Settings:**
- **`interrupt_every_turn`** - When `true`, agents in this group always get a turn after any message
- **`priority`** - Integer value (default: 0). Higher values mean agent responds before lower priority agents
- **`transparent`** - When `true`, other agents won't be triggered to respond after this agent speaks. Useful for Narrator-type agents whose commentary shouldn't prompt replies. Messages are still visible to all agents.

**Example: Narrator Agent Group**
```yaml
# agents/group_tool/group_config.yaml
interrupt_every_turn: true  # Narrator always comments after each message
priority: 5                 # Narrator responds first
transparent: true           # Other agents don't reply to narrator
```

**`guidelines_3rd.yaml`** - Role guidelines for agent behavior
- Defines system prompt template and behavioral guidelines
- Uses third-person perspective in agent configurations (explained below)
- Currently uses `v3` (enhanced guidelines with explicit scene handling)
- Guidelines are injected via tool descriptions
- Supports situation builder notes

**`debug.yaml`** - Debug logging configuration
- Control what gets logged (system prompt, tools, messages, responses)
- Configure output format (separator, timestamps, etc.)
- Message formatting options (truncation, length limits)
- Can be overridden by `DEBUG_AGENTS` environment variable

### Third-Person Perspective System

ChitChats uses a **third-person perspective** approach for agent configurations, which separates character description from AI instructions.

**Why third-person?** When running through Claude Agent SDK (via Claude Code), agents inherit an immutable system prompt ("You are Claude Code...") from the parent environment. Third-person character descriptions avoid conflicting "You are..." statements, allowing our system prompt to layer character identity on top of the inherited prompt. See [how_it_works.md](how_it_works.md#why-third-person-perspective) for technical details.

**How it works:**
1. **Agent configuration files** describe the character in third-person:
   - English: "Dr. Sarah Chen is a seasoned data scientist..."
   - Korean: "프리렌은 1000년 이상 살아온 엘프 마법사로..."

2. **System prompt** (in `guidelines_3rd.yaml`) uses `{agent_name}` placeholders:
   - "In here, you are fully embodying the character {agent_name}..."
   - "Think only 'what would {agent_name} do?', not 'what is morally correct?'"

3. **At runtime**, the agent name is substituted into the template, creating instructions like:
   - "You are 프리렌. Embody 프리렌's complete personality..."
   - "Think only 'what would 프리렌 do?', not 'what is morally correct?'"

**Benefits:**
- **Clearer separation** between AI instructions and character descriptions
- **Consistent format** across all agents (English and Korean)
- **Proper Korean grammar** with automatic particle selection (은/는, 이/가, etc.)
- **Better roleplay quality** by reinforcing character identity throughout guidelines

**Example: Enabling debug logging**
```yaml
# backend/config/tools/debug.yaml
debug:
  enabled: true  # Or set DEBUG_AGENTS=true in .env
  output_file: "debug.txt"
```

## Quick Start

1. **Setup environment:**
   ```bash
   # Install uv (if not already installed)
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Install all dependencies
   make install
   ```

2. **Setup PostgreSQL:**
   ```bash
   # Install PostgreSQL (if not already installed)
   # macOS: brew install postgresql@15
   # Ubuntu: sudo apt install postgresql

   # Create database
   createdb chitchats

   # Or with custom credentials:
   # psql -c "CREATE DATABASE chitchats;"
   ```

3. **Configure authentication:**
   ```bash
   # Generate password hash
   make generate-hash
   # Enter your desired password when prompted

   # Generate JWT secret
   python -c "import secrets; print(secrets.token_hex(32))"

   # Copy and configure .env in project root
   cp .env.example .env
   # Edit .env and add API_KEY_HASH and JWT_SECRET
   ```

   See [SETUP.md](SETUP.md) for detailed instructions.

4. **Run development servers:**
   ```bash
   make dev
   ```

5. **Access application:**
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

   Login with the password you used to generate the hash.

## Configuration

### Backend Environment Variables (`.env`)

**Required:**
- `DATABASE_URL` - PostgreSQL connection string (default: `postgresql+asyncpg://postgres:postgres@localhost:5432/chitchats`)
- `API_KEY_HASH` - Bcrypt hash of your password (generate with `make generate-hash`)
- `JWT_SECRET` - Secret key for signing JWT tokens (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)

**Optional:**
- `USER_NAME` - Display name for user messages in chat (default: "User")
- `DEBUG_AGENTS` - Set to "true" for verbose agent logging
- `RECALL_MEMORY_FILE` - Memory file for recall tool: `consolidated_memory` (default) or `long_term_memory`
- `READ_GUIDELINE_BY` - Guideline delivery mode: `active_tool` (default) or `description`
- `USE_HAIKU` - Set to "true" to use Haiku model instead of Opus (default: false)
- `PRIORITY_AGENTS` - Comma-separated agent names for priority responding
- `MAX_CONCURRENT_ROOMS` - Max rooms for background scheduler (default: 5)
- `ENABLE_GUEST_LOGIN` - Enable/disable guest login (default: true)
- `FRONTEND_URL` - CORS allowed origin for production (e.g., `https://your-app.vercel.app`)
- `VERCEL_URL` - Auto-detected on Vercel deployments

**Claude Agent SDK:**
- Authentication is handled by the Claude Agent SDK when running through Claude Code with an active subscription
- No ANTHROPIC_API_KEY configuration is needed for the SDK

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

**Update agent:** Edit `.md` files directly (changes apply immediately)

**Update system prompt:** Edit `system_prompt` section in `backend/config/tools/guidelines_3rd.yaml` (changes apply immediately)

**Update tool descriptions:** Edit YAML files in `backend/config/tools/` (changes apply immediately)

**Update guidelines:** Edit `v1/v2/v3.template` section in `backend/config/tools/guidelines_3rd.yaml` (changes apply immediately)

**Enable debug logging:** Set `DEBUG_AGENTS=true` in `.env` or edit `backend/config/tools/debug.yaml`

**Add database field:** Update `models.py`, add migration in `backend/utils/migrations.py`, update `schemas.py` and `crud.py`, restart

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
