# Setup Guide

Complete setup guide for Claude Code Role Play, covering authentication, deployment, and memory systems.

## Quick Start

### 1. Install Dependencies

```bash
make install
```

#### Windows one-click setup

If you want a single PowerShell command that installs uv + Node, creates `.env`, hashes your password, and (optionally) starts the servers:

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/windows/one_click_setup.ps1 -Password "your_password" -StartServers
```

The script fetches uv, installs backend/frontend dependencies, writes `API_KEY_HASH` and `JWT_SECRET` to `.env`, and launches both servers. Omit `-StartServers` if you only want to install and configure. `winget` is used when available, but if it is missing or fails the script will silently fall back to downloading the official Node.js LTS MSI and installing it with `msiexec`.

**Prefer an .exe-style installer?** You can wrap the PowerShell script into a single self-extracting binary without changing the app:

```powershell
# Install the packager (one-time)
Install-Module -Scope CurrentUser -Name ps2exe -Force

# Build a signed-by-you installer binary
Invoke-ps2exe scripts/windows/one_click_setup.ps1 ClaudeCodeSetup.exe
```

This produces `ClaudeCodeSetup.exe` that runs the same steps as the script. Signing or reputation is up to you; the project does not ship an .exe to avoid unsigned binaries and to keep installers versioned by the repo owner.

**CI-built installer artifact:** If you want GitHub Actions to generate the `.exe` for you, trigger the `Build Windows installer` workflow from the Actions tab. It uses `Invoke-ps2exe` on `scripts/windows/one_click_setup.ps1` and uploads `ClaudeCodeSetup.exe` as an artifact (optionally stamping a version string via the workflow input).

### 2. Configure Authentication

Claude Code Role Play uses JWT token-based authentication with bcrypt password hashing.

**Generate password hash:**
```bash
make generate-hash
# Or manually:
# cd backend && uv run python generate_hash.py
# Non-interactive (for scripts/CI):
# cd backend && uv run python generate_hash.py --password "your_password" --output-only
```

**Generate JWT secret:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**Configure environment:**
```bash
cp .env.example .env
```

Edit `.env` and add:
```env
API_KEY_HASH=<hash from step 1>
JWT_SECRET=<secret from step 2>
```

**Optional settings:**
```env
USER_NAME=User                    # Display name for user messages
DEBUG_AGENTS=false                # Enable verbose agent logging
MEMORY_BY=RECALL                  # Memory system: RECALL or BRAIN
FRONTEND_URL=https://your-app.vercel.app  # CORS for production
```

### 3. Run Development Server

```bash
make dev
```

Access:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

Login with the password you used to generate the hash.

## Memory Systems

Claude Code Role Play supports **two mutually exclusive memory modes** controlled by `MEMORY_BY` environment variable.

### RECALL Mode (Default)

**On-demand memory retrieval** - Agents call `recall` tool to fetch specific memories when needed.

**Configuration:**
```env
MEMORY_BY=RECALL
RECALL_MEMORY_FILE=consolidated_memory  # Optional: default value
```

**Agent structure:**
```
agents/agent_name/
  ├── in_a_nutshell.md           # ✅ Always loaded
  ├── characteristics.md          # ✅ Always loaded
  ├── consolidated_memory.md     # 📋 Parsed into recallable sections
  ├── anti_pattern.md            # ✅ Always loaded
  └── recent_events.md           # ✅ Always loaded
```

**Memory file format:**
```markdown
## [section_title]
Memory content for this section...

## [another_section]
More memory content...
```

**Benefits:**
- Lower baseline token cost (only subtitles shown in context)
- Agent-controlled memory retrieval
- Flexible memory access

**See [MEMORY_SYSTEMS.md](MEMORY_SYSTEMS.md) for complete documentation.**

### BRAIN Mode

**Automatic memory surfacing** - Separate memory brain agent analyzes context and injects relevant memories before each response.

**Configuration:**
```env
MEMORY_BY=BRAIN
```

**Agent setup:**

Add `memory_brain.md` to agent folder:
```markdown
enabled: true
policy: balanced
```

Add `long_term_memory.md` with subtitle format:
```markdown
## [memory_subtitle]
Full memory content here...

## [another_memory]
More content...
```

**Available policies:**
- `balanced` - Neutral, context-driven selection
- `trauma_biased` - Favors painful/difficult memories
- `genius_planner` - Favors strategic/analytical memories
- `optimistic` - Favors positive/hopeful memories
- `avoidant` - Suppresses difficult memories

**Features:**
- Psychologically realistic memory activation
- Max 3 memories per turn (configurable)
- 10-turn cooldown to prevent repetition
- Activation strength scores for each memory

**Benefits:**
- Context-driven memory activation
- Character depth through policy-based selection
- Dynamic behavior changes when memories surface

**See [MEMORY_SYSTEMS.md](MEMORY_SYSTEMS.md) for complete documentation.**

### Choosing a Memory System

| Feature | RECALL Mode | BRAIN Mode |
|---------|-------------|------------|
| Token Cost | Lower baseline | Higher baseline |
| Control | Agent decides | Automatic |
| Memory Activation | On-demand | Context-driven |
| Psychological Realism | Moderate | High |
| Configuration | Simple | Per-agent policies |

**Default:** If `MEMORY_BY` is not set or has an invalid value, defaults to `RECALL` mode.

## Deployment

### Frontend: Vercel

**Quick deploy:**
```bash
cd frontend
vercel --prod
```

**Set environment variable:**
```bash
vercel env add VITE_API_BASE_URL
# Enter your ngrok backend URL when prompted
# Example: https://your-domain.ngrok-free.app
```

Then redeploy:
```bash
vercel --prod
```

### Backend: ngrok

**Start backend with ngrok:**
```bash
# Terminal 1: Start backend
make run-backend

# Terminal 2: Start ngrok tunnel
make run-ngrok-backend
```

**Update CORS for production:**

Add your Vercel URL to `.env`:
```env
FRONTEND_URL=https://your-app.vercel.app
```

Restart the backend after changing CORS settings.

### Access Your App

1. **Frontend**: Visit your Vercel URL (e.g., `https://your-app.vercel.app`)
2. **Login**: Use the password you configured during setup
3. **Backend**: Automatically connects to your ngrok URL via environment variables

**Notes:**
- No credentials in URLs - authentication is handled via login screen
- ngrok provides automatic HTTPS (wss:// for WebSockets)
- Keep ngrok running while you want remote access
- Free ngrok URLs change on restart; update `VITE_API_BASE_URL` if needed

## Authentication System

Claude Code Role Play uses JWT token-based authentication with bcrypt password hashing.

### How It Works

**Backend** (`backend/auth.py`):
- JWT tokens sent via `X-API-Key` header (REST) or `api_key` query param (WebSocket)
- Tokens expire after 7 days
- Rate limiting: 5 login attempts per minute per IP
- Endpoints: `POST /auth/login`, `GET /auth/verify`, `GET /health`

**Frontend** (`frontend/src/contexts/AuthContext.tsx`):
- Login screen stores JWT token in localStorage
- Auto-login on page refresh
- Logout clears localStorage

### Security Notes

- Passwords are hashed with bcrypt (never stored in plaintext)
- JWT tokens are signed and time-limited
- Use strong, unique passwords
- Keep `JWT_SECRET` secret and don't commit to git
- WebSocket auth uses query params (browser limitation) - tokens may appear in logs, but they expire

## Troubleshooting

### "Invalid or missing API key"
- Ensure `API_KEY_HASH` is set in `.env` (project root)
- Enter the original password (not the hash) when logging in

### CORS errors
- Add frontend URL to `FRONTEND_URL` in `.env` (project root)
- Check backend startup logs for CORS configuration

### Memory system not working
- Check `MEMORY_BY` environment variable is set correctly
- For RECALL mode: Verify `consolidated_memory.md` exists with `## [subtitle]` format
- For BRAIN mode: Verify `memory_brain.md` has `enabled: true` and `long_term_memory.md` exists
- Enable `DEBUG_AGENTS=true` to see detailed logs

### Database issues
- **Location:** `backend/chitchats.db`
- **Migrations:** Automatic schema updates via `backend/utils/migrations.py`
- **Complete Reset:** Delete file and restart backend to recreate from scratch

## Testing & Simulation

### Run Simulations

```bash
make simulate ARGS='--password "yourpass" --scenario "Discuss AI ethics" --agents "alice,bob,charlie"'
```

**See [SIMULATIONS.md](SIMULATIONS.md) for complete guide.**

### Test Agent Capabilities

```bash
make test-agents ARGS='10 agent1 agent2 agent3'
# 10 questions per agent
```

### Scripts Location

All scripts are now organized in `scripts/` directory:
- `scripts/setup/` - Setup utilities (generate_hash.py)
- `scripts/simulation/` - Simulation scripts
- `scripts/testing/` - Testing scripts

## Common Tasks

**Create agent:** Add folder in `agents/` with required `.md` files using third-person perspective (e.g., "Alice is..." not "You are..."), restart backend

**Update agent:** Edit `.md` files directly (changes apply immediately)

**Update system prompt:** Edit `system_prompt` section in `backend/config/tools/guidelines.yaml` (changes apply immediately)

**Update tool descriptions:** Edit YAML files in `backend/config/tools/` (changes apply immediately)

**Enable debug logging:** Set `DEBUG_AGENTS=true` in `.env` or edit `backend/config/tools/debug.yaml`

**Switch memory mode:** Set `MEMORY_BY=RECALL` or `MEMORY_BY=BRAIN` in `.env`, restart backend

**Add database field:** Update `models.py`, add migration in `backend/utils/migrations.py`, update `schemas.py` and `crud.py`, restart

**Add endpoint:** Define schema in `schemas.py`, add CRUD in `crud.py`, add endpoint in `main.py`
