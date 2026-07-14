# Setup Guide

Complete setup guide for ChitChats, covering database, authentication, deployment, and memory systems.

## Quick Start

### 1. Install Dependencies

```bash
make install
```

### 2. Set Up PostgreSQL

ChitChats uses PostgreSQL with async SQLAlchemy (asyncpg). Create the database once:

```bash
createdb chitchats
```

Then set the connection string in `.env` (this is the default, so it can be omitted if it matches):

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/chitchats
```

Schema migrations run automatically on backend startup (`backend/infrastructure/database/migrations.py`).

**SQLite fallback:** if you don't want to run PostgreSQL, use `make dev-sqlite` (sets `USE_SQLITE=true`).
SQLite is also auto-selected on Windows. See `backend/database.py`.

### 3. Configure Authentication

ChitChats uses JWT token-based authentication with bcrypt password hashing.

**Generate password hash and configure `.env`:**
```bash
make generate-hash
```

This prompts for a password and writes the result straight into `.env`:
- Creates `.env` from `.env.example` if you don't have one yet
- Sets `API_KEY_HASH` to the bcrypt hash of your password
- Fills in a random `JWT_SECRET` if it isn't set yet
- Offers to set `GUEST_PASSWORD_HASH` for read-only guest access

Re-running it is safe: existing values and comments are preserved, an unchanged
`JWT_SECRET` is left alone, and the previous file is backed up to `.env.bak`.

To print the hash instead of writing it (e.g. for a deployment secret store):
```bash
make generate-hash ARGS=--print-only
```

`make env` is a separate, more opinionated alternative: it writes a fresh minimal
`.env` from scratch (SQLite by default) and overwrites any existing one.

**Optional settings:**
```env
USER_NAME=User                    # Display name for user messages
DEBUG_AGENTS=false                # Enable verbose agent logging
ENABLE_GUEST_LOGIN=true           # Allow guest login
GUEST_PASSWORD_HASH=<hash>        # Separate bcrypt hash for guest access
USE_SONNET=false                  # Default to Sonnet instead of Opus
FRONTEND_URL=https://your-app.vercel.app  # CORS for production
```

### 4. Run Development Server

```bash
make dev          # Backend + frontend
make dev-voice    # Backend + frontend + voice TTS server (port 8002)
```

Access:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8001
- API Docs: http://localhost:8001/docs

Login with the password you used to generate the hash.

## Memory System

Agents can use the `recall` tool to fetch specific memories from their long-term memory file when needed.

**Agent structure:**
```
agents/agent_name/
  ├── in_a_nutshell.md           # ✅ Always loaded (required)
  ├── characteristics.md          # ✅ Always loaded (required)
  ├── recent_events.md           # ✅ Always loaded
  └── consolidated_memory.md     # 📋 Parsed into recallable sections
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
# Enter your public backend URL when prompted
# Example: https://your-tunnel.trycloudflare.com
```

Then redeploy:
```bash
vercel --prod
```

### Backend: Cloudflare Tunnel

Requires the `cloudflared` CLI.

```bash
# Terminal 1: Start backend
make run-backend

# Terminal 2: Start Cloudflare tunnel (http://localhost:8001)
make run-tunnel-backend
```

`make run-tunnel-frontend` does the same for the dev frontend (port 5173).

**One-shot production flow:**
```bash
make prod
```
This starts the backend, opens the tunnel, updates `VITE_API_BASE_URL` on Vercel, and triggers a
redeploy (`scripts/deploy/update_vercel_backend_url.sh`). Requires `vercel login` first.

**Update CORS for production:**

Add your Vercel URL to `.env`:
```env
FRONTEND_URL=https://your-app.vercel.app
```

Restart the backend after changing CORS settings.

### Access Your App

1. **Frontend**: Visit your Vercel URL (e.g., `https://your-app.vercel.app`)
2. **Login**: Use the password you configured during setup
3. **Backend**: Automatically connects to your tunnel URL via environment variables

**Notes:**
- No credentials in URLs - authentication is handled via login screen
- Cloudflare tunnels provide automatic HTTPS
- Keep the tunnel running while you want remote access
- Quick tunnel URLs change on restart; update `VITE_API_BASE_URL` if needed (`make prod` does this for you)

## Authentication System

ChitChats uses JWT token-based authentication with bcrypt password hashing.

### How It Works

**Backend** (`backend/core/auth.py`):
- JWT tokens sent via the `X-API-Key` header
- Tokens expire after 7 days
- Rate limiting: 20 login attempts per minute per IP
- Endpoints: `POST /auth/login`, `POST /auth/logout`, `GET /auth/verify`, `GET /auth/health`
- SSE connections use a short-lived (60s), room-scoped ticket from `POST /rooms/{id}/sse-ticket`,
  because `EventSource` cannot send custom headers

**Frontend** (`frontend/src/contexts/AuthContext.tsx`):
- Login screen stores JWT token in localStorage
- Auto-login on page refresh
- Logout clears localStorage

### Security Notes

- Passwords are hashed with bcrypt (never stored in plaintext)
- JWT tokens are signed and time-limited
- Use strong, unique passwords
- Keep `JWT_SECRET` secret and don't commit to git
- SSE tickets appear in URLs/logs, but they are room-scoped and expire in 60 seconds

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
- **Connection:** Set via `DATABASE_URL` (PostgreSQL, asyncpg driver)
- **Migrations:** Automatic schema updates via `backend/infrastructure/database/migrations.py`
- **Complete Reset:** `dropdb chitchats && createdb chitchats`, then restart the backend
- **SQLite mode:** database file is `./chitchats.db`; delete it and restart to reset

## Testing & Simulation

### Run Simulations

```bash
make simulate ARGS='--password "yourpass" --scenario "Discuss AI ethics" --agents "alice,bob,charlie"'
# Run with no ARGS to print the script's --help
```

### Test Agent Capabilities

```bash
./scripts/testing/test_agent_questions.sh 10 agent1 agent2 agent3
# 10 questions per agent
```

### Scripts Location

All scripts are organized in the `scripts/` directory:
- `scripts/setup/` - Setup utilities (`generate_hash.py`, `create_env.py`)
- `scripts/simulation/` - Simulation scripts (`simulate_chatroom.sh`)
- `scripts/testing/` - Testing scripts
- `scripts/deploy/` - Deployment helpers
- `scripts/windows/` - Windows dev/build scripts

## Common Tasks

**Create agent:** Add folder in `agents/` with required `.md` files using third-person perspective (e.g., "Alice is..." not "You are..."), restart backend

**Update agent:** Edit `.md` files directly

**Update system prompt:** Edit `backend/providers/claude/prompts.yaml` (or `backend/providers/codex/prompts.yaml`), selecting the active prompt via `active_system_prompt`

**Update guidelines:** Edit the `<guidelines>` block inside the active `system_prompt_*` in the provider's `prompts.yaml`

**Update tool descriptions:** Edit the `TOOLS` registry in `backend/mcp_servers/config/tools.py`

**Enable debug logging:** Set `DEBUG_AGENTS=true` in `.env` or edit `backend/mcp_servers/config/debug.yaml`

**Add database field:** Update `backend/infrastructure/database/models.py`, add a migration in `backend/infrastructure/database/migrations.py`, update `backend/schemas/` and `backend/crud/`, restart

**Add endpoint:** Define schema in `backend/schemas/`, add CRUD in `backend/crud/`, add the route to a router in `backend/routers/`, and wire it up in `backend/core/app_factory.py` if it's a new router
