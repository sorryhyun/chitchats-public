# Plan: Multi-Provider Support (Claude Code + Codex)

## Goal
Expand ChitChats to support both Claude Code and OpenAI Codex as AI backends, with provider selection at room creation time. **Provider is immutable once the room is created.**

## Architecture Decision: Immutable Provider

**Rationale:** Making provider immutable at room creation simplifies the architecture significantly:

| Aspect | Mutable (Rejected) | Immutable (Chosen) |
|--------|-------------------|-------------------|
| Session tracking | Both `claude_session_id` AND `codex_thread_id` per agent | Single `session_id` per room-agent |
| Session migration | Needed when switching providers | Not needed |
| Frontend UI | Provider toggle in chat room | Provider dropdown at room creation |
| Edge cases | Mixed provider messages, context loss | None |
| `RoomAgentSession` | 2 session fields + migration logic | 1 session field |

**Trade-off:** User must create a new room to use a different provider. This is acceptable because:
1. Conversations are inherently provider-specific (different context windows, capabilities)
2. Switching mid-conversation would lose context anyway
3. Simpler UX - users know what type of room they're in

---

## Completed Phases

### Phase 1-3: Provider Abstraction Layer ✅
- **Provider Abstraction Layer**: `backend/providers/` with base interfaces, factory, Claude and Codex implementations
- **Backend API Updates**: `provider` field in Message, `default_provider` in Room (set at creation only)
- **Database Migrations**: All new columns added automatically on startup

### Phase 4: Backend Cleanup (Immutability Enforcement) ✅
- Fixed `create_room` to set `default_provider` from `RoomCreate`
- Removed `default_provider` from `RoomUpdate` schema (immutable after creation)
- Session management uses room's provider

### Phase 5: Frontend Provider Selection ✅
- Added provider toggle (Claude/Codex) to Create Room dialog
- Provider indicator badge displayed in room list (amber for Claude, green for Codex)
- Provider badge shown in room header (RoomBadges component)

### Phase 6: AgentManager Provider Routing ✅
**Completed:** AgentManager now routes to the correct provider based on room settings.

**Changes:**
- `backend/sdk/manager.py`: Added provider routing in `generate_sdk_response()`
- Codex requests route to new `_generate_codex_response()` method
- Claude requests continue using existing SDK implementation

**Key Code:**
```python
# In generate_sdk_response()
provider_type = context.provider or "claude"
provider = get_provider(provider_type)

if provider.provider_type == ProviderType.CODEX:
    async for event in self._generate_codex_response(context, provider):
        yield event
    return
# ... existing Claude SDK logic
```

### Phase 7: MCP Tools for Codex ✅
**Completed:** Full MCP integration for Codex CLI.

**New Files:**
| File | Purpose |
|------|---------|
| `backend/providers/codex/mcp_config.py` | Generates `~/.codex/config.toml` for MCP servers |
| `backend/mcp_servers/__init__.py` | Package for standalone MCP servers |
| `backend/mcp_servers/action_server.py` | Skip, memorize, recall tools (JSON-RPC over stdio) |
| `backend/mcp_servers/guidelines_server.py` | Read guidelines, anthropic classification tools |

**MCP Config Generation:**
- Generates TOML config at `~/.codex/config.toml`
- Configures `chitchats_action` and `chitchats_guidelines` servers
- Passes agent context via environment variables

**Codex MCP Config Format:**
```toml
[mcp_servers.chitchats_action]
command = "python"
args = ["-m", "mcp_servers.action_server"]
cwd = "/path/to/backend"
env = { "AGENT_NAME" = "AgentName", "AGENT_GROUP" = "default" }

[mcp_servers.chitchats_guidelines]
command = "python"
args = ["-m", "mcp_servers.guidelines_server"]
cwd = "/path/to/backend"
env = { "AGENT_NAME" = "AgentName" }
```

### Phase 8: Provider Health Check ✅
- Added `/debug/providers` endpoint - lists supported providers
- Added `/debug/providers/health` endpoint - checks availability of each provider
- Endpoints require admin authentication

---

## Implementation Details

### Provider Flow (Codex)

```
Room (provider="codex")
    ↓
ResponseGenerator.generate_response()
    ↓ reads room.default_provider
AgentManager.generate_sdk_response(context)
    ↓ checks context.provider
get_provider("codex") → CodexProvider
    ↓
_generate_codex_response(context, provider)
    ↓
provider.build_options() → CodexOptions
    ↓ generates MCP config
provider.create_client() → CodexClient
    ↓
CodexClient.query() → subprocess: codex exec ...
    ↓
CodexStreamParser.parse_message() → ParsedStreamMessage
    ↓
Yields streaming events back to ResponseGenerator
```

### Session/Thread Management

- **Claude**: Uses `claude_session_id` for SDK session resume
- **Codex**: Uses `codex_thread_id` for CLI thread resume
- Thread ID extracted from `thread.started` event
- Resume command: `codex exec resume <thread-id>`

### Tool Parity

| Tool | Claude | Codex |
|------|--------|-------|
| skip | MCP via SDK hooks | MCP via standalone server |
| memorize | MCP via SDK hooks | MCP via standalone server |
| recall | MCP via SDK hooks | MCP via standalone server |
| guidelines | MCP via SDK | MCP via standalone server |
| anthropic | MCP via SDK hooks | MCP via standalone server |

---

## Verification

**Install Dependencies:**
```bash
uv sync  # Installs toml>=0.10.2
```

**Provider Health Check:**
```bash
curl http://localhost:8000/debug/providers/health
# Returns: {"providers": {"claude": {"available": true}, "codex": {"available": true/false}}}
```

**Create Codex Room:**
```bash
curl -X POST http://localhost:8000/api/rooms \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name": "Test Codex", "default_provider": "codex"}'
```

**Check Logs for Codex Routing:**
```
🤖 [Codex] Agent generating response | Session: NEW | Task: room_1_agent_1
📤 [Codex] Sending message | Task: room_1_agent_1 | Length: 500
Running Codex: codex exec --json --full-auto ...
✅ [Codex] Response generated | Length: 200 chars | Session: thread_abc123
```

**Frontend Testing:**
1. Open "Create Room" dialog
2. Select "Codex" provider (green button)
3. Create room and add agents
4. Send a message
5. Verify response comes from Codex (check backend logs for `[Codex]` prefix)

---

## Dependencies

- `toml>=0.10.2` - For MCP config TOML generation
- Codex CLI must be installed and authenticated (`codex auth login`)
