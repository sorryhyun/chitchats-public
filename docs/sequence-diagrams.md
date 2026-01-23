# Chat Orchestration Sequence Diagrams

This document describes the message flow for both Claude SDK and Codex providers.

## Overview

ChitChats supports two AI providers through a unified abstraction layer:

- **Claude SDK**: Uses Claude Agent SDK via Claude Code CLI (subprocess-based)
- **Codex**: Uses Codex via app server pool (persistent connections)

Both providers share the same orchestration logic but differ in their client implementations.

---

## Claude SDK Flow

```mermaid
sequenceDiagram
    autonumber
    participant FE as Frontend
    participant API as REST API
    participant CO as ChatOrchestrator
    participant RG as ResponseGenerator
    participant AM as AgentManager
    participant Pool as ClaudeClientPool
    participant Client as ClaudeClient
    participant SDK as ClaudeSDKClient<br/>(subprocess)

    FE->>API: POST /api/rooms/{id}/messages
    activate API
    API->>API: save message to DB
    API->>CO: handle_user_message()
    activate CO

    CO->>AM: interrupt_room(room_id)
    Note right of AM: Save partial responses<br/>before interrupting

    CO->>CO: create TapeExecutor
    CO->>RG: execute(tape)
    activate RG

    RG->>RG: build_conversation_context()
    RG->>RG: build_system_prompt()
    RG->>AM: generate_sdk_response(context)
    activate AM

    AM->>Pool: get_or_create(task_id, options)
    activate Pool

    alt Client exists in pool
        Pool-->>AM: (existing_client, false)
    else Create new client
        Pool->>Client: create
        Client->>SDK: create with options
        SDK->>SDK: spawn subprocess
        Client->>SDK: connect()
        Pool-->>AM: (new_client, true)
    end
    deactivate Pool

    AM->>Client: query(message)
    Client->>SDK: query(message)

    AM->>Client: receive_response()
    activate Client

    loop Streaming Events
        SDK-->>Client: AssistantMessage / ToolUse / ToolResult
        Client-->>AM: parsed event
        AM->>AM: update streaming_state
        AM-->>RG: yield {type: content_delta}
        AM-->>RG: yield {type: thinking_delta}
    end

    Client-->>AM: stream complete
    deactivate Client

    AM-->>RG: yield {type: stream_end}
    deactivate AM

    RG->>RG: check interruption
    RG->>API: save_agent_message()
    deactivate RG

    CO-->>API: processing complete
    deactivate CO
    deactivate API
```

---

## Codex App Server Flow

```mermaid
sequenceDiagram
    autonumber
    participant FE as Frontend
    participant API as REST API
    participant CO as ChatOrchestrator
    participant RG as ResponseGenerator
    participant AM as AgentManager
    participant Pool as CodexClientPool
    participant Client as CodexAppServerClient
    participant SP as CodexAppServerPool<br/>(singleton)
    participant Server as App Server<br/>Instance

    FE->>API: POST /api/rooms/{id}/messages
    activate API
    API->>API: save message to DB
    API->>CO: handle_user_message()
    activate CO

    Note over CO,AM: Same orchestration logic as Claude

    CO->>RG: execute(tape)
    activate RG

    RG->>AM: generate_sdk_response(context)
    activate AM

    AM->>Pool: get_or_create(task_id, options)
    activate Pool

    alt Client exists in pool
        Pool-->>AM: (existing_client, false)
    else Create new client
        Pool->>Client: create
        Client->>SP: connect()
        SP->>SP: ensure_started()
        Pool-->>AM: (new_client, true)
    end
    deactivate Pool

    AM->>Client: query(message)
    Client->>Client: store pending_message

    AM->>Client: receive_response()
    activate Client

    Client->>SP: call_codex(prompt, config, thread_id)
    activate SP

    SP->>SP: route by thread_id affinity
    SP->>Server: start_turn (JSON-RPC)
    activate Server
    Server->>Server: call Codex API
    Server-->>SP: streaming notifications
    deactivate Server

    SP-->>Client: {thread_id, content[]}
    deactivate SP

    Note right of Client: Convert batch to<br/>streaming events

    loop Emit Events from Batch
        Client-->>AM: thread_started / agent_message / reasoning
    end
    deactivate Client

    AM-->>RG: yield {type: stream_end}
    deactivate AM

    RG->>API: save_agent_message()
    deactivate RG

    CO-->>API: processing complete
    deactivate CO
    deactivate API
```

---

## Interruption Flow

When a new user message arrives while agents are processing:

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant API as REST API
    participant CO as ChatOrchestrator
    participant AM as AgentManager
    participant Client as AIClient
    participant DB as Database

    Note over CO,Client: Agents currently generating responses

    User->>API: POST /api/rooms/{id}/messages
    activate API

    API->>DB: save user message
    API->>CO: handle_user_message()
    activate CO

    CO->>CO: record last_user_message_time

    rect rgb(255, 230, 230)
        Note over CO,AM: Capture Partial Responses
        CO->>AM: get_and_clear_streaming_state(room_id)
        AM-->>CO: {agent_id: {thinking_text, response_text}}
    end

    rect rgb(255, 200, 200)
        Note over CO,Client: Interrupt Active Agents
        CO->>AM: interrupt_room(room_id)
        loop For each active client
            AM->>Client: interrupt()
            AM->>AM: del active_clients[task_id]
        end
    end

    CO->>CO: task.cancel()

    opt Has partial content
        CO->>DB: save partial responses
    end

    rect rgb(200, 255, 200)
        Note over CO: Start New Processing
        CO->>CO: create new processing_task
    end

    CO-->>API: done
    deactivate CO
    deactivate API
```

---

## Session Persistence

```mermaid
sequenceDiagram
    autonumber
    participant RG as ResponseGenerator
    participant DB as Database
    participant Claude as ClaudeClient
    participant Codex as CodexMCPClient

    rect rgb(230, 230, 255)
        Note over RG,Codex: First Message (No Session)
        RG->>DB: get_room_agent_session(room, agent, provider)
        DB-->>RG: null

        alt Claude Provider
            RG->>Claude: options.resume = null
            Claude->>Claude: creates new session
            Claude-->>RG: stream_end {session_id: "uuid-xxx"}
        else Codex Provider
            RG->>Codex: options.thread_id = null
            Codex->>Codex: creates new thread
            Codex-->>RG: turn_started {thread_id: "thread-xxx"}
        end

        RG->>DB: update_room_agent_session(new_id)
    end

    rect rgb(230, 255, 230)
        Note over RG,Codex: Subsequent Messages (Resume)
        RG->>DB: get_room_agent_session(room, agent, provider)
        DB-->>RG: "existing-session-id"

        alt Claude Provider
            RG->>Claude: options.resume = "existing-session-id"
            Note right of Claude: Resumes conversation<br/>context from session
        else Codex Provider
            RG->>Codex: options.thread_id = "existing-session-id"
            Note right of Codex: Routes to same app server<br/>instance via affinity
        end
    end
```

---

## Provider Comparison

| Aspect | Claude SDK | Codex |
|--------|-----------|-------|
| **Connection** | Subprocess per client | Shared app server pool |
| **Streaming** | True streaming | JSON-RPC streaming notifications |
| **Session ID** | `options.resume` (UUID) | `thread_id` |
| **Pool Limit** | 10 concurrent | Configurable (default: 3) |
| **Server Mgmt** | Per-client subprocess | Singleton pool w/ instances |
| **Tool Capture** | PostToolUse hooks | Stream parsing |
| **Parallelism** | Multiple subprocesses | Multiple app server instances |

---

## Unified Event Types

Both providers emit the same event types for downstream processing:

```json
{"type": "stream_start", "temp_id": "temp_room1_agent1_abc123"}

{"type": "content_delta", "delta": "Hello, ", "temp_id": "..."}

{"type": "thinking_delta", "delta": "I should greet...", "temp_id": "..."}

{
  "type": "stream_end",
  "temp_id": "...",
  "response_text": "Hello, how are you?",
  "thinking_text": "I should greet the user warmly...",
  "session_id": "uuid-or-thread-id",
  "memory_entries": [],
  "anthropic_calls": [],
  "skipped": false
}
```

---

## Key Components

### Shared (Provider-Agnostic)

| Component | File |
|-----------|------|
| `ChatOrchestrator` | `backend/orchestration/orchestrator.py` |
| `ResponseGenerator` | `backend/orchestration/response_generator.py` |
| `AgentManager` | `backend/core/manager.py` |
| `AIClient` / `AIProvider` | `backend/providers/base.py` |

### Claude SDK Provider

| Component | File |
|-----------|------|
| `ClaudeProvider` | `backend/providers/claude/provider.py` |
| `ClaudeClient` | `backend/providers/claude/client.py` |
| `ClaudeClientPool` | `backend/providers/claude/pool.py` |
| `ClaudeStreamParser` | `backend/providers/claude/parser.py` |

### Codex Provider

| Component | File |
|-----------|------|
| `CodexProvider` | `backend/providers/codex/provider.py` |
| `CodexAppServerClient` | `backend/providers/codex/app_server_client.py` |
| `CodexClientPool` | `backend/providers/codex/pool.py` |
| `CodexAppServerPool` | `backend/providers/codex/app_server_pool.py` |
| `CodexAppServerInstance` | `backend/providers/codex/app_server_instance.py` |
| `CodexAppServerParser` | `backend/providers/codex/app_server_parser.py` |
