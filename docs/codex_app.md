# Codex App Server Integration

This document describes the Codex provider integration in ChitChats using the official `codex-app-server` Python SDK with JSON-RPC streaming over stdio.

## Overview

The Codex provider uses the official `codex-app-server` SDK (`AppServerClient`) to manage `codex app-server` subprocesses. Each agent gets a dedicated instance with MCP servers baked in at startup. Communication uses typed JSON-RPC 2.0 over stdio, with Pydantic models for all notifications.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  ResponseGenerator                                        │
│    └── AgentManager.generate_sdk_response()               │
│          └── CodexAppServerClient (AIClient interface)    │
│                └── CodexAppServerPool (singleton)         │
│                      └── CodexAppServerInstance (per-agent)│
│                            └── AppServerClient (SDK)     │
│                                  └── codex app-server    │
│                                        (subprocess)      │
└──────────────────────────────────────────────────────────┘
```

## Components

### CodexAppServerPool (`backend/providers/codex/app_server_pool.py`)

Singleton pool managing per-agent app-server instances:

- **`get_instance()`** - Async singleton accessor
- **`get_or_create_instance(agent_key, startup_config)`** - Creates dedicated instance per agent
- **`try_resume_thread(thread_id)`** - Resume threads after instance restart
- **`register_thread(thread_id, agent_key)`** - Track thread→agent mapping
- **`shutdown()`** - Graceful cleanup of all instances

Features:
- Per-agent instance isolation (each agent gets its own subprocess + MCP servers)
- Configurable idle timeout via `CODEX_IDLE_TIMEOUT` (default: 600s)
- Max instances via `CODEX_MAX_INSTANCES` (default: 10)
- LRU eviction when at capacity
- Background cleanup task every 60s (`CODEX_CLEANUP_INTERVAL`)
- `ThreadSessionManager` for centralized thread→agent mapping

### CodexAppServerInstance (`backend/providers/codex/app_server_instance.py`)

Single `codex app-server` subprocess manager using the official SDK:

- **`start()`** - Launch subprocess via `AppServerClient`, call `initialize()`
- **`create_thread(config)`** - Create new conversation thread
- **`resume_thread(thread_id, config)`** - Resume existing thread
- **`start_turn(thread_id, input_items, config)`** - Execute turn, stream typed `Notification` objects via `asyncio.Queue`
- **`interrupt_turn(thread_id, turn_id)`** - Interrupt ongoing turn
- **`shutdown()`** / **`restart()`** - Lifecycle management

All blocking SDK calls are bridged to async via `asyncio.to_thread()`.

### CodexAppServerClient (`backend/providers/codex/app_server_client.py`)

Implements `AIClient` interface using the App Server pool:

- `connect()` → gets/creates dedicated instance from pool
- `query(message)` → stores pending input (text, images, mixed)
- `receive_response()` → streams turn events in unified internal format
- `interrupt()` → interrupt current turn
- Tracks `thread_id` for session continuity
- Handles `SessionRecoveryError` for invalid threads

### CodexStreamParser (`backend/providers/codex/parser.py`)

Parses internal event format to unified `ParsedStreamMessage`:

- Extracts streaming text (`content.delta`)
- Extracts reasoning/thinking (`thinking.delta`)
- Detects `skip` and `memorize` tool calls
- Captures `thread_id` from `thread.started` events

## SDK Coverage

### Official SDK Surface (`codex-app-server` Python package)

The SDK provides `AppServerClient` with these methods:

| SDK Method | ChitChats Usage | Notes |
|---|---|---|
| `start()` / `close()` | **Used** | Subprocess lifecycle |
| `initialize()` | **Used** | JSON-RPC handshake |
| `thread_start(params)` | **Used** | Create conversation thread |
| `thread_resume(thread_id, params)` | **Used** | Resume existing thread |
| `turn_start(thread_id, input, params)` | **Used** | Execute a turn |
| `turn_interrupt(thread_id, turn_id)` | **Used** | Interrupt ongoing turn |
| `next_notification()` | **Used** | Consume streaming notifications |
| `thread_list(params)` | Not used | List all threads |
| `thread_read(thread_id, include_turns)` | Not used | Read thread history/items |
| `thread_fork(thread_id, params)` | Not used | Fork a thread into a new one |
| `thread_archive(thread_id)` | Not used | Archive a thread |
| `thread_unarchive(thread_id)` | Not used | Unarchive a thread |
| `thread_set_name(thread_id, name)` | Not used | Set thread display name |
| `thread_compact(thread_id)` | Not used | Trigger context compaction |
| `turn_steer(thread_id, turn_id, input)` | Not used | Inject input mid-turn |
| `model_list(include_hidden)` | Not used | List available models |
| `stream_text(thread_id, text, params)` | Not used | Convenience: stream text turn |
| `stream_until_methods(methods)` | Not used | Convenience: collect until method |
| `wait_for_turn_completed(turn_id)` | Not used | Convenience: block until done |
| `request_with_retry_on_overload(...)` | Not used | Auto-retry on `ServerBusyError` |

### SDK Configuration (`AppServerConfig`)

```python
@dataclass
class AppServerConfig:
    codex_bin: str | None = None              # Path to codex binary
    launch_args_override: tuple[str, ...] | None = None  # Full command override
    config_overrides: tuple[str, ...] = ()    # --config key=value pairs
    cwd: str | None = None                    # Working directory
    env: dict[str, str] | None = None         # Environment variables
    client_name: str = "codex_python_sdk"     # Client identifier
    client_title: str = "Codex Python SDK"    # Client display name
    client_version: str = "0.2.0"             # Client version
    experimental_api: bool = True             # Enable experimental API
```

ChitChats uses `launch_args_override` to pass the full command with `--config` flags for feature toggles and MCP server definitions.

### SDK Notification Types

The SDK provides typed Pydantic models for all notification methods. Here is the full registry:

**Handled by ChitChats:**

| Notification Method | SDK Model | Usage |
|---|---|---|
| `item/agentMessage/delta` | `AgentMessageDeltaNotification` | Streaming text output |
| `item/reasoning/textDelta` | `ReasoningTextDeltaNotification` | Streaming thinking/reasoning |
| `item/reasoning/summaryTextDelta` | `ReasoningSummaryTextDeltaNotification` | Reasoning summary |
| `item/completed` | `ItemCompletedNotification` | Completed items (messages, tool calls) |
| `turn/started` | `TurnStartedNotification` | Turn lifecycle start |
| `turn/completed` | `TurnCompletedNotification` | Turn lifecycle end |

**Not handled (available for future integration):**

| Notification Method | SDK Model | Potential Use |
|---|---|---|
| `thread/tokenUsage/updated` | `ThreadTokenUsageUpdatedNotification` | Token tracking, cost display, budget limits |
| `thread/compacted` | `ContextCompactedNotification` | Context window management alerts |
| `thread/name/updated` | `ThreadNameUpdatedNotification` | Auto-generated thread names |
| `thread/status/changed` | `ThreadStatusChangedNotification` | Thread health monitoring |
| `thread/closed` | `ThreadClosedNotification` | Thread lifecycle |
| `thread/archived` | `ThreadArchivedNotification` | Thread archival |
| `turn/plan/updated` | `TurnPlanUpdatedNotification` | Planning steps display |
| `turn/diff/updated` | `TurnDiffUpdatedNotification` | Code diff display |
| `item/started` | `ItemStartedNotification` | Item lifecycle start |
| `item/mcpToolCall/progress` | `McpToolCallProgressNotification` | Tool call progress UI |
| `item/plan/delta` | `PlanDeltaNotification` | Streaming plan text |
| `item/commandExecution/outputDelta` | `CommandExecutionOutputDeltaNotification` | Shell output streaming |
| `item/fileChange/outputDelta` | `FileChangeOutputDeltaNotification` | File change streaming |
| `model/rerouted` | `ModelReroutedNotification` | Model fallback awareness |
| `skills/changed` | `SkillsChangedNotification` | Skills availability updates |
| `hook/started` | `HookStartedNotification` | Hook lifecycle |
| `hook/completed` | `HookCompletedNotification` | Hook lifecycle |
| `thread/realtime/started` | `ThreadRealtimeStartedNotification` | Real-time audio session |
| `thread/realtime/outputAudio/delta` | `ThreadRealtimeOutputAudioDeltaNotification` | Audio streaming |
| `thread/realtime/itemAdded` | `ThreadRealtimeItemAddedNotification` | Real-time items |
| `thread/realtime/closed` | `ThreadRealtimeClosedNotification` | Audio session end |
| `thread/realtime/error` | `ThreadRealtimeErrorNotification` | Audio session error |
| `error` | `ErrorNotification` | General errors |
| `configWarning` | `ConfigWarningNotification` | Config issues |
| `deprecationNotice` | `DeprecationNoticeNotification` | API deprecation warnings |

### SDK Error Hierarchy

```
AppServerError (base)
├── TransportClosedError          # stdio transport closed
└── JsonRpcError                  # JSON-RPC protocol error
    └── AppServerRpcError         # Typed RPC errors
        ├── ParseError            # -32700
        ├── InvalidRequestError   # -32600
        ├── MethodNotFoundError   # -32601
        ├── InvalidParamsError    # -32602
        ├── InternalRpcError      # -32603
        └── ServerBusyError       # -32000..-32099 (retryable)
            └── RetryLimitExceededError
```

ChitChats handles `AppServerError` and `TransportClosedError` for graceful recovery.

The SDK provides `is_retryable_error(exc)` and `retry_on_overload(op, ...)` for automatic retry with exponential backoff on `ServerBusyError`.

## Integration Opportunities

Features available in the SDK but not yet used, ranked by potential value:

### High Value

1. **Token Usage Tracking** (`thread/tokenUsage/updated`)
   - Monitor per-agent token consumption
   - Display cost estimates in UI
   - Set budget limits per room/agent

2. **Context Compaction** (`thread_compact()` + `thread/compacted`)
   - Proactively compact long conversations instead of session recovery
   - Avoid full history rebuild on context overflow

3. **Retry on Overload** (`request_with_retry_on_overload()`)
   - Automatic retry with backoff for transient `ServerBusyError`
   - Currently not used; errors propagate immediately

4. **Model List** (`model_list()`)
   - Dynamically discover available models instead of hardcoding
   - Populate model selector in frontend

### Medium Value

5. **Turn Steering** (`turn_steer()`)
   - Inject additional input while a turn is in progress
   - Enable "real-time correction" UX for agents

6. **Thread Forking** (`thread_fork()`)
   - Branch conversations for "what if" scenarios
   - Enable room cloning with preserved context

7. **Thread Reading** (`thread_read(include_turns=True)`)
   - Read back full conversation history from Codex
   - Useful for debugging or sync verification

8. **MCP Tool Call Progress** (`item/mcpToolCall/progress`)
   - Show progress for long-running tool calls in UI
   - Better UX than "typing..." indicator

### Lower Value (but available)

9. **Thread Listing/Archiving** (`thread_list()`, `thread_archive()`, `thread_unarchive()`)
   - Thread management outside of ChitChats sessions
   - Cleanup/maintenance tooling

10. **Thread Naming** (`thread_set_name()`)
    - Auto-name threads for debugging/monitoring

11. **Plan Display** (`turn/plan/updated`, `item/plan/delta`)
    - Show agent's planning steps (if model supports planning)

12. **Real-time Audio** (`thread/realtime/*`)
    - Voice conversation mode
    - Requires significant frontend work

## Configuration Flow

```
AIClientOptions → CodexAppServerOptions → {
  startup_config: CodexStartupConfig (per-agent, at instance creation)
  turn_config: CodexTurnConfig (per-turn)
}
```

### Startup Configuration (baked into subprocess)

Feature flags via `--config` CLI args:

```
features.shell_tool=false
features.unified_exec=false
features.apply_patch_freeform=false
features.collab=false
tools.view_image=false
web_search=disabled
sandbox=danger-full-access
approval_policy=never
```

MCP servers defined at startup:
```
mcp_servers.action.command=python
mcp_servers.action.args=["-m", "mcp_servers.action_server"]
mcp_servers.action.env.AGENT_NAME=<name>
mcp_servers.guidelines.command=python
mcp_servers.guidelines.args=["-m", "mcp_servers.guidelines_server"]
```

### Turn Configuration (per-turn)

| Field | Description |
|---|---|
| `baseInstructions` | System prompt (developer instructions) |
| `model` | Model override (e.g., "o3", "gpt-4.1") |
| `input` | User message array (text + images) |

## Session Continuity

1. **First turn**: `thread_start(params)` → returns `thread.id`
2. **Subsequent turns**: `turn_start(thread_id, input, params)` → streams notifications
3. **After restart**: `thread_resume(thread_id)` → restores thread state
4. **On failure**: `SessionRecoveryError` → caller rebuilds with full history

Thread IDs stored in `room_agent_sessions.codex_thread_id` column.

## Streaming Events (Internal Format)

The instance converts SDK `Notification` objects to internal event dicts:

| Internal Event | Source SDK Notification | Description |
|---|---|---|
| `{"type": "item.completed", "item": {"type": "agent_message", ...}}` | `AgentMessageDeltaNotification` | Text delta |
| `{"type": "item.completed", "item": {"type": "reasoning", ...}}` | `ReasoningTextDeltaNotification` | Thinking delta |
| `{"type": "item.completed", "item": {"type": "mcp_tool_call", ...}}` | `ItemCompletedNotification` (McpToolCallThreadItem) | Tool call |
| `{"method": "turn/started", "params": {...}}` | `TurnStartedNotification` | Turn lifecycle |
| `{"method": "turn/completed", "params": {...}}` | `TurnCompletedNotification` | Turn lifecycle |
| `{"type": "error", "data": {"message": ...}}` | Error conditions | Error |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `CODEX_IDLE_TIMEOUT` | 600 | Instance idle timeout in seconds |
| `CODEX_MAX_INSTANCES` | 10 | Maximum concurrent app-server instances |
| `CODEX_CLEANUP_INTERVAL` | 60 | Background cleanup interval in seconds |
| `CODEX_MODEL` | (none) | Default model for Codex provider |

## Files Reference

| File | Purpose |
|---|---|
| `backend/providers/codex/__init__.py` | Module exports |
| `backend/providers/codex/app_server_client.py` | AIClient implementation |
| `backend/providers/codex/app_server_instance.py` | Per-agent subprocess wrapper (SDK bridge) |
| `backend/providers/codex/app_server_pool.py` | Instance pool manager (singleton) |
| `backend/providers/codex/constants.py` | Event types, exceptions, factory functions |
| `backend/providers/codex/parser.py` | Stream parser + accumulator |
| `backend/providers/codex/prompts.py` | Prompt loader utility |
| `backend/providers/codex/prompts.yaml` | System prompt definitions |
| `backend/providers/codex/provider.py` | Provider factory (AIProvider interface) |
| `backend/providers/codex/thread_manager.py` | Thread→agent mapping |

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

### Authentication

Codex requires authentication via `codex login` before starting the backend. The provider checks availability via `codex login status`.

## Troubleshooting

### Instance fails to start
Check:
1. Codex CLI is installed: `which codex`
2. Codex is authenticated: `codex login status`
3. `codex-app-server` SDK is installed: `uv run python -c "from codex_app_server import AppServerClient"`

### Instance health issues
The pool automatically creates fresh instances for unhealthy agents. Check logs for:
```
Instance for <agent_key> is no longer healthy, getting fresh instance from pool
```

### Turn timeouts
Default turn timeout is 120 seconds. Check:
- Model availability
- Network connectivity
- MCP server responsiveness

### Session recovery
When a `SessionRecoveryError` occurs, the `ResponseGenerator` rebuilds the full conversation history and starts a fresh thread. Check logs for:
```
SessionRecoveryError: Session recovery needed
```
