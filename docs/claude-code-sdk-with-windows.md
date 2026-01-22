# Building Windows Applications with Claude Code CLI (Rust)

This guide documents how to build native Windows desktop applications that integrate with the Claude Code CLI using a pure Rust backend. No Node.js runtime required for end users.

## Why Rust?

- **Zero runtime dependencies** - Single executable, no Node.js/Python needed
- **Small binary size** - MCP servers can be ~500KB
- **Native performance** - Fast startup, low memory usage
- **Cross-platform** - Build for Windows, macOS, and Linux from one codebase

## Overview

Instead of using the Anthropic API directly (which requires API key management), you can leverage the **Claude Code CLI** as your AI backend. This approach:

- Uses the user's existing Claude Code authentication (no API keys needed)
- Provides streaming JSON output for real-time responses
- Supports MCP (Model Context Protocol) for extending Claude's capabilities

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Your App (Tauri)                              │
├─────────────────────────────────────────────────────────────────┤
│  Frontend (React/Vue/Svelte)                                     │
│  └── UI, state management, event handling                        │
├─────────────────────────────────────────────────────────────────┤
│  Rust Backend                                                    │
│  ├── Spawn `claude` CLI process                                  │
│  ├── Parse streaming JSON from stdout                            │
│  └── Emit events to frontend                                     │
└──────────────────────┬──────────────────────────────────────────┘
                       │ spawn process
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  claude (user's installed Claude Code CLI)                       │
│  --print --output-format stream-json --verbose                   │
│  --mcp-config mcp-config.json                                    │
└──────────────────────┬──────────────────────────────────────────┘
                       │ stdio (MCP protocol)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  your-mcp-server.exe (Rust binary, ~500KB)                       │
│  └── Custom tools for your application                           │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- [Claude Code CLI](https://claude.ai/download) installed and authenticated
- Rust toolchain (`rustup`)
- Windows SDK (for code signing)

## Spawning Claude Code CLI

### Basic Command

```bash
claude --print --output-format stream-json --verbose "Your prompt here"
```

### With MCP Server and Session Resume

```bash
claude --print \
  --output-format stream-json \
  --verbose \
  --mcp-config "path/to/mcp-config.json" \
  --allowedTools "mcp__your-server__*" \
  --system-prompt "Custom system prompt" \
  --resume <session-id> \
  "user prompt here"
```

### Streaming JSON Events

The CLI outputs newline-delimited JSON events:

```jsonc
// Session initialization
{"type": "system", "session_id": "abc123", ...}

// Assistant text response
{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello!"}]}}

// Tool use
{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "tool_name", ...}]}}

// Final result
{"type": "result", "session_id": "abc123", ...}
```

## Rust Implementation

### Cargo.toml

```toml
[package]
name = "your-app"
version = "0.1.0"
edition = "2021"

[dependencies]
tokio = { version = "1", features = ["full"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

### Claude Runner

```rust
use std::process::Stdio;
use tokio::process::Command;
use tokio::io::{BufReader, AsyncBufReadExt};
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize)]
#[serde(tag = "type")]
enum ClaudeEvent {
    #[serde(rename = "system")]
    System { session_id: String },
    #[serde(rename = "assistant")]
    Assistant { message: AssistantMessage },
    #[serde(rename = "result")]
    Result { session_id: String },
}

#[derive(Debug, Deserialize)]
struct AssistantMessage {
    content: Vec<ContentBlock>,
}

#[derive(Debug, Deserialize)]
#[serde(tag = "type")]
enum ContentBlock {
    #[serde(rename = "text")]
    Text { text: String },
    #[serde(rename = "tool_use")]
    ToolUse { id: String, name: String },
}

pub struct ClaudeRunner {
    session_id: Option<String>,
    mcp_config_path: Option<String>,
}

impl ClaudeRunner {
    pub fn new() -> Self {
        Self {
            session_id: None,
            mcp_config_path: None,
        }
    }

    pub fn with_mcp_config(mut self, path: String) -> Self {
        self.mcp_config_path = Some(path);
        self
    }

    pub async fn send_message<F>(
        &mut self,
        prompt: &str,
        mut on_event: F,
    ) -> Result<(), Box<dyn std::error::Error>>
    where
        F: FnMut(ClaudeEvent),
    {
        let mut args = vec![
            "--print".to_string(),
            "--output-format".to_string(),
            "stream-json".to_string(),
            "--verbose".to_string(),
        ];

        // Add MCP config if specified
        if let Some(ref config_path) = self.mcp_config_path {
            args.push("--mcp-config".to_string());
            args.push(config_path.clone());
        }

        // Resume session if we have one
        if let Some(ref session_id) = self.session_id {
            args.push("--resume".to_string());
            args.push(session_id.clone());
        }

        args.push(prompt.to_string());

        let mut child = Command::new("claude")
            .args(&args)
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()?;

        let stdout = child.stdout.take().unwrap();
        let reader = BufReader::new(stdout);
        let mut lines = reader.lines();

        while let Some(line) = lines.next_line().await? {
            if let Ok(event) = serde_json::from_str::<ClaudeEvent>(&line) {
                // Save session_id for future resume
                match &event {
                    ClaudeEvent::System { session_id } |
                    ClaudeEvent::Result { session_id } => {
                        self.session_id = Some(session_id.clone());
                    }
                    _ => {}
                }
                on_event(event);
            }
        }

        child.wait().await?;
        Ok(())
    }
}
```

### Tauri Integration

```rust
use tauri::{AppHandle, Manager};

#[tauri::command]
async fn send_message(
    app: AppHandle,
    prompt: String,
) -> Result<(), String> {
    let mut runner = ClaudeRunner::new()
        .with_mcp_config("path/to/mcp-config.json".to_string());

    runner
        .send_message(&prompt, |event| {
            // Emit events to frontend
            let _ = app.emit_all("claude-event", &event);
        })
        .await
        .map_err(|e| e.to_string())
}
```

### Frontend Event Handling (TypeScript)

```typescript
import { listen } from "@tauri-apps/api/event";

interface ClaudeEvent {
  type: "system" | "assistant" | "result";
  session_id?: string;
  message?: {
    content: Array<{ type: string; text?: string }>;
  };
}

listen<ClaudeEvent>("claude-event", (event) => {
  const data = event.payload;

  if (data.type === "assistant" && data.message) {
    for (const block of data.message.content) {
      if (block.type === "text") {
        console.log("Claude:", block.text);
      }
    }
  }
});
```

## MCP Server in Rust

MCP (Model Context Protocol) lets you extend Claude's capabilities with custom tools.

### Cargo.toml

```toml
[package]
name = "your-mcp-server"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "your-mcp-server"
path = "src/main.rs"

[dependencies]
rmcp = { version = "0.3", features = ["server", "macros", "transport-io"] }
tokio = { version = "1", features = ["full"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
schemars = "0.8"
anyhow = "1.0"

# For screenshot/image support (optional)
xcap = "0.4"                    # Cross-platform screen capture
base64 = "0.22"                 # Base64 encoding
image = { version = "0.25", default-features = false, features = ["png", "webp"] }
```

### MCP Server Implementation

```rust
use std::io::Cursor;
use anyhow::Result;
use base64::{Engine as _, engine::general_purpose::STANDARD as BASE64};
use image::ImageFormat;
use rmcp::{
    handler::server::{router::tool::ToolRouter, tool::Parameters},
    model::*,
    schemars, tool, tool_handler, tool_router, ServerHandler, ServiceExt,
};
use xcap::Monitor;

// Define tool input schemas
#[derive(serde::Deserialize, schemars::JsonSchema)]
struct SetEmotionRequest {
    /// The emotion to display (happy, sad, excited, thinking)
    emotion: String,
    /// Duration in milliseconds (default: 5000)
    #[serde(default)]
    duration_ms: Option<u32>,
}

#[derive(serde::Deserialize, schemars::JsonSchema)]
struct MoveToRequest {
    /// Target position: "left", "right", "center", or x-coordinate
    target: String,
}

#[derive(serde::Deserialize, schemars::JsonSchema)]
struct CaptureScreenshotRequest {
    /// Optional description of what to look for
    #[serde(default)]
    description: Option<String>,
}

// MCP Server with tool router
pub struct MascotService {
    tool_router: ToolRouter<MascotService>,
}

#[tool_router]
impl MascotService {
    fn new() -> Self {
        Self {
            tool_router: Self::tool_router(),
        }
    }

    // Tool returning text (simple case)
    #[tool(description = "Set the mascot's emotional expression")]
    async fn set_emotion(&self, Parameters(req): Parameters<SetEmotionRequest>) -> String {
        let duration = req.duration_ms.unwrap_or(5000);
        format!("Emotion set to '{}' for {}ms", req.emotion, duration)
    }

    #[tool(description = "Move the mascot to a screen position")]
    async fn move_to(&self, Parameters(req): Parameters<MoveToRequest>) -> String {
        format!("Moving to: {}", req.target)
    }

    // Tool returning image content (advanced case)
    #[tool(description = "Capture a screenshot of the user's screen")]
    async fn capture_screenshot(
        &self,
        Parameters(req): Parameters<CaptureScreenshotRequest>,
    ) -> Result<CallToolResult, rmcp::ErrorData> {
        let desc = req.description.unwrap_or_else(|| "general view".to_string());

        let make_error = |msg: String| {
            rmcp::ErrorData::new(
                rmcp::model::ErrorCode::INTERNAL_ERROR,
                msg,
                None::<serde_json::Value>,
            )
        };

        // Get primary monitor
        let monitors = Monitor::all()
            .map_err(|e| make_error(format!("Failed to get monitors: {}", e)))?;
        let monitor = monitors.into_iter().next()
            .ok_or_else(|| make_error("No monitors found".to_string()))?;

        // Capture screen
        let image = monitor.capture_image()
            .map_err(|e| make_error(format!("Failed to capture: {}", e)))?;

        // Resize if too large (MCP has ~1MB limit)
        let (w, h) = (image.width(), image.height());
        let max_dim = 1920u32;
        let resized = if w > max_dim || h > max_dim {
            let scale = max_dim as f32 / w.max(h) as f32;
            image::imageops::resize(
                &image,
                (w as f32 * scale) as u32,
                (h as f32 * scale) as u32,
                image::imageops::FilterType::Triangle,
            )
        } else {
            image::imageops::resize(&image, w, h, image::imageops::FilterType::Triangle)
        };

        // Encode as WebP (smaller than PNG)
        let mut webp_data = Cursor::new(Vec::new());
        resized.write_to(&mut webp_data, ImageFormat::WebP)
            .map_err(|e| make_error(format!("Failed to encode: {}", e)))?;

        // Base64 encode and return as image content
        let base64_data = BASE64.encode(webp_data.into_inner());

        Ok(CallToolResult::success(vec![
            Content::text(format!("Screenshot captured (looking for: {})", desc)),
            Content::image(base64_data, "image/webp"),
        ]))
    }
}

#[tool_handler]
impl ServerHandler for MascotService {
    fn get_info(&self) -> ServerInfo {
        ServerInfo {
            capabilities: ServerCapabilities::builder().enable_tools().build(),
            ..Default::default()
        }
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    let transport = (tokio::io::stdin(), tokio::io::stdout());
    let service = MascotService::new().serve(transport).await?;
    service.waiting().await?;
    Ok(())
}
```

### Tool Return Types

MCP tools can return different types:

| Return Type | Use Case | Example |
|-------------|----------|---------|
| `String` | Simple text response | `set_emotion`, `move_to` |
| `Result<CallToolResult, rmcp::ErrorData>` | Image/multi-content | `capture_screenshot` |

For image content, use `Content::image(base64_data, mime_type)` within `CallToolResult::success(vec![...])`.

**Note:** MCP has a ~1MB limit for tool results. Always resize large images before encoding.

### MCP Config File

```json
{
  "mcpServers": {
    "mascot": {
      "command": "path/to/your-mcp-server.exe",
      "args": []
    }
  }
}
```

### Bundle MCP Server with Tauri

```json
// tauri.conf.json
{
  "bundle": {
    "resources": [
      "../your-mcp-server/target/release/your-mcp-server.exe"
    ]
  }
}
```

## Windows Code Signing

Windows SmartScreen warns users about unsigned executables.

### Development Certificate

```powershell
# Create certificate
$cert = New-SelfSignedCertificate `
  -Type CodeSigningCert `
  -Subject "CN=Your Dev Certificate" `
  -CertStoreLocation "Cert:\CurrentUser\My" `
  -NotAfter (Get-Date).AddYears(5)

# Export to .pfx
$password = ConvertTo-SecureString -String "devpass" -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath ".\dev-cert.pfx" -Password $password
```

### Signing Script (Rust)

For a pure Rust build pipeline, create a signing utility:

```rust
// scripts/sign.rs
use std::process::Command;
use std::path::Path;
use std::fs;

fn find_signtool() -> Option<String> {
    let sdk_path = r"C:\Program Files (x86)\Windows Kits\10\bin";

    let mut versions: Vec<_> = fs::read_dir(sdk_path)
        .ok()?
        .filter_map(|e| e.ok())
        .map(|e| e.file_name().to_string_lossy().to_string())
        .filter(|n| n.starts_with("10."))
        .collect();

    versions.sort();
    versions.reverse();

    for version in versions {
        let signtool = format!(r"{}\{}\x64\signtool.exe", sdk_path, version);
        if Path::new(&signtool).exists() {
            return Some(signtool);
        }
    }
    None
}

fn main() {
    let signtool = find_signtool().expect("signtool.exe not found");
    let cert_path = "dev-cert.pfx";
    let password = "devpass";

    let artifacts = fs::read_dir("artifacts")
        .expect("artifacts directory not found")
        .filter_map(|e| e.ok())
        .filter(|e| e.path().extension().map_or(false, |ext| ext == "exe"));

    for entry in artifacts {
        let path = entry.path();
        println!("Signing {:?}...", path);

        Command::new(&signtool)
            .args([
                "sign",
                "/f", cert_path,
                "/p", password,
                "/fd", "sha256",
                path.to_str().unwrap(),
            ])
            .status()
            .expect("Failed to sign");
    }

    println!("Signing complete!");
}
```

### Build with Cargo

```toml
# Cargo.toml
[[bin]]
name = "sign"
path = "scripts/sign.rs"
```

```bash
# Build everything
cargo build --release -p your-app
cargo build --release -p your-mcp-server

# Sign
cargo run --bin sign
```

### Production Code Signing Options

| Option | Cost | Notes |
|--------|------|-------|
| Azure Trusted Signing | ~$10/month | Microsoft's cloud signing service |
| SignPath.io | Free (OSS) | Free for open source projects |
| Traditional CA | $200-500/year | DigiCert, Sectigo, Comodo |

### .gitignore

```gitignore
# Code signing certificates
*.pfx
*.p12

# Build outputs
target/
artifacts/
```

## Project Structure

```
your-app/
├── src/                      # Frontend (if using Tauri)
├── src-tauri/                # Tauri Rust backend
│   ├── src/
│   │   ├── main.rs
│   │   ├── lib.rs
│   │   └── claude_runner.rs  # Claude CLI integration
│   └── Cargo.toml
├── your-mcp-server/          # MCP server (separate crate)
│   ├── src/
│   │   └── main.rs
│   └── Cargo.toml
├── scripts/
│   └── sign.rs               # Signing utility
├── artifacts/                # Build outputs (gitignored)
├── dev-cert.pfx              # Dev certificate (gitignored)
├── Cargo.toml                # Workspace root
└── mcp-config.json
```

### Cargo Workspace

```toml
# Cargo.toml (workspace root)
[workspace]
members = [
    "src-tauri",
    "your-mcp-server",
]
```

## Tips and Best Practices

### 1. Session Management

Store `session_id` to enable conversation continuity:

```rust
// Save after each conversation
self.session_id = Some(result.session_id);

// Resume later
args.push("--resume".to_string());
args.push(session_id);
```

### 2. Error Handling

Handle cases where Claude Code is not installed:

```rust
match Command::new("claude").spawn() {
    Ok(child) => { /* proceed */ }
    Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
        return Err("Claude Code CLI not found. Please install from https://claude.ai/download".into());
    }
    Err(e) => return Err(e.into()),
}
```

### 3. Async Streaming

Use channels for clean async streaming to UI:

```rust
use tokio::sync::mpsc;

let (tx, mut rx) = mpsc::channel(100);

// Spawn reader task
tokio::spawn(async move {
    while let Some(line) = lines.next_line().await.unwrap() {
        if let Ok(event) = serde_json::from_str(&line) {
            tx.send(event).await.unwrap();
        }
    }
});

// Consume in main task
while let Some(event) = rx.recv().await {
    app.emit_all("claude-event", &event)?;
}
```

### 4. Binary Size Optimization

```toml
# Cargo.toml
[profile.release]
opt-level = "z"     # Optimize for size
lto = true          # Link-time optimization
codegen-units = 1   # Single codegen unit
strip = true        # Strip symbols
```

## Case Study: Claude Mascot

Claude Mascot demonstrates this architecture:

- **Tauri Backend**: Spawns Claude CLI, manages windows, system tray
- **MCP Server**: ~500KB Rust binary providing mascot control tools
- **Frontend**: React for mascot rendering and chat UI

Features powered by Claude + MCP:
- Natural conversation with the mascot
- Emotional expressions via `set_emotion` tool
- Screen movement via `move_to` tool
- **Screenshot capture** via `capture_screenshot` tool - Claude can see what's on your screen

The screenshot feature uses:
- `xcap` crate for cross-platform screen capture
- WebP encoding for smaller file sizes (~60% smaller than PNG)
- Automatic resizing to stay under MCP's 1MB limit
- Returns image as `Content::image` so Claude can actually "see" the screen

All without requiring API keys - uses the user's Claude Code authentication.

## Additional Notes: Codex App Server Integration

As an alternative to Claude Code CLI, you can integrate with [OpenAI Codex](https://github.com/openai/codex) using the **App Server** mode. This provides a persistent JSON-RPC 2.0 server over stdio, enabling efficient multi-turn conversations without subprocess spawn overhead.

### Why App Server (vs CLI exec)?

| Approach | Pros | Cons |
|----------|------|------|
| `codex exec` | Simple one-shot usage | Subprocess spawn per query |
| `codex app-server` | Persistent connection, parallel threads | More complex setup |

For desktop applications with ongoing conversations, App Server is recommended.

### Starting the App Server

```bash
codex app-server
```

The server communicates via JSON-RPC 2.0 over stdin/stdout (streaming JSONL).

### JSON-RPC Protocol

App Server uses a simplified JSON-RPC 2.0 format (no `jsonrpc` field required):

```jsonc
// Request
{"id": 1, "method": "thread/start", "params": {"config": {...}}}

// Response
{"id": 1, "result": {"threadId": "abc123"}}

// Streaming notification (no id)
{"method": "agent/message/delta", "params": {"delta": "Hello"}}
```

### Core Methods

| Method | Description |
|--------|-------------|
| `thread/start` | Create a new conversation thread |
| `turn/start` | Start a new turn in a thread |
| `turn/interrupt` | Interrupt an ongoing turn |

### Thread Configuration

```jsonc
// thread/start request
{
  "id": 1,
  "method": "thread/start",
  "params": {
    "config": {
      "cwd": "/tmp/empty",
      "model": "gpt-5.2",
      "baseInstructions": "You are a helpful assistant",
      "sandbox": "danger-full-access",
      "approvalPolicy": "never",
      "mcpServers": {
        "mascot": {
          "command": "path/to/mcp-server.exe",
          "args": []
        }
      }
    }
  }
}

// Response
{"id": 1, "result": {"threadId": "thread_abc123"}}
```

### Turn Configuration

```jsonc
// turn/start request
{
  "id": 2,
  "method": "turn/start",
  "params": {
    "threadId": "thread_abc123",
    "input": [
      {"type": "text", "text": "Hello!"}
    ],
    "baseInstructions": "Optional override for this turn"
  }
}
```

### Streaming Notifications

During a turn, the server emits notifications:

```jsonc
// Turn started
{"method": "turn/started", "params": {"turnId": "turn_xyz"}}

// Text output (incremental)
{"method": "agent/message/delta", "params": {"delta": "Hello"}}

// Reasoning/thinking (incremental)
{"method": "agent/reasoning/delta", "params": {"delta": "Let me think..."}}

// Item completed (message, tool call, etc.)
{"method": "item/completed", "params": {"item": {"type": "message", "content": [...]}}}

// MCP tool call completed
{"method": "item/completed", "params": {"item": {"type": "mcpToolCall", "name": "set_emotion", "arguments": {...}, "result": {...}}}}

// Turn completed
{"method": "turn/completed", "params": {"turnId": "turn_xyz", "status": "completed"}}

// Turn failed
{"method": "turn/completed", "params": {"turnId": "turn_xyz", "status": "failed", "codexErrorInfo": {"message": "..."}}}
```

### Rust Implementation

```rust
use std::process::Stdio;
use tokio::process::{Command, Child, ChildStdin, ChildStdout};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Serialize)]
struct JsonRpcRequest {
    id: u64,
    method: String,
    params: Value,
}

#[derive(Debug, Deserialize)]
struct JsonRpcResponse {
    id: Option<u64>,
    result: Option<Value>,
    error: Option<JsonRpcError>,
    method: Option<String>,  // For notifications
    params: Option<Value>,   // For notifications
}

#[derive(Debug, Deserialize)]
struct JsonRpcError {
    code: i32,
    message: String,
}

pub struct CodexAppServer {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    request_id: u64,
}

impl CodexAppServer {
    pub async fn spawn() -> Result<Self, Box<dyn std::error::Error>> {
        let mut child = Command::new("codex")
            .arg("app-server")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()?;

        let stdin = child.stdin.take().unwrap();
        let stdout = BufReader::new(child.stdout.take().unwrap());

        Ok(Self {
            child,
            stdin,
            stdout,
            request_id: 0,
        })
    }

    async fn send_request(&mut self, method: &str, params: Value) -> Result<Value, String> {
        self.request_id += 1;
        let request = JsonRpcRequest {
            id: self.request_id,
            method: method.to_string(),
            params,
        };

        let mut line = serde_json::to_string(&request).unwrap();
        line.push('\n');
        self.stdin.write_all(line.as_bytes()).await
            .map_err(|e| format!("Write error: {}", e))?;

        // Read response (skip notifications)
        loop {
            let mut buf = String::new();
            self.stdout.read_line(&mut buf).await
                .map_err(|e| format!("Read error: {}", e))?;

            let response: JsonRpcResponse = serde_json::from_str(&buf)
                .map_err(|e| format!("Parse error: {}", e))?;

            // Check if this is our response (has matching id)
            if response.id == Some(self.request_id) {
                if let Some(error) = response.error {
                    return Err(format!("RPC error: {}", error.message));
                }
                return Ok(response.result.unwrap_or(Value::Null));
            }
            // Otherwise it's a notification, continue reading
        }
    }

    pub async fn create_thread(&mut self, config: ThreadConfig) -> Result<String, String> {
        let params = serde_json::json!({ "config": config });
        let result = self.send_request("thread/start", params).await?;
        result["threadId"].as_str()
            .map(|s| s.to_string())
            .ok_or("Missing threadId".to_string())
    }

    pub async fn start_turn(
        &mut self,
        thread_id: &str,
        text: &str,
    ) -> Result<TurnStream, String> {
        self.request_id += 1;
        let request = JsonRpcRequest {
            id: self.request_id,
            method: "turn/start".to_string(),
            params: serde_json::json!({
                "threadId": thread_id,
                "input": [{"type": "text", "text": text}]
            }),
        };

        let mut line = serde_json::to_string(&request).unwrap();
        line.push('\n');
        self.stdin.write_all(line.as_bytes()).await
            .map_err(|e| format!("Write error: {}", e))?;

        Ok(TurnStream { request_id: self.request_id })
    }

    pub async fn read_event(&mut self) -> Result<TurnEvent, String> {
        let mut buf = String::new();
        self.stdout.read_line(&mut buf).await
            .map_err(|e| format!("Read error: {}", e))?;

        let response: JsonRpcResponse = serde_json::from_str(&buf)
            .map_err(|e| format!("Parse error: {}", e))?;

        // Check for notifications
        if let Some(method) = &response.method {
            let params = response.params.unwrap_or(Value::Null);
            return Ok(match method.as_str() {
                "agent/message/delta" => {
                    TurnEvent::TextDelta(params["delta"].as_str().unwrap_or("").to_string())
                }
                "agent/reasoning/delta" => {
                    TurnEvent::ReasoningDelta(params["delta"].as_str().unwrap_or("").to_string())
                }
                "turn/completed" => {
                    let status = params["status"].as_str().unwrap_or("completed");
                    if status == "failed" {
                        let msg = params["codexErrorInfo"]["message"]
                            .as_str().unwrap_or("Unknown error");
                        TurnEvent::Failed(msg.to_string())
                    } else {
                        TurnEvent::Completed
                    }
                }
                "item/completed" => {
                    let item = &params["item"];
                    if item["type"] == "mcpToolCall" {
                        TurnEvent::ToolCall {
                            name: item["name"].as_str().unwrap_or("").to_string(),
                            arguments: item["arguments"].clone(),
                        }
                    } else {
                        TurnEvent::ItemCompleted(item.clone())
                    }
                }
                _ => TurnEvent::Other(method.clone(), params),
            });
        }

        // Response to our request
        if response.id.is_some() {
            if let Some(error) = response.error {
                return Ok(TurnEvent::Failed(error.message));
            }
        }

        Ok(TurnEvent::Other("response".to_string(), response.result.unwrap_or(Value::Null)))
    }
}

#[derive(Debug, Serialize)]
pub struct ThreadConfig {
    pub cwd: String,
    pub model: String,
    #[serde(rename = "baseInstructions")]
    pub base_instructions: String,
    pub sandbox: String,
    #[serde(rename = "approvalPolicy")]
    pub approval_policy: String,
    #[serde(rename = "mcpServers", skip_serializing_if = "Option::is_none")]
    pub mcp_servers: Option<Value>,
}

pub struct TurnStream {
    request_id: u64,
}

#[derive(Debug)]
pub enum TurnEvent {
    TextDelta(String),
    ReasoningDelta(String),
    ToolCall { name: String, arguments: Value },
    ItemCompleted(Value),
    Completed,
    Failed(String),
    Other(String, Value),
}
```

### Tauri Integration

```rust
use tauri::{AppHandle, Manager, State};
use std::sync::Arc;
use tokio::sync::Mutex;

struct AppState {
    codex: Arc<Mutex<Option<CodexAppServer>>>,
    thread_id: Arc<Mutex<Option<String>>>,
}

#[tauri::command]
async fn init_codex(state: State<'_, AppState>) -> Result<(), String> {
    let server = CodexAppServer::spawn().await?;
    *state.codex.lock().await = Some(server);
    Ok(())
}

#[tauri::command]
async fn send_message(
    app: AppHandle,
    state: State<'_, AppState>,
    message: String,
) -> Result<(), String> {
    let mut codex_guard = state.codex.lock().await;
    let codex = codex_guard.as_mut().ok_or("Codex not initialized")?;

    // Create thread if needed
    let mut thread_guard = state.thread_id.lock().await;
    if thread_guard.is_none() {
        let config = ThreadConfig {
            cwd: "/tmp/empty".to_string(),
            model: "gpt-5.2".to_string(),
            base_instructions: "You are a helpful assistant".to_string(),
            sandbox: "danger-full-access".to_string(),
            approval_policy: "never".to_string(),
            mcp_servers: None,
        };
        *thread_guard = Some(codex.create_thread(config).await?);
    }

    let thread_id = thread_guard.as_ref().unwrap().clone();
    drop(thread_guard);

    // Start turn
    codex.start_turn(&thread_id, &message).await?;

    // Stream events to frontend
    loop {
        let event = codex.read_event().await?;
        match &event {
            TurnEvent::TextDelta(text) => {
                let _ = app.emit_all("codex-text", text);
            }
            TurnEvent::ToolCall { name, arguments } => {
                let _ = app.emit_all("codex-tool", serde_json::json!({
                    "name": name,
                    "arguments": arguments
                }));
            }
            TurnEvent::Completed => break,
            TurnEvent::Failed(msg) => return Err(msg.clone()),
            _ => {}
        }
    }

    Ok(())
}
```

### Image Support

Codex supports images via `localImage` (file path) input type:

```jsonc
{
  "method": "turn/start",
  "params": {
    "threadId": "...",
    "input": [
      {"type": "text", "text": "What's in this image?"},
      {"type": "localImage", "path": "/path/to/image.png"}
    ]
  }
}
```

For base64 images, save to a temp file first:

```rust
fn save_image_to_temp(base64_data: &str, index: usize) -> Result<PathBuf, String> {
    use base64::{engine::general_purpose::STANDARD, Engine};

    let image_data = STANDARD.decode(base64_data)
        .map_err(|e| format!("Failed to decode: {}", e))?;

    let temp_path = std::env::temp_dir()
        .join(format!("app-image-{}.png", index));

    std::fs::write(&temp_path, &image_data)
        .map_err(|e| format!("Failed to write: {}", e))?;

    Ok(temp_path)
}
```

### Key Differences: Claude Code vs Codex App Server

| Feature | Claude Code CLI | Codex App Server |
|---------|-----------------|------------------|
| Auth | Claude Code login | OpenAI API key |
| Protocol | Spawn per query, stream-json | Persistent JSON-RPC 2.0 |
| Session | `--resume <session-id>` | `threadId` in requests |
| Parallelism | Multiple processes | Multiple threads, one server |
| MCP Config | JSON file via `--mcp-config` | In `thread/start` config |
| Image Input | Base64 in prompt | `localImage` with file path |

### Setup Notes

**Disable Skills Injection:** Codex injects skills from `~/.codex/skills/` which can break character immersion. Disable with:

```bash
chmod 000 ~/.codex/skills
```

**Empty Working Directory:** Set `cwd` to an empty directory (e.g., `/tmp/codex-empty`) to prevent Codex from picking up `AGENTS.md` or other project files.

### Download Codex

Install via npm or download from [OpenAI Codex Releases](https://github.com/openai/codex/releases).

## Resources

- [Claude Code CLI](https://claude.ai/download)
- [OpenAI Codex CLI](https://github.com/openai/codex)
- [Tauri v2](https://v2.tauri.app/)
- [rmcp - Rust MCP SDK](https://github.com/modelcontextprotocol/rust-sdk)
- [Model Context Protocol](https://modelcontextprotocol.io/)

## Author

Seunghyun Ji (sorryhyun) <standingbehindnv@gmail.com>
