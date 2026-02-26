# Voice Transcription for App-Server Clients

> **Status**: The Codex app-server does not expose a built-in transcription
> endpoint. This guide describes how to replicate the TUI's voice-to-text
> flow in your own client.

## Background

The Codex TUI has a hold-Space-to-dictate feature (gated behind the
`voice_transcription` feature flag). Internally it:

1. Captures microphone audio via `cpal` (macOS / Windows only).
2. Encodes the recording as a 16-bit WAV with peak normalization.
3. Sends the WAV to an external speech-to-text API.
4. Pastes the resulting text into the composer as if the user had typed it.
5. Submits the text as a normal `turn/start`.

Because steps 1-4 happen entirely inside the TUI process, **no audio or
transcription data ever passes through `codex-core` or the app-server**.
The agent only sees the final text string.

## Recommended Client Integration

```
 Your Client                  STT Service              App-Server
    │                              │                        │
    │── capture microphone ──>     │                        │
    │── encode WAV / PCM ────>     │                        │
    │── POST audio ───────────────>│                        │
    │<── transcribed text ─────────│                        │
    │                              │                        │
    │── turn/start { text } ───────────────────────────────>│
    │<── turn events ───────────────────────────────────────│
```

### 1. Capture and encode audio

Record from the user's microphone in whatever format your platform
supports. Convert to one of:

| Format | Notes |
|--------|-------|
| WAV (PCM16, mono, 16 kHz+) | Widely supported, simple to produce |
| WebM/Opus | Smaller; good for browser clients |
| MP3 | Supported by most STT APIs |

The TUI uses 16-bit signed PCM at the device's native sample rate with
peak normalization to improve accuracy on quiet inputs. You can skip
normalization if your levels are reasonable.

### 2. Transcribe

Send the audio to a speech-to-text service. The TUI uses one of two
endpoints depending on the auth mode:

**OpenAI API** (API-key auth):

```
POST https://api.openai.com/v1/audio/transcriptions
Authorization: Bearer <api-key>
Content-Type: multipart/form-data

  model=gpt-4o-transcribe
  file=@audio.wav
  prompt=<optional context>        # improves accuracy
```

Response: `{ "text": "transcribed text here" }`

**ChatGPT backend** (session auth):

```
POST https://chatgpt.com/backend-api/transcribe
Authorization: Bearer <session-token>
Content-Type: multipart/form-data

  file=@audio.wav
```

You are free to use any STT provider (Whisper, Deepgram, Google, etc.).
The app-server does not care where the text came from.

### 3. Submit text to the app-server

Once you have the transcribed text, send it as a regular turn:

```jsonc
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "turn/start",
  "params": {
    "threadId": "019bc...",
    "message": "the transcribed text goes here"
  }
}
```

Or, if a turn is already running, steer it:

```jsonc
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "turn/steer",
  "params": {
    "threadId": "019bc...",
    "message": "additional transcribed text"
  }
}
```

From the agent's perspective, this is identical to typed input.

## Providing transcription context

The TUI passes the current composer text as a `prompt` parameter to the
transcription API. This gives the STT model context about what the user
is likely saying (e.g., code identifiers, file names). If your client
has a text buffer or recent conversation history, pass a relevant snippet
as context to improve accuracy.

## Comparison with realtime voice mode

| | Voice transcription | Realtime voice mode |
|---|---|---|
| Audio handling | Client-side | Server-side (WebSocket) |
| Latency model | Record → transcribe → submit (batch) | Streaming bidirectional |
| Agent interaction | Normal text turns | Parallel voice session + text routing |
| Platform support | Any (client's responsibility) | Any (app-server) / macOS+Windows (TUI) |
| Feature flag | `voice_transcription` (TUI only) | `realtime_conversation` |
| App-server API needed | No (`turn/start` only) | Yes (`thread/realtime/*`) |
| See also | This document | [app-server-voice-mode.md](app-server-voice-mode.md) |

Voice transcription is simpler and works with any STT provider, but
introduces a record-then-submit delay. Realtime voice mode provides a
lower-latency conversational experience but requires the experimental
`thread/realtime/*` API.

## TUI feature flag

To enable the hold-Space dictation in the TUI itself:

```toml
# ~/.codex/config.toml
[features]
voice_transcription = true
```

This is an `UnderDevelopment` feature and is not available on Linux
builds (the TUI stubs out audio capture on Linux via `#[cfg]` gates).

## Source files

| File | Contents |
|------|----------|
| `codex-rs/tui/src/voice.rs` | `VoiceCapture`, `transcribe_async`, WAV encoding, STT HTTP calls |
| `codex-rs/tui/src/bottom_pane/chat_composer.rs` | Space-hold recording UX, placeholder management |
| `codex-rs/tui/src/chatwidget/realtime.rs` | Realtime voice UI state (separate feature) |
| `codex-rs/core/src/features.rs` | `VoiceTranscription` and `RealtimeConversation` feature definitions |
