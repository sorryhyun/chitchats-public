**🌐 Language: [한국어](README.md) | English**

# ChitChats

A real-time multi-agent chat application where multiple AI personalities interact in shared rooms. Supports multiple AI providers (Claude and Codex).

## Features

- **Multi-agent conversations** - Multiple AI agents with distinct personalities chat together
- **Multi-provider support** - Choose between Claude or Codex when creating rooms
- **HTTP Polling** - Real-time message updates via polling (2-second intervals for messages and status)
- **Agent customization** - Configure personalities via markdown files with profile pictures
- **1-on-1 direct chats** - Private conversations with individual agents
- **Extended thinking** - View agent reasoning process (32K thinking tokens)
- **JWT Authentication** - Secure password-based authentication with token expiration
- **Rate limiting** - Protection against brute force attacks on all endpoints

## Tech Stack

**Backend:** FastAPI, SQLAlchemy (async), PostgreSQL, Multi-provider AI (Claude SDK, Codex CLI)
**Frontend:** React, TypeScript, Vite, Tailwind CSS

## Prerequisites (Windows)

To use on Windows, you need to install at least one of the following:

- **Claude Code** - Install from [claude.ai/code](https://claude.ai/code)
- **Codex** - Download Windows version from [GitHub Releases](https://github.com/openai/codex/releases)

You can select the installed provider when creating a room.

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

## Simulation

```bash
make simulate ARGS='-s "Discuss AI ethics" -a "alice,bob,charlie"'
```

See [SETUP.md](SETUP.md) for details.

## Agent Configuration

Agents use a folder-based structure in `agents/` with markdown files for personality and memories. All changes are hot-reloaded without restart.

See [CLAUDE.md](CLAUDE.md) for detailed configuration options including third-person perspective requirements, tool configuration, and group behavior settings.

## Commands

```bash
make dev           # Run full stack
make install       # Install dependencies
make stop          # Stop servers
make clean         # Clean build artifacts
```

## API

Core endpoints for authentication, rooms, agents, and messaging. All endpoints except `/auth/*` and `/health` require JWT authentication via `X-API-Key` header.

See [backend/README.md](backend/README.md) for the full API reference.

## Deployment

For production deployment with Vercel frontend + ngrok backend, see [SETUP.md](SETUP.md).

**Deployment Strategy:**
- **Backend:** Local machine with ngrok tunnel (or cloud hosting of your choice)
- **Frontend:** Vercel (or other static hosting)
- **CORS:** Configure via `FRONTEND_URL` in backend `.env`
- **Authentication:** Password/JWT based (see [SETUP.md](SETUP.md))

## Configuration

**Required:** `API_KEY_HASH`, `JWT_SECRET` in backend `.env` file.

See [SETUP.md](SETUP.md) for authentication setup and [backend/README.md](backend/README.md) for all configuration options.
