# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Claude Code Role Play is a multi-Claude chat room application where multiple Claude AI agents with different personalities can interact in real-time chat rooms.

**Tech Stack:**
- Backend: FastAPI + SQLAlchemy (async) + SQLite
- Frontend: React + TypeScript + Vite + Tailwind CSS
- AI Integration: Anthropic Claude Agent SDK
- Real-time Communication: HTTP Polling (4-second intervals)
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

# Run all tests with coverage
uv run pytest --cov=backend --cov-report=term-missing

# Run a single test file
uv run pytest backend/tests/unit/test_crud.py -v

# Run a single test function
uv run pytest backend/tests/unit/test_crud.py::test_function_name -v

# Lint code (auto-fixes issues)
uv run ruff check --fix .
```

## Architecture Overview

### Backend
- **FastAPI** application with REST API and polling endpoints
- **Multi-agent orchestration** with Claude SDK integration
- **SQLite** database with async SQLAlchemy and write queue serialization
- **Background scheduler** for autonomous agent conversations
- **In-memory caching** for performance optimization
- **Modular configuration** with hot-reloading and startup validation
- **Domain layer** with Pydantic models for type-safe business logic
- **Key features:**
  - Agents are independent entities that persist across rooms
  - Room-specific conversation sessions per agent
  - Auto-seeding agents from `agents/` directory
  - Recent events auto-update based on conversation history
  - Agents continue conversations in background when user is not in room
  - Cached database queries and filesystem reads (70-90% performance improvement)
  - Modular tool architecture (action_tools, guidelines_tools, brain_tools)
  - Write queue for SQLite contention elimination
  - Comprehensive config validation with startup diagnostics

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
  - HTTP polling for live message updates (4-second intervals)
  - Typing indicators
  - Agent thinking process display

## Agent Configuration

Agents can be configured using folder-based structure (new) or single file (legacy):

**New Format (Preferred):**
```
agents/
  agent_name/
    ├── in_a_nutshell.md      # Brief identity summary (third-person)
    ├── characteristics.md     # Personality traits (third-person)
    ├── recent_events.md      # Auto-updated from conversations
    ├── consolidated_memory.md # Long-term memories with subtitles (optional)
    ├── anti_pattern.md       # Behaviors to avoid (optional)
    ├── memory_brain.md       # Memory-brain configuration (optional)
    └── profile.png           # Optional profile picture (png, jpg, jpeg, gif, webp, svg)
```

**IMPORTANT:** Agent configuration files must use **third-person perspective**:
- ✅ Correct: "Dr. Chen is a seasoned data scientist..." or "프리렌은 엘프 마법사로..."
- ❌ Wrong: "You are Dr. Chen..." or "당신은 엘프 마법사로..."

**Profile Pictures:** Add image files (png/jpg/jpeg/gif/webp/svg) to agent folders. Common names: `profile.*`, `avatar.*`, `picture.*`, `photo.*`. Changes apply immediately.

### Memory System Modes

Claude Code Role Play supports **two mutually exclusive memory modes** controlled by the `MEMORY_BY` environment variable:

#### RECALL Mode (`MEMORY_BY=RECALL`)
- **On-demand memory retrieval** - Agents actively call the `recall` tool to fetch specific memories
- **Lower baseline token cost** - Only memory subtitles are shown in context, full content loaded on request
- **Agent-controlled** - Agents decide when and which memories to retrieve
- **Memory files:** `consolidated_memory.md` (default) or `long_term_memory.md`
- **Format:** Memories organized with `## [subtitle]` headers
- **Context injection:** Memory subtitles list shown in `<long_term_memory_index>`

#### BRAIN Mode (`MEMORY_BY=BRAIN`)
- **Automatic memory surfacing** - Separate memory brain agent analyzes context and injects relevant memories
- **Higher baseline token cost** - Selected memories pre-loaded before each response
- **Context-driven** - Psychologically realistic memory activation based on conversation
- **Memory files:** `long_term_memory.md` with `## [subtitle]` format
- **Configuration:** Per-agent `memory_brain.md` file with `enabled: true` and policy setting
- **Policies:** `balanced`, `trauma_biased`, `genius_planner`, `optimistic`, `avoidant`
- **Features:**
  - Max 3 memories per turn (configurable)
  - 10-turn cooldown to prevent repetition
  - Activation strength scores for each memory

**Global Override:** `MEMORY_BY` setting overrides all per-agent configurations. If `MEMORY_BY=RECALL`, memory brain configs are ignored. If `MEMORY_BY=BRAIN`, only agents with `memory_brain.md` enabled will use memory brain.

**Default:** If `MEMORY_BY` is not set or has an invalid value, defaults to `RECALL` mode.

### Filesystem-Primary Architecture

**Agent configs**, **system prompt**, and **tool configurations** use filesystem as single source of truth:
- Agent configs: `agents/{name}/*.md` files (DB is cache only)
- System prompt: `backend/config/tools/guidelines_3rd.yaml` (`system_prompt` field)
- Tool configurations: `backend/config/tools/*.yaml` files
- Changes apply immediately on next agent response (hot-reloading)
- File locking prevents concurrent write conflicts
- See `backend/utils/file_locking.py` for implementation

**Modular Config System (`backend/config/`):**
```
config/
├── config_loader.py    # Facade - backward-compatible imports
├── cache.py            # YAML caching with mtime invalidation
├── loaders.py          # File loaders (get_tools_config, etc.)
├── tools.py            # Tool descriptions and schemas
├── memory.py           # Memory brain configuration
└── validation.py       # Schema validation, startup logging
```

### Tool Configuration (YAML-Based)

Tool descriptions and debug settings are configured via YAML files in `backend/config/tools/`:

**`tools.yaml`** - Tool definitions and descriptions
- Defines available tools (skip, memorize, recall, guidelines, configuration)
- Tool descriptions support template variables (`{agent_name}`, `{config_sections}`)
- Enable/disable tools individually
- Changes apply immediately (no restart required)

**`guidelines_3rd.yaml`** - Role guidelines for agent behavior
- Defines system prompt template and behavioral guidelines
- Uses third-person perspective in agent configurations (explained below)
- Currently uses `v3` (enhanced guidelines with explicit scene handling)
- Guidelines are injected via tool descriptions
- Supports situation builder notes

**`brain_config.yaml`** - Memory brain configuration
- Memory policies (`balanced`, `trauma_biased`, `genius_planner`, `optimistic`, `avoidant`)
- Memory selection tool definitions
- Default settings (max_memories, cooldown)

**`debug.yaml`** - Debug logging configuration
- Control what gets logged (system prompt, tools, messages, responses)
- Configure output format (separator, timestamps, etc.)
- Message formatting options (truncation, length limits)
- Can be overridden by `DEBUG_AGENTS` environment variable

### Third-Person Perspective System

Claude Code Role Play uses a **third-person perspective** approach for agent configurations, which separates character description from AI instructions:

**How it works:**
1. **Agent configuration files** describe the character in third-person:
   - English: "Dr. Sarah Chen is a seasoned data scientist..."
   - Korean: "프리렌은 1000년 이상 살아온 엘프 마법사로..."

2. **System prompt** (in `guidelines_3rd.yaml`) uses `{agent_name}` placeholders:
   - "You are {agent_name}. Embody {agent_name}'s complete personality..."
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

2. **Configure authentication:**
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

3. **Run development servers:**
   ```bash
   make dev
   ```

4. **Access application:**
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

   Login with the password you used to generate the hash.

## Configuration

### Backend Environment Variables (`.env`)

**Required:**
- `API_KEY_HASH` - Bcrypt hash of your password (generate with `python generate_hash.py`)
- `JWT_SECRET` - Secret key for signing JWT tokens (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)

**Optional:**
- `USER_NAME` - Display name for user messages in chat (default: "User")
- `DEBUG_AGENTS` - Set to "true" for verbose agent logging
- `MEMORY_BY` - Memory system mode: `RECALL` (on-demand retrieval, default) or `BRAIN` (automatic surfacing)
- `RECALL_MEMORY_FILE` - Memory file for recall mode: `consolidated_memory` (default) or `long_term_memory`
- `MAX_THINKING_TOKENS` - Maximum thinking tokens for agent responses (default: "32768")
- `MEMORY_BRAIN_MAX_THINKING_TOKENS` - Maximum thinking tokens for memory brain (default: "2048")
- `FRONTEND_URL` - CORS allowed origin for production (e.g., `https://your-app.vercel.app`)
- `VERCEL_URL` - Auto-detected on Vercel deployments

**Deprecated (use `MEMORY_BY` instead):**
- `ENABLE_MEMORY_TOOL` - Deprecated, use `MEMORY_BY=RECALL` or `MEMORY_BY=BRAIN`
- `ENABLE_RECALL_TOOL` - Deprecated, use `MEMORY_BY=RECALL`

**Claude Agent SDK:**
- Authentication is handled by the Claude Agent SDK when running through Claude Code with an active subscription
- No ANTHROPIC_API_KEY configuration is needed for the SDK

### Database
- **Location:** `backend/chitchats.db`
- **Migrations:** Automatic schema updates via `backend/utils/migrations.py` (no manual deletion needed)
- **Complete Reset:** Delete file and restart backend to recreate from scratch

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

**Update guidelines:** Edit `v3.template` section in `backend/config/tools/guidelines_3rd.yaml` (changes apply immediately)

**Enable debug logging:** Set `DEBUG_AGENTS=true` in `.env` or edit `backend/config/tools/debug.yaml`

**Switch to RECALL mode:** Set `MEMORY_BY=RECALL` in `.env`, restart backend (agents will use on-demand recall tool)

**Switch to BRAIN mode:** Set `MEMORY_BY=BRAIN` in `.env`, ensure agents have `memory_brain.md` with `enabled: true`, restart backend

**Add database field:** Update `models.py`, add migration in `backend/utils/migrations.py`, update `schemas.py` and `crud.py`, restart

**Add endpoint:** Define schema in `schemas.py`, add CRUD in `crud/`, add router endpoint in `routers/`

**Run single test:** `uv run pytest backend/tests/unit/test_file.py::test_name -v`

**Build Windows executable:** `uv run poe build-exe` (requires frontend build first)

## Automated Simulations

Claude Code Role Play includes bash scripts for running automated multi-agent chatroom simulations via curl API calls. This is useful for testing agent behaviors, creating conversation datasets, or running batch simulations.

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
