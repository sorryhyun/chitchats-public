# Setup Guide

Complete setup guide for ChitChats, covering authentication, deployment, and memory systems.

## Quick Start

### 1. Install Dependencies

```bash
make install
```

### 2. Configure Authentication

ChitChats uses JWT token-based authentication with bcrypt password hashing.

**Generate password hash:**
```bash
make generate-hash
# Or directly:
# uv run python scripts/setup/generate_hash.py
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
FRONTEND_URL=https://your-app.vercel.app  # CORS for production
```

### 3. Run Development Server

```bash
make dev
```

Access:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8001
- API Docs: http://localhost:8001/docs

Login with the password you used to generate the hash.

## Memory System

Agents can use the `recall` tool to fetch specific memories from their long-term memory file when needed.

**Configuration (optional):**
```env
RECALL_MEMORY_FILE=consolidated_memory  # Default value
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

ChitChats uses JWT token-based authentication with bcrypt password hashing.

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
- Verify `consolidated_memory.md` exists with `## [subtitle]` format
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

**Update agent:** Edit `.md` files directly

**Update system prompt:** Edit `system_prompt` section in `backend/config/tools/guidelines_3rd.yaml`

**Update tool descriptions:** Edit YAML files in `backend/config/tools/`

**Enable debug logging:** Set `DEBUG_AGENTS=true` in `.env` or edit `backend/config/tools/debug.yaml`

**Add database field:** Update `models.py`, add migration in `backend/utils/migrations.py`, update `schemas.py` and `crud.py`, restart

**Add endpoint:** Define schema in `schemas.py`, add CRUD in `crud.py`, add endpoint in `main.py`
