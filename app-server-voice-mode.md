# Voice Mode via the Codex App-Server (v2 API)

> **Status**: Experimental — all types and methods are subject to change.

This guide explains how to integrate Codex's realtime voice mode into your
own client application using the `codex-app-server` JSON-RPC v2 API. The
app-server handles the backend websocket connection to the realtime model;
your client is responsible for capturing microphone audio, playing back
assistant audio, and driving the session lifecycle over JSON-RPC.

## Prerequisites

1. **Enable the feature flag.** Realtime conversation is gated behind an
   `UnderDevelopment` feature flag. Add the following to
   `~/.codex/config.toml` (or the project-level `.codex/config.toml`):

   ```toml
   [features]
   realtime_conversation = true
   ```

2. **Start the app-server.** The app-server binary is `codex app-server`.
   It communicates over JSON-RPC 2.0 (line-delimited) on stdio.

3. **Create a thread.** Before starting a realtime session you need an
   active thread (conversation). Use the `thread/start` method to obtain a
   `threadId`.

### Optional config overrides

For development and testing you can override the websocket endpoint and the
backend system prompt in `config.toml`:

```toml
# Custom websocket base URL (e.g., a local mock server)
experimental_realtime_ws_base_url = "http://127.0.0.1:8011"

# Override the backend system prompt sent to the realtime model
experimental_realtime_ws_backend_prompt = "You are a pirate."
```

## Session Lifecycle

A realtime session follows this sequence:

```
Client                            App-Server                   Model Backend
  │                                   │                              │
  │── thread/realtime/start ─────────>│                              │
  │                                   │── open websocket ───────────>│
  │<── thread/realtime/started ───────│<── session created ──────────│
  │                                   │                              │
  │── thread/realtime/appendAudio ──>│── audio frame ──────────────>│
  │── thread/realtime/appendText ───>│── text input ───────────────>│
  │                                   │                              │
  │<── thread/realtime/outputAudio/delta ─│<── audio response ───────│
  │<── thread/realtime/itemAdded ─────│<── transcript/item ──────────│
  │<── thread/realtime/error ─────────│<── error ────────────────────│
  │                                   │                              │
  │── thread/realtime/stop ──────────>│── close websocket ──────────>│
  │<── thread/realtime/closed ────────│                              │
```

## JSON-RPC Methods (client -> server)

All request params use **camelCase** field names.

### `thread/realtime/start`

Opens a realtime session on an existing thread.

```jsonc
// Request
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "thread/realtime/start",
  "params": {
    "threadId": "019bc...",
    "prompt": "You are a helpful voice assistant.",
    "sessionId": null  // optional: resume a previous session
  }
}

// Response
{ "jsonrpc": "2.0", "id": 1, "result": {} }
```

| Field       | Type             | Description                                    |
|-------------|------------------|------------------------------------------------|
| `threadId`  | `string`         | The thread to attach the realtime session to.  |
| `prompt`    | `string`         | Backend/system prompt for the realtime model.  |
| `sessionId` | `string \| null` | Optional session ID to resume a prior session. |

### `thread/realtime/appendAudio`

Sends a chunk of audio input (e.g., from the user's microphone).

```jsonc
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "thread/realtime/appendAudio",
  "params": {
    "threadId": "019bc...",
    "audio": {
      "data": "BQYH...",          // base64-encoded PCM16 samples
      "sampleRate": 24000,
      "numChannels": 1,
      "samplesPerChannel": 480    // optional
    }
  }
}
```

| Field                       | Type             | Description                                |
|-----------------------------|------------------|--------------------------------------------|
| `audio.data`                | `string`         | Base64-encoded PCM16 (little-endian) audio |
| `audio.sampleRate`          | `number`         | Sample rate in Hz (typically 24000)        |
| `audio.numChannels`         | `number`         | Number of channels (typically 1)           |
| `audio.samplesPerChannel`   | `number \| null` | Samples per channel in this chunk          |

### `thread/realtime/appendText`

Sends text input into the realtime session (useful for typed messages during
a voice conversation).

```jsonc
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "thread/realtime/appendText",
  "params": {
    "threadId": "019bc...",
    "text": "What's the weather like?"
  }
}
```

### `thread/realtime/stop`

Closes the realtime session.

```jsonc
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "thread/realtime/stop",
  "params": {
    "threadId": "019bc..."
  }
}
```

## Notifications (server -> client)

While the realtime session is active, the server pushes these JSON-RPC
notifications. All notification params use **camelCase**.

### `thread/realtime/started`

Emitted once the backend session is established.

```jsonc
{
  "jsonrpc": "2.0",
  "method": "thread/realtime/started",
  "params": {
    "threadId": "019bc...",
    "sessionId": "sess_abc123"  // may be null
  }
}
```

Store the `sessionId` if you want to resume the session later.

### `thread/realtime/outputAudio/delta`

Streamed audio output from the assistant. Decode and enqueue these chunks
for playback.

```jsonc
{
  "jsonrpc": "2.0",
  "method": "thread/realtime/outputAudio/delta",
  "params": {
    "threadId": "019bc...",
    "audio": {
      "data": "base64...",
      "sampleRate": 24000,
      "numChannels": 1,
      "samplesPerChannel": 480
    }
  }
}
```

### `thread/realtime/itemAdded`

Conversation items such as transcripts, function calls, or messages. The
`item` field is a raw JSON object whose schema depends on the backend.

```jsonc
{
  "jsonrpc": "2.0",
  "method": "thread/realtime/itemAdded",
  "params": {
    "threadId": "019bc...",
    "item": { /* backend-specific conversation item */ }
  }
}
```

### `thread/realtime/error`

An error occurred in the realtime stream.

```jsonc
{
  "jsonrpc": "2.0",
  "method": "thread/realtime/error",
  "params": {
    "threadId": "019bc...",
    "message": "rate_limit_exceeded"
  }
}
```

### `thread/realtime/closed`

The realtime session has ended.

```jsonc
{
  "jsonrpc": "2.0",
  "method": "thread/realtime/closed",
  "params": {
    "threadId": "019bc...",
    "reason": "requested"  // or "transport_closed", or null
  }
}
```

## Audio Format

All audio exchanged through the API uses the same format:

| Property             | Value                                     |
|----------------------|-------------------------------------------|
| Encoding             | PCM16 signed, little-endian               |
| Wire encoding        | Base64 string in the `data` field         |
| Sample rate          | 24000 Hz (match what the backend expects) |
| Channels             | 1 (mono)                                  |
| Chunk size           | Flexible; 20ms frames (480 samples) work well for low latency |

### Encoding audio (pseudocode)

```python
import base64, struct

def encode_audio_chunk(pcm16_samples: list[int]) -> dict:
    raw = struct.pack(f"<{len(pcm16_samples)}h", *pcm16_samples)
    return {
        "data": base64.b64encode(raw).decode("ascii"),
        "sampleRate": 24000,
        "numChannels": 1,
        "samplesPerChannel": len(pcm16_samples),
    }
```

### Decoding audio (pseudocode)

```python
import base64, struct

def decode_audio_chunk(chunk: dict) -> list[int]:
    raw = base64.b64decode(chunk["data"])
    count = len(raw) // 2
    return list(struct.unpack(f"<{count}h", raw))
```

## Complete Example Session

Below is a minimal end-to-end flow showing every JSON-RPC message
exchanged. Assume the client has already created a thread and holds a
`threadId`.

```jsonc
// 1. Start realtime session
// -> Client sends:
{"jsonrpc":"2.0","id":1,"method":"thread/realtime/start","params":{"threadId":"t1","prompt":"You are a helpful assistant."}}

// <- Server responds:
{"jsonrpc":"2.0","id":1,"result":{}}

// <- Server notifies session is ready:
{"jsonrpc":"2.0","method":"thread/realtime/started","params":{"threadId":"t1","sessionId":"sess_1"}}

// 2. Stream microphone audio (repeat for each chunk)
// -> Client sends:
{"jsonrpc":"2.0","id":2,"method":"thread/realtime/appendAudio","params":{"threadId":"t1","audio":{"data":"BQYH...","sampleRate":24000,"numChannels":1,"samplesPerChannel":480}}}
{"jsonrpc":"2.0","id":3,"method":"thread/realtime/appendAudio","params":{"threadId":"t1","audio":{"data":"CwkN...","sampleRate":24000,"numChannels":1,"samplesPerChannel":480}}}

// 3. Server streams back assistant audio + transcripts
// <- Server notifies:
{"jsonrpc":"2.0","method":"thread/realtime/outputAudio/delta","params":{"threadId":"t1","audio":{"data":"AQID...","sampleRate":24000,"numChannels":1,"samplesPerChannel":480}}}
{"jsonrpc":"2.0","method":"thread/realtime/itemAdded","params":{"threadId":"t1","item":{"type":"message","role":"assistant","content":[{"type":"text","text":"Hello! How can I help?"}]}}}

// 4. Optionally send text during voice conversation
// -> Client sends:
{"jsonrpc":"2.0","id":4,"method":"thread/realtime/appendText","params":{"threadId":"t1","text":"Never mind, thanks."}}

// 5. End session
// -> Client sends:
{"jsonrpc":"2.0","id":5,"method":"thread/realtime/stop","params":{"threadId":"t1"}}

// <- Server notifies:
{"jsonrpc":"2.0","method":"thread/realtime/closed","params":{"threadId":"t1","reason":"requested"}}
```

## Implementation Tips

- **Buffer playback audio.** `outputAudio/delta` chunks arrive
  incrementally. Queue them in a playback buffer and drain at the sample
  rate to avoid glitchy audio.

- **Use 20ms frames for input.** At 24 kHz mono, that's 480 samples per
  chunk. This gives a good balance of latency and overhead.

- **Handle errors gracefully.** If you receive `thread/realtime/error`,
  decide whether to retry or surface the error to the user. The session may
  still be alive after a non-fatal error.

- **Watch for `closed`.** The server may close the session unilaterally
  (e.g., transport failure). Always handle `thread/realtime/closed` to
  clean up your audio pipeline.

- **Platform notes.** The app-server's realtime protocol works on all
  platforms (Linux, macOS, Windows) since audio I/O is the client's
  responsibility. This is different from the TUI, which only supports local
  microphone/speaker on macOS and Windows.

## Source Files

For the authoritative type definitions, see:

| File | Contents |
|------|----------|
| `codex-rs/app-server-protocol/src/protocol/v2.rs` | V2 wire types (`ThreadRealtime*`) |
| `codex-rs/app-server-protocol/src/protocol/common.rs` | `ClientRequest` / `ServerNotification` enums with method names |
| `codex-rs/protocol/src/protocol.rs` | Core `Op` / `EventMsg` / `RealtimeAudioFrame` |
| `codex-rs/core/src/realtime_conversation.rs` | `RealtimeConversationManager` |
| `codex-rs/app-server/src/bespoke_event_handling.rs` | Core event -> v2 notification mapping |
| `codex-rs/app-server/tests/suite/v2/realtime_conversation.rs` | Integration test showing full flow |
