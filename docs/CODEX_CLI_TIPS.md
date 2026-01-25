# Codex CLI Usage Tips for Community

This guide shares practical tips and lessons learned from integrating Codex CLI into a production multi-agent chat application. These insights can help you build better applications with Codex.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Architecture Patterns](#architecture-patterns)
3. [App Server Mode](#app-server-mode)
4. [Session Management](#session-management)
5. [MCP Server Integration](#mcp-server-integration)
6. [Configuration Tips](#configuration-tips)
7. [Error Handling & Recovery](#error-handling--recovery)
8. [Performance Optimization](#performance-optimization)
9. [Platform-Specific Notes](#platform-specific-notes)
10. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Installation & Authentication

```bash
# Install globally via npm
npm install -g @openai/codex

# Authenticate (one-time, opens browser)
codex login

# Verify authentication
codex login status
```

### Programmatic Authentication Check

```python
import asyncio
import shutil

async def check_codex_available() -> bool:
    """Check if Codex CLI is installed and authenticated."""
    codex_path = shutil.which("codex")
    if not codex_path:
        return False

    process = await asyncio.create_subprocess_exec(
        "codex", "login", "status",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await process.wait()
    return process.returncode == 0
```

---

## Architecture Patterns

### Per-Agent Instance Pattern

For multi-agent applications, use **dedicated app-server instances per agent**:

```
CodexAppServerPool (singleton)
├── Agent "Alice" → CodexAppServerInstance (port 8001)
├── Agent "Bob"   → CodexAppServerInstance (port 8002)
└── Agent "Carol" → CodexAppServerInstance (port 8003)
```

**Benefits:**
- Complete isolation between agents
- Agent-specific MCP configurations
- No cross-contamination of context
- Independent failure recovery

### Thread Affinity

Always route follow-up messages to the same instance using thread IDs:

```python
# Store thread_id in database
thread_id = await instance.create_thread(config)
await db.save_session(agent_id, room_id, thread_id)

# Later: retrieve and route to same thread
thread_id = await db.get_session(agent_id, room_id)
await instance.resume_thread(thread_id, config)
```

---

## App Server Mode

### Why App Server Mode?

The `codex app-server` command provides significant advantages over spawning `codex` processes per query:

| Approach | Startup Overhead | Memory | Session Persistence |
|----------|-----------------|--------|---------------------|
| `codex` per query | ~2-3 seconds | High (new process each time) | None |
| `codex app-server` | Once at startup | Shared | Thread-based |

### Starting App Server

```bash
# Basic startup
codex app-server

# With configuration overrides
codex app-server -c "features.shell_tool=false" -c "web_search=disabled"
```

### JSON-RPC 2.0 Protocol

App server uses JSON-RPC 2.0 over stdio (without the `jsonrpc` field):

```python
# Request format
{"method": "thread/start", "params": {...}, "id": 1}

# Response format
{"result": {...}, "id": 1}

# Notification format (streaming events, no id)
{"method": "item/agentMessage/delta", "params": {...}}
```

### Key Methods

| Method | Purpose |
|--------|---------|
| `thread/start` | Create new conversation thread |
| `thread/resume` | Resume existing thread |
| `turn/start` | Start a new turn in thread |
| `turn/interrupt` | Interrupt ongoing turn |

### Streaming Events

```python
# Event types to handle
TURN_STARTED = "turn/started"
TURN_COMPLETED = "turn/completed"
ITEM_COMPLETED = "item/completed"
AGENT_MESSAGE_DELTA = "item/agentMessage/delta"  # Text streaming
REASONING_DELTA = "item/reasoning/textDelta"      # Thinking streaming
MCP_TOOL_CALL_COMPLETED = "item/mcpToolCall/completed"
```

---

## Session Management

### Thread Lifecycle

```python
# 1. Create thread (first interaction)
params = {
    "cwd": "/path/to/workspace",
    "model": "gpt-5.2",
    "baseInstructions": "You are a helpful assistant...",
    "sandbox": "danger-full-access",  # or "workspace-write", "read-only"
    "approvalPolicy": "never",        # or "on-request", "on-failure"
}
thread_id = await send_request("thread/start", params)

# 2. Start turn (send message)
params = {
    "threadId": thread_id,
    "input": [{"type": "text", "text": "Hello!"}],
    "baseInstructions": system_prompt,  # Can override per-turn
    "model": "gpt-5.2",                 # Can override per-turn
}
async for event in stream_request("turn/start", params):
    handle_event(event)

# 3. Resume thread (subsequent sessions)
await send_request("thread/resume", {"threadId": thread_id, ...})
```

### Database Persistence

Store thread IDs for session continuity across restarts:

```sql
-- Add to your room_agents or sessions table
ALTER TABLE room_agents ADD COLUMN codex_thread_id VARCHAR(255);
```

```python
# Save after creating thread
await crud.update_room_agent_session(db, room_id, agent_id, "codex", thread_id)

# Retrieve for continuation
thread_id = await crud.get_room_agent_session(db, room_id, agent_id, "codex")
```

---

## MCP Server Integration

### Configuring MCP Servers at Startup

Unlike per-turn tool configuration, MCP servers must be configured at app-server startup:

```python
# Build MCP config
mcp_servers = {
    "action_server": {
        "command": "python",
        "args": ["-m", "mcp_servers.action"],
        "env": {
            "AGENT_NAME": agent_name,
            "ROOM_ID": str(room_id),
        }
    },
    "guidelines_server": {
        "command": "python",
        "args": ["-m", "mcp_servers.guidelines"],
    }
}

# Pass via startup config
startup_config = CodexStartupConfig(mcp_servers=mcp_servers)
cli_args = startup_config.to_cli_args()
```

### Environment Isolation for MCP

Use separate Python environments to avoid dependency conflicts:

```python
def get_python_executable():
    """Prefer virtualenv Python for MCP servers."""
    venv_python = Path(sys.prefix) / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable
```

---

## Configuration Tips

### Disable Unwanted Features

For chat/roleplay applications, disable shell and file access:

```python
config_overrides = {
    "features.shell_tool": False,        # No shell execution
    "features.unified_exec": False,      # No unified execution
    "features.apply_patch_freeform": False,
    "features.collab": False,
    "tools.view_image": False,           # Receive images directly instead
    "web_search": "disabled",
}

# Convert to CLI args
cli_args = ["-c", f"{k}={v}" for k, v in config_overrides.items()]
```

### Disable Skills Injection

Codex auto-injects instructions from `~/.codex/skills/` which can break character immersion:

```bash
# Disable skills (restrict permissions)
chmod 000 ~/.codex/skills

# Re-enable later
chmod 755 ~/.codex/skills
```

### Isolate Working Directory

Prevent Codex from reading project-specific files like `AGENTS.md`:

```python
import tempfile
from pathlib import Path

def get_isolated_working_dir() -> str:
    """Use empty temp directory to isolate from project files."""
    temp_dir = Path(tempfile.gettempdir()) / "codex-empty"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return str(temp_dir)
```

### Prevent Browser Auto-Open

When spawning subprocesses, prevent browser opening:

```python
import os

subprocess_env = {**os.environ, "BROWSER": ""}
process = await asyncio.create_subprocess_exec(
    "codex", "app-server",
    env=subprocess_env,
    ...
)
```

---

## Error Handling & Recovery

### Session Recovery Pattern

When sessions become invalid (e.g., MCP server restart), recover gracefully:

```python
class SessionRecoveryError(Exception):
    """Raised when session needs full history restart."""
    def __init__(self, old_thread_id: str):
        self.old_thread_id = old_thread_id
        super().__init__("Session recovery needed")

async def generate_response(context):
    try:
        async for event in start_turn(context.thread_id, context.message):
            yield event
    except SessionRecoveryError as e:
        # Rebuild with full conversation history
        full_history = await get_full_conversation(context.room_id)
        context.thread_id = None  # Force new thread
        context.messages = full_history

        async for event in start_turn(None, context):
            yield event
```

### Instance Health Monitoring

```python
class CodexAppServerInstance:
    @property
    def is_healthy(self) -> bool:
        """Check if server process is still running."""
        return (
            self._transport is not None
            and self._transport.is_healthy
        )

# In pool manager
async def get_or_create_instance(self, agent_key: str):
    instance = self._instances.get(agent_key)

    if instance and instance.is_healthy:
        instance.touch()  # Update last access time
        return instance

    # Unhealthy or missing - recreate
    if instance:
        await instance.shutdown()
        del self._instances[agent_key]

    return await self._create_instance(agent_key)
```

### Graceful Shutdown

```python
async def shutdown_pool(timeout: float = 10.0):
    """Shutdown all instances with timeout."""
    tasks = [
        asyncio.create_task(instance.shutdown())
        for instance in self._instances.values()
    ]

    if tasks:
        done, pending = await asyncio.wait(tasks, timeout=timeout)

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
```

---

## Performance Optimization

### Pool Configuration

```bash
# Environment variables for tuning
export CODEX_MAX_INSTANCES=10      # Max concurrent app-server instances
export CODEX_IDLE_TIMEOUT=600      # Seconds before idle instance shutdown (10 min)
export CODEX_CLEANUP_INTERVAL=60   # Seconds between cleanup checks
```

### LRU Eviction

When hitting max instances, evict least-recently-used:

```python
def _evict_lru_instance(self):
    """Evict the least recently used instance."""
    if not self._instances:
        return None

    oldest_key = min(
        self._instances.keys(),
        key=lambda k: self._instances[k].last_used
    )

    instance = self._instances.pop(oldest_key)
    asyncio.create_task(instance.shutdown())
    return oldest_key
```

### Large Message Handling

For base64 images, use chunked writes:

```python
CHUNK_SIZE = 1024 * 1024  # 1MB chunks

async def write_large_message(self, data: bytes):
    """Write large messages in chunks to avoid buffer issues."""
    for i in range(0, len(data), CHUNK_SIZE):
        chunk = data[i:i + CHUNK_SIZE]
        self._process.stdin.write(chunk)
        await self._process.stdin.drain()
```

---

## Platform-Specific Notes

### Windows Support

For Windows deployment, consider bundling the Codex binary:

```python
def find_codex_executable() -> str:
    """Find Codex executable with bundled binary fallback."""
    # Check for bundled binary first
    bundled_paths = [
        "bin/codex-x86_64-pc-windows-msvc.exe",  # Windows
        "bin/codex-aarch64-apple-darwin",         # macOS ARM
        "bin/codex-x86_64-unknown-linux-gnu",     # Linux
    ]

    for path in bundled_paths:
        if Path(path).exists():
            return str(Path(path).absolute())

    # Fall back to system PATH
    return shutil.which("codex") or "codex"
```

### macOS Considerations

On macOS, ensure proper code signing if distributing bundled binaries:

```bash
# Remove quarantine attribute
xattr -d com.apple.quarantine ./bin/codex-aarch64-apple-darwin
```

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "command not found: codex" | Not installed | `npm install -g @openai/codex` |
| Authentication fails | Token expired | Run `codex login` again |
| Skills interfere with prompts | Auto-injection | `chmod 000 ~/.codex/skills` |
| Picks up AGENTS.md | Wrong cwd | Use isolated temp directory |
| Browser opens on startup | Default behavior | Set `BROWSER=""` in env |
| Session invalid errors | MCP restart | Implement SessionRecoveryError pattern |

### Debug Logging

Enable verbose logging for troubleshooting:

```python
import logging

# Enable debug logging
logging.getLogger("codex").setLevel(logging.DEBUG)

# Log all JSON-RPC messages
async def log_message(direction: str, msg: dict):
    logger.debug(f"[{direction}] {json.dumps(msg, indent=2)}")
```

### Health Check Endpoint

Add a health check for monitoring:

```python
@app.get("/health/codex")
async def codex_health():
    pool = await CodexAppServerPool.get_instance()
    stats = pool.get_stats()

    return {
        "status": "healthy" if stats["healthy_count"] > 0 else "degraded",
        "active_instances": stats["active_instances"],
        "healthy_instances": stats["healthy_count"],
        "total_threads": stats["total_threads"],
    }
```

---

## Quick Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CODEX_MAX_INSTANCES` | 10 | Maximum app-server instances |
| `CODEX_IDLE_TIMEOUT` | 600 | Seconds before idle shutdown |
| `CODEX_CLEANUP_INTERVAL` | 60 | Cleanup check interval |
| `CODEX_MODEL` | gpt-5.2 | Default model |
| `BROWSER` | (system) | Set to "" to prevent auto-open |

### Key Files in ChitChats Implementation

| File | Purpose |
|------|---------|
| `backend/providers/codex/app_server_pool.py` | Singleton pool manager |
| `backend/providers/codex/app_server_instance.py` | Single instance lifecycle |
| `backend/providers/codex/transport.py` | JSON-RPC transport layer |
| `backend/providers/codex/parser.py` | Stream event parser |
| `backend/providers/codex/constants.py` | Event types & exceptions |
| `backend/providers/mcp_config.py` | MCP configuration builder |

---

## Summary

Key takeaways for using Codex CLI effectively:

1. **Use App Server mode** for production - avoid per-query process spawning
2. **Implement per-agent instances** for multi-agent applications
3. **Persist thread IDs** in database for session continuity
4. **Configure MCP at startup** - tools can't be changed per-turn
5. **Disable skills injection** for roleplay/character applications
6. **Isolate working directory** to prevent unwanted file pickup
7. **Implement session recovery** for graceful error handling
8. **Monitor instance health** and implement auto-recovery
9. **Tune pool settings** based on your concurrency needs

For the complete implementation, see the [ChitChats backend/providers/codex/](../backend/providers/codex/) directory.
