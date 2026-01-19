# ChitChats

A real-time multi-agent chat application where multiple Claude AI personalities interact in shared rooms.

## Features

- **Multi-agent conversations** - Multiple Claude agents with distinct personalities chat together
- **HTTP Polling** - Real-time message updates via polling (2-second intervals for messages and status)
- **Agent customization** - Configure personalities via markdown files with profile pictures
- **1-on-1 direct chats** - Private conversations with individual agents
- **Extended thinking** - View agent reasoning process (32K thinking tokens)
- **JWT Authentication** - Secure password-based authentication with token expiration
- **Rate limiting** - Protection against brute force attacks on all endpoints

## Tech Stack

**Backend:** FastAPI, SQLAlchemy (async), PostgreSQL, Anthropic Claude SDK
**Frontend:** React, TypeScript, Vite, Tailwind CSS

## Quick Start

### 1. Install Dependencies

```bash
make install
```

### 2. Configure Authentication

```bash
make generate-hash  # Generate password hash
python -c "import secrets; print(secrets.token_hex(32))"  # Generate JWT secret
cp .env.example .env  # Add API_KEY_HASH and JWT_SECRET to .env
```

See [SETUP.md](SETUP.md) for details.

### 3. Run & Access

```bash
make dev
```

Open http://localhost:5173 and login with your password.

## Simulation & Testing

**Run simulations:**
```bash
make simulate ARGS='-s "Discuss AI ethics" -a "alice,bob,charlie"'
# Or use the script directly:
# ./scripts/simulation/simulate_chatroom.sh -s "..." -a "..."
```

**Test agents:**
```bash
make test-agents ARGS='10 agent1 agent2 agent3'
```
or
```bash
make evaluate-agents ARGS='--target-agent "프리렌" --evaluator "페른" --questions 2'
```
or
```bash
./scripts/simulation/simulate_chatroom.sh -s "덴지와 레제가 전투 후 카페에서 만나기로 한 날, 덴지는 우연히 마키마가 레제를 죽이려고 하려는 찰나를 목격한다. 덴지가 '아' 라고 하는 순간, 마키마는 레제에게 손가락을 겨누고 '빵'이라고 말했다. (다른 캐릭터들이 아닌, 마키마가 쏠 위치를 정한다)" -a "덴지,레제,마키마" --max-interactions 10 -p sorrysorry --variants 3 --no-thinking
```

See [SIMULATIONS.md](SIMULATIONS.md) and [SETUP.md](SETUP.md) for details.

## Agent Configuration

Agents are configured using a folder-based structure in the `agents/` directory:

```
agents/
  agent_name/
    ├── in_a_nutshell.md       # Brief identity summary (third-person)
    ├── characteristics.md      # Personality traits (third-person)
    ├── recent_events.md       # Auto-updated from conversations
    ├── anti_pattern.md        # Behaviors to avoid (optional)
    ├── consolidated_memory.md # Long-term memories with subtitles (optional)
    └── profile.*              # Optional profile picture (png, jpg, jpeg, gif, webp, svg)
```

Add optional profile pictures (png, jpg, jpeg, gif, webp, svg) to agent folders. Changes take effect immediately without restart.

**Tool Configuration:** Agent behavior guidelines and debug settings are configured via YAML files in `backend/config/tools/`. Switch between guideline versions or enable debug logging without code changes. See [CLAUDE.md](CLAUDE.md) for details.

## Commands

```bash
make dev           # Run full stack
make install       # Install dependencies
make stop          # Stop servers
make clean         # Clean build artifacts
```

## API

**Authentication:**
- `POST /auth/login` - Login with password, returns JWT token
- `GET /auth/verify` - Verify current JWT token

**Rooms:**
- `POST /rooms` - Create room
- `GET /rooms` - List all rooms
- `GET /rooms/{id}` - Get room details
- `DELETE /rooms/{id}` - Delete room

**Agents:**
- `GET /agents` - List agents
- `POST /agents` - Create agent from config
- `GET /agents/{id}/direct-room` - Get 1-on-1 room
- `PATCH /agents/{id}` - Update agent persona
- `GET /agents/{name}/profile-pic` - Get agent profile picture

**Messages & Polling:**
- `GET /rooms/{id}/messages/poll?since_id={id}` - Poll for new messages (rate limited: 60/min)
- `POST /rooms/{id}/messages/send` - Send message and trigger agent responses (rate limited: 30/min)
- `GET /rooms/{id}/chatting-agents` - Get list of agents currently responding (rate limited: 120/min)
- `DELETE /rooms/{id}/messages` - Clear all messages (Admin only)

See [backend/README.md](backend/README.md) for full API reference and [SETUP.md](SETUP.md) for auth details.

## Deployment

For production deployment with Vercel frontend + ngrok backend, see [SETUP.md](SETUP.md).

**Deployment Strategy:**
- **Backend:** Local machine with ngrok tunnel (or cloud hosting of your choice)
- **Frontend:** Vercel (or other static hosting)
- **CORS:** Configure via `FRONTEND_URL` in backend `.env`
- **Authentication:** Password/JWT based (see [SETUP.md](SETUP.md))

## Configuration

**Backend `.env`:** `API_KEY_HASH` (required), `JWT_SECRET` (required), `USER_NAME`, `DEBUG_AGENTS`, `FRONTEND_URL`

**Frontend `.env`:** `VITE_API_BASE_URL` (default: http://localhost:8001)

See [SETUP.md](SETUP.md) and [backend/README.md](backend/README.md) for details.
