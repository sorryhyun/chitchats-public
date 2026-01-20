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

## Additional Notes: Codex CLI Integration

As an alternative to Claude Code CLI, you can also integrate with [OpenAI Codex CLI](https://github.com/openai/codex). This provides similar capabilities with OpenAI's models.

### Codex CLI Command

```bash
codex exec --json --full-auto --skip-git-repo-check "Your prompt here"
```

Key flags:
- `exec` - Execute mode for running prompts
- `--json` - Output streaming JSON events
- `--full-auto` - Autonomous mode without user confirmations
- `--skip-git-repo-check` - Skip git repository validation (important for desktop apps)

### With Session Resume

```bash
codex exec resume <thread-id> --json --full-auto --skip-git-repo-check "follow-up prompt"
```

### Codex Streaming JSON Events

Codex outputs different event types than Claude Code:

```jsonc
// Thread initialization
{"type": "thread.started", "thread_id": "abc123"}

// Turn lifecycle
{"type": "turn.started", "turn_id": "xyz789"}
{"type": "turn.completed", "turn_id": "xyz789"}

// Content items
{"type": "item.started", "item": {"type": "message", "content": [...]}}
{"type": "item.completed", "item": {"type": "message", "content": [...]}}

// Tool calls
{"type": "item.started", "item": {"type": "tool_call", "name": "tool_name", "arguments": {...}}}

// MCP tool calls
{"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "mascot", "tool": "set_emotion", ...}}

// Errors
{"type": "turn.failed", "error": "Something went wrong"}
{"type": "error", "message": "Error details"}
```

### Rust Event Types

```rust
#[derive(Debug, Deserialize)]
#[serde(tag = "type")]
pub enum CodexStreamEvent {
    #[serde(rename = "thread.started")]
    ThreadStarted { thread_id: Option<String> },

    #[serde(rename = "turn.started")]
    TurnStarted { turn_id: Option<String> },

    #[serde(rename = "turn.completed")]
    TurnCompleted { turn_id: Option<String> },

    #[serde(rename = "turn.failed")]
    TurnFailed { error: Option<String> },

    #[serde(rename = "item.started")]
    ItemStarted { item: Option<CodexItem> },

    #[serde(rename = "item.completed")]
    ItemCompleted { item: Option<CodexItem> },

    #[serde(rename = "error")]
    Error { message: Option<String> },
}

#[derive(Debug, Deserialize)]
#[serde(tag = "type")]
pub enum CodexItem {
    #[serde(rename = "message")]
    Message { content: Vec<CodexContent> },

    #[serde(rename = "tool_call")]
    ToolCall { name: Option<String>, arguments: Option<serde_json::Value> },

    #[serde(rename = "mcp_tool_call")]
    McpToolCall {
        server: Option<String>,
        tool: Option<String>,
        arguments: Option<serde_json::Value>,
        result: Option<serde_json::Value>,
    },
}
```

### Codex MCP Configuration

Unlike Claude Code which uses a JSON config file, Codex reads MCP config from `~/.codex/config.toml`:

```toml
[mcp_servers.mascot]
command = "C:\\path\\to\\your-mcp-server.exe"
args = []
```

Write this config programmatically before spawning Codex:

```rust
fn write_codex_mcp_config(mcp_exe_path: &str) -> Result<(), String> {
    let home = dirs::home_dir().ok_or("Could not find home directory")?;
    let config_path = home.join(".codex").join("config.toml");

    // Create directory if needed
    std::fs::create_dir_all(config_path.parent().unwrap())
        .map_err(|e| format!("Failed to create .codex directory: {}", e))?;

    // Escape backslashes for TOML
    let escaped_path = mcp_exe_path.replace('\\', "\\\\");

    let config = format!(
        "[mcp_servers.mascot]\ncommand = \"{}\"\nargs = []\n",
        escaped_path
    );

    std::fs::write(&config_path, config)
        .map_err(|e| format!("Failed to write config: {}", e))?;

    Ok(())
}
```

### Codex Model Configuration

Pass model settings via `--config` flag:

```bash
codex exec --json --full-auto \
  --config model="\"gpt-4o\"" \
  --config model_reasoning_effort="\"high\"" \
  "Your prompt"
```

### Image Support

Codex supports image inputs via file paths (not base64):

```bash
codex exec --json --full-auto --image "/path/to/image.png" "Describe this image"
```

Save base64 images to temp files before passing to Codex:

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

### Key Differences: Claude Code vs Codex

| Feature | Claude Code CLI | Codex CLI |
|---------|-----------------|-----------|
| Auth | Claude Code login | OpenAI API key |
| MCP Config | JSON file via `--mcp-config` | TOML at `~/.codex/config.toml` |
| Session Resume | `--resume <session-id>` | `exec resume <thread-id>` |
| Output Format | `--output-format stream-json` | `--json` |
| Auto Mode | N/A (always interactive) | `--full-auto` |
| Git Check | N/A | `--skip-git-repo-check` |
| Image Input | Base64 in prompt | File path via `--image` |

### Download Codex CLI

Download the Windows executable from [OpenAI Codex Releases](https://github.com/openai/codex/releases):
- `codex-x86_64-pc-windows-msvc.exe` for Windows x64

Bundle it with your application or expect users to install it separately.

## Resources

- [Claude Code CLI](https://claude.ai/download)
- [OpenAI Codex CLI](https://github.com/openai/codex)
- [Tauri v2](https://v2.tauri.app/)
- [rmcp - Rust MCP SDK](https://github.com/modelcontextprotocol/rust-sdk)
- [Model Context Protocol](https://modelcontextprotocol.io/)

## Author

Seunghyun Ji (sorryhyun) <standingbehindnv@gmail.com>
