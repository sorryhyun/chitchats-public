# Codex CLI: Architectural Decisions

This document explains **why** we chose our current approach to integrating Codex CLI into ChitChats, based on analysis of the Codex source code.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [The Core Problem](#the-core-problem)
3. [Why App Server Mode (Not MCP Server)](#why-app-server-mode-not-mcp-server)
4. [Why Per-Agent Instances](#why-per-agent-instances)
5. [Why Instructions at Session Init](#why-instructions-at-session-init)
6. [Why We Disable Certain Features](#why-we-disable-certain-features)
7. [Implementation Reference](#implementation-reference)
8. [Appendix: Codex Internals](#appendix-codex-internals)

---

## Quick Start

### Installation

```bash
npm install -g @openai/codex
codex login              # Authenticate (opens browser)
codex login status       # Verify authentication
```

### Running App Server

```bash
# Basic
codex app-server

# With custom instructions
codex app-server -c "base_instructions=You are a helpful assistant"

# Disable shell/web for chat use cases
codex app-server \
  -c "features.shell_tool=false" \
  -c "web_search=disabled"
```

### JSON-RPC Protocol (over stdio)

**Create a thread:**

```json
{"method": "thread/start", "params": {"baseInstructions": "You are Alice..."}, "id": 1}
```

Response: `{"result": {"threadId": "thread_abc123"}, "id": 1}`

**Send a message:**

```json
{"method": "turn/start", "params": {"threadId": "thread_abc123", "input": [{"type": "text", "text": "Hello!"}]}, "id": 2}
```

Streaming notifications follow (no `id` field):

```json
{"method": "item/agentMessage/delta", "params": {"delta": "Hi there"}}
{"method": "item/agentMessage/delta", "params": {"delta": "! How can I help?"}}
{"method": "turn/completed", "params": {"status": "completed"}}
```

**Resume a thread (after restart):**

```json
{"method": "thread/resume", "params": {"threadId": "thread_abc123"}, "id": 3}
```

### Key Events

| Event | Purpose |
|-------|---------|
| `turn/started` | Turn began processing |
| `turn/completed` | Turn finished |
| `item/agentMessage/delta` | Streaming text chunk |
| `item/reasoning/textDelta` | Streaming thinking |
| `item/mcpToolCall/completed` | MCP tool was called |

---

## The Core Problem

ChitChats needs to run multiple AI agents with distinct personalities in real-time chat rooms. Each agent requires:

- **Unique system prompts** (personality, backstory, behavior)
- **Session continuity** (remember conversation context)
- **Custom tools** (agent-specific MCP servers)
- **Isolation** (agents shouldn't leak into each other's context)

Codex CLI offers three integration modes. We evaluated each against these requirements.

---

## Why App Server Mode (Not MCP Server)

### The Three Options

| Mode | How it Works | Session State |
|------|--------------|---------------|
| `codex` CLI | Spawn process per query | None (stateless) |
| `codex-mcp-server` | Connect via MCP protocol | Per-call only |
| `codex app-server` | Long-running JSON-RPC server | Thread-based persistence |

### Why Not `codex` Per Query?

Spawning a new process for each message has severe overhead:

```
User sends message
  → Spawn codex process (~2-3 seconds)
  → Load config, authenticate
  → Process single message
  → Exit and lose all context
```

For a chat application with real-time expectations, this latency is unacceptable. More critically, **there's no way to maintain conversation context** across messages.

### Why Not MCP Server?

The `codex-mcp-server` has a fundamental limitation we discovered by reading the source:

```text
MCP Client (with image support)
    ↓
MCP Server (TEXT-ONLY interface) ← bottleneck
    ↓
Codex Core (full multimodal support)
```

The MCP server only accepts `String` prompts:

```rust
// codex-rs/mcp-server/src/codex_tool_config.rs
pub struct CodexToolCallParam {
    pub prompt: String,  // Text only - no image support
}
```

Even though Codex core supports `UserInput::Image` and `UserInput::LocalImage`, the MCP protocol interface wraps input as `UserInput::Text` only.

For a chat application where users share images, this is a dealbreaker.

### Why App Server Wins

`codex app-server` provides:

1. **Thread-based sessions** - Create once, resume indefinitely
2. **Full multimodal support** - Direct access to Codex core (no MCP bottleneck)
3. **Streaming events** - Real-time text/thinking deltas via JSON-RPC
4. **Per-thread instructions** - Each thread maintains its own system prompt

```
User sends message
  → Route to existing app-server instance
  → Resume thread (instant)
  → Stream response in real-time
  → Thread persists for next message
```

---

## Why Per-Agent Instances

### The Alternative: Shared Instance

A simpler approach would be one `codex app-server` serving all agents:

```
Single App Server
├── Thread for Alice in Room 1
├── Thread for Bob in Room 1
├── Thread for Alice in Room 2
└── ...
```

**Problems:**
- MCP servers are configured at startup, not per-thread
- Agent-specific tools (memory, actions) can't vary per-thread
- A crash affects ALL agents simultaneously

### Our Approach: Per-Agent Instances

```
CodexAppServerPool (singleton)
├── Agent "Alice" → CodexAppServerInstance (with Alice's MCP config)
├── Agent "Bob"   → CodexAppServerInstance (with Bob's MCP config)
└── ...
```

Each instance has agent-specific MCP servers baked in at startup:

```python
mcp_servers = {
    "memory_server": {
        "env": {"AGENT_NAME": "alice"}  # Agent-specific
    }
}
```

**Benefits:**
- Complete isolation between agents
- Agent-specific tools without workarounds
- Crash isolation (one agent down ≠ all agents down)
- Independent scaling and lifecycle

**Trade-off:** Higher memory usage (one process per agent). Mitigated by:
- Idle timeout eviction (default: 10 minutes)
- Max instance limit with LRU eviction
- Lazy creation (instances spawn on first interaction)

---

## Why Instructions at Session Init

### The Codex Constraint

From analyzing the Codex source, we found:

> Instructions are applied at INIT TIME (session/thread creation), NOT per-turn

The resolution order (from `codex.rs:285-294`):

1. `config.base_instructions` override (CLI/API)
2. `conversation_history.get_base_instructions()` (session persistence)
3. `model_info.get_model_instructions()` (model default)

This means:

- `base_instructions` is set when creating a thread
- Changing personality mid-conversation requires a new thread
- Per-turn instruction changes are ignored

### Implications for ChitChats

Since agent personalities are defined in `base_instructions`, we:

1. **Create thread at first interaction** with the agent's full system prompt
2. **Persist thread_id** in database for session continuity
3. **Resume existing threads** for follow-up messages in the same room

If an agent's personality files change, we'd need to invalidate their threads—but this is rare in practice.

### The `instructions` Config Field is Dead Code

A surprising finding: the `instructions` field in `config.toml` is **defined but never read**:

```rust
// ConfigToml struct in config/mod.rs
pub instructions: Option<String>,  // Never used!
```

No code reads `cfg.instructions` anywhere in the codebase. Use `base_instructions` or `model_instructions_file` instead.

---

## Why We Disable Certain Features

### The Roleplay Use Case

ChitChats agents are characters in chat rooms, not coding assistants. Codex's default features work against this:

| Feature | Why Disable |
|---------|-------------|
| `shell_tool` | Characters shouldn't execute system commands |
| `web_search` | Breaks immersion, leaks real-world info |
| `view_image` | We handle images directly, not via Codex tool |
| Skills (`~/.codex/skills/`) | Auto-injected prompts break character |
| `AGENTS.md` pickup | Reads project files, contaminates personality |

### Skills Injection Problem

Codex auto-loads instructions from `~/.codex/skills/` into every session. For roleplay:

```
System: You are Alice, a shy librarian...
Skills: [AUTO-INJECTED] You are a helpful coding assistant...
```

This destroys character immersion. Solution: `chmod 000 ~/.codex/skills`

### Working Directory Contamination

Codex reads `AGENTS.md` and other files from the working directory. If running from the ChitChats repo:

```
System: You are Alice...
Codex: [Reads AGENTS.md] Oh, I see there are multiple agents configured...
```

Solution: Use an empty temp directory as `cwd`:

```python
cwd = Path(tempfile.gettempdir()) / "codex-empty"
```

---

## Implementation Reference

### Key Files

| File | Purpose |
|------|---------|
| `backend/providers/codex/app_server_pool.py` | Singleton pool with LRU eviction |
| `backend/providers/codex/app_server_instance.py` | Per-agent process lifecycle |
| `backend/providers/codex/transport.py` | JSON-RPC over stdio |
| `backend/providers/codex/constants.py` | Event types, session recovery |

### Configuration Defaults

```bash
CODEX_MAX_INSTANCES=10      # Max concurrent instances
CODEX_IDLE_TIMEOUT=600      # 10 min idle before shutdown
```

### Session Recovery

When an instance restarts (crash, idle timeout), threads become invalid. We handle this via `SessionRecoveryError`:

1. Detect invalid thread_id from Codex error
2. Raise `SessionRecoveryError` to caller
3. Caller rebuilds full conversation history
4. Create new thread with complete context

This ensures users never see "session expired" errors—conversations continue seamlessly.

---

## Summary

| Decision | Rationale |
|----------|-----------|
| App Server mode | Session persistence, full multimodal, streaming |
| Per-agent instances | MCP isolation, crash isolation, agent-specific tools |
| Instructions at init | Codex constraint—instructions aren't per-turn |
| Disable shell/web/skills | Roleplay use case requires immersion |
| Empty working directory | Prevent file contamination |
| Thread persistence in DB | Resume across instance restarts |

---

## Appendix: Codex Internals

This section documents Codex CLI internals discovered through source code analysis.

### Instruction-Related Fields

There are **multiple instruction fields** that serve different purposes:

| Field | Location | Purpose | Status |
|-------|----------|---------|--------|
| `instructions` | ConfigToml | System instructions | **DEAD CODE** |
| `base_instructions` | Config (runtime) | Actual system prompt | Active |
| `developer_instructions` | Config | Separate "developer" role | Active |
| `user_instructions` | Config | From AGENTS.md file | Active |
| `model_instructions_file` | ConfigToml/Profile | Path to instructions file | Active |

### Tool Disabling Reference

**Tools that CAN be disabled:**

| Tool | Config Option |
|------|---------------|
| Shell tools | `features.shell_tool = false` |
| Web search | `web_search = "disabled"` |
| View image | `tools_view_image = false` |
| Apply patch | `include_apply_patch_tool = false` |
| Collab tools | `features.collab = false` |

**Tools that CANNOT be disabled** (hard-coded in `build_specs()`):

- `plan` - Update plan tool
- `list_mcp_resources`
- `list_mcp_resource_templates`
- `read_mcp_resource`

### MCP Server Tool Filtering

Per-server tool filtering via `config.toml`:

```toml
[mcp_servers.my_server]
enabled_tools = ["tool1", "tool2"]   # Whitelist
disabled_tools = ["tool3"]            # Blacklist (applied second)
```

### CLI Examples

```bash
# Disable shell tools
codex app-server -c "features.shell_tool=false"

# Disable web search
codex app-server -c "web_search=disabled"

# Set custom instructions
codex app-server -c "base_instructions=You are Alice..."
```
