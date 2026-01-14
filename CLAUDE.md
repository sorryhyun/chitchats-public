# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

See [README.md](README.md) for quick start and [backend/README.md](backend/README.md) for configuration.

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
- System prompt: `backend/config/guidelines_3rd.yaml` (`system_prompt` field)
- Tool configurations: `backend/config/*.yaml` files
- Changes apply immediately on next agent response (hot-reloading)
- File locking prevents concurrent write conflicts
- See `backend/infrastructure/locking.py` for implementation

### Tool Configuration (YAML-Based)

Tool descriptions and debug settings are configured via YAML files in `backend/config/`:

**`tools.yaml`** - Tool definitions and descriptions
- Defines available tools (skip, memorize, guidelines, configuration)
- Tool descriptions support template variables (`{agent_name}`, `{config_sections}`)
- Enable/disable tools individually
- Changes apply immediately (no restart required)

### Provider-Specific Tool Overrides

Tool configurations can be overridden per AI provider using `claude_tools.yaml` and `codex_tools.yaml`:

```
backend/config/
├── tools.yaml           # Base tool definitions
├── claude_tools.yaml    # Claude-specific overrides
└── codex_tools.yaml     # Codex-specific overrides
```

**Merge order:** `tools.yaml` → provider config → group config

**Example:** Different moderation tools per provider:
- Claude uses `mcp__guidelines__anthropic`
- Codex uses `mcp__guidelines__openai`

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

## Common Tasks

**Create agent:** Add folder in `agents/` with required `.md` files using third-person perspective (e.g., "Alice is..." not "You are..."), restart backend

**Update agent:** Edit `.md` files directly (changes apply immediately)

**Update system prompt:** Edit `system_prompt` section in `backend/config/guidelines_3rd.yaml` (changes apply immediately)

**Update tool descriptions:** Edit YAML files in `backend/config/` (changes apply immediately)

**Update guidelines:** Edit `v1/v2/v3.template` section in `backend/config/guidelines_3rd.yaml` (changes apply immediately)

**Enable debug logging:** Set `DEBUG_AGENTS=true` in `.env` or edit `backend/config/debug.yaml`

**Add database field:** Update `models.py`, add migration in `backend/infrastructure/database/migrations.py`, update `schemas.py` and `crud/`, restart

**Add endpoint:** Define schema in `schemas.py`, add CRUD in `crud/`, add endpoint in `routers/`
