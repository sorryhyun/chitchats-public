# Codex App Server Integration

This document describes the Codex provider integration in ChitChats using the App Server mode with JSON-RPC streaming.

## Overview

The Codex provider uses `codex app-server` with JSON-RPC 2.0 protocol over stdio. A pool of server instances enables parallel request processing with thread ID affinity routing.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Application Startup                                     │
│    └── CodexAppServerPool.ensure_started()              │
│          └── spawn N instances of: codex app-server     │
│                └── JSON-RPC 2.0 over stdio              │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  AgentManager.generate_sdk_response()                   │
│    └── CodexAppServerClient.query(message)              │
│          └── pool.start_turn(thread_id, text, config)   │
│                └── Streaming notifications              │
└─────────────────────────────────────────────────────────┘
```

## Components

### CodexAppServerPool (`backend/providers/codex/app_server_pool.py`)

Singleton pool manager for multiple `codex app-server` instances:

- **`get_instance()`** - Async singleton accessor
- **`ensure_started()`** - Start all pool instances
- **`create_thread(config)`** - Create new conversation thread
- **`start_turn(thread_id, text, config)`** - Stream turn events
- **`interrupt_turn(thread_id)`** - Interrupt ongoing turn
- **`release_thread(thread_id)`** - Release thread from pool
- **`shutdown()`** - Graceful cleanup

Features:
- Configurable pool size via `CODEX_POOL_SIZE` (default: 3)
- Selection strategies: `round_robin` (default), `least_busy`
- Thread ID affinity routing (follow-up messages route to same instance)
- Automatic recovery from instance failures

### CodexAppServerInstance (`backend/providers/codex/app_server_instance.py`)

Single `codex app-server` subprocess manager:

- JSON-RPC 2.0 protocol (without jsonrpc header field)
- Streaming notifications for real-time output
- Turn interruption via `turn/interrupt` method
- Explicit thread creation via `thread/start`

### CodexAppServerClient (`backend/providers/codex/app_server_client.py`)

Implements `AIClient` interface using the App Server pool:

- Uses shared `CodexAppServerPool` for all requests
- Emits events compatible with `CodexStreamParser`
- Tracks `thread_id` for session continuity

### CodexClientPool (`backend/providers/codex/pool.py`)

Client pool for session management:

- Tracks client instances per agent task
- Same interface as other provider pools
- Server connection is shared via singleton pool

## Configuration Flow

```
AIClientOptions → CodexAppServerOptions → pool.start_turn({
  threadId: "...",
  input: [{type: "text", text: "..."}],
  baseInstructions: "...",
  mcpServers: {...},
  model: "...",
})
```

### Thread Configuration (`thread/start`):
- `cwd` - Working directory
- `model` - Model to use
- `baseInstructions` - System prompt
- `sandbox` - Sandbox mode
- `approvalPolicy` - Approval policy

### Turn Configuration (`turn/start`):
- `threadId` - Thread to continue
- `input` - User message array
- `baseInstructions` - System prompt (can override)
- `mcpServers` - MCP server configurations
- `model` - Model override

## Session Continuity

1. **First turn**: `create_thread(config)` → returns `threadId`
2. **Subsequent turns**: `start_turn(threadId, text, config)` streams events

The thread ID is stored in the database field `codex_thread_id` for persistence across requests.

## Streaming Events

The App Server emits JSON-RPC notifications during a turn:

| Method | Description |
|--------|-------------|
| `turn/started` | Turn has started, includes `turnId` |
| `agent/message/delta` | Incremental text output |
| `agent/reasoning/delta` | Incremental reasoning/thinking |
| `item/completed` | Completed item (message, tool call, etc.) |
| `turn/completed` | Turn finished, includes status |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CODEX_POOL_SIZE` | 3 | Number of server instances |
| `CODEX_SELECTION_STRATEGY` | round_robin | Instance selection: `round_robin` or `least_busy` |
| `CODEX_MODEL` | gpt-5.2 | Default model for Codex provider |

## Advantages

- Parallel processing with thread affinity
- Streaming output for responsive UI
- Turn interruption support
- Automatic instance recovery
- No subprocess spawn overhead per query

## Troubleshooting

### Pool fails to start
Check:
1. Codex CLI is installed: `which codex`
2. Codex is authenticated: `codex login status`

### Instance health issues
The pool automatically attempts to restart unhealthy instances. Check logs for:
```
Attempting to recover N unhealthy instances...
```

### Turn timeouts
Default turn timeout is 120 seconds. Check:
- Model availability
- Network connectivity
- MCP server responsiveness

## Files Reference

| File | Purpose |
|------|---------|
| `backend/providers/codex/app_server_pool.py` | Pool manager |
| `backend/providers/codex/app_server_instance.py` | Single instance manager |
| `backend/providers/codex/app_server_client.py` | AIClient implementation |
| `backend/providers/codex/app_server_parser.py` | Event parser |
| `backend/providers/codex/pool.py` | Client pool |
| `backend/providers/codex/provider.py` | Provider implementation |
| `backend/core/app_factory.py` | Lifespan hooks for startup/shutdown |

---

## Setup Notes

### Disable Codex Skills Injection

Codex automatically injects skill instructions from `~/.codex/skills/` into every conversation. This breaks character immersion in roleplay. **There is no config option to disable this** - skills loading is hardcoded in Codex.

**Solution: Restrict permissions on the skills directory**

```bash
chmod 000 ~/.codex/skills
```

This prevents Codex from reading the skills directory, effectively disabling skill injection.

To re-enable skills later:
```bash
chmod 755 ~/.codex/skills
```

### Empty Working Directory

ChitChats sets `cwd` to `/tmp/codex-empty` to prevent Codex from picking up:
- `AGENTS.md` files from the project directory
- Other project-specific instructions

This is handled automatically by the provider.
