.PHONY: help install run-backend run-frontend run-tunnel-backend run-tunnel-frontend dev dev-win dev-sqlite prod stop clean env generate-hash simulate build-exe

# Use bash for all commands
SHELL := /bin/bash

help:
	@echo "ChitChats - Available commands:"
	@echo ""
	@echo "Development:"
	@echo "  make dev               - Run backend + frontend (PostgreSQL)"
	@echo "  make dev-win           - Run backend + frontend (Windows, clean Ctrl+C)"
	@echo "  make dev-sqlite        - Run backend + frontend (SQLite)"
	@echo "  make install           - Install all dependencies (backend + frontend)"
	@echo "  make run-backend       - Run backend server only"
	@echo "  make run-frontend      - Run frontend server only"
	@echo ""
	@echo "Build:"
	@echo "  make build-exe         - Build Windows executable (requires PowerShell)"
	@echo ""
	@echo "Setup:"
	@echo "  make env               - Create .env file (prompts for password)"
	@echo "  make generate-hash     - Generate password hash for authentication"
	@echo ""
	@echo "Simulation:"
	@echo "  make simulate          - Run chatroom simulation (requires args)"
	@echo ""
	@echo "Deployment (Cloudflare tunnels for remote access):"
	@echo "  make prod              - Start tunnel + auto-update Vercel env + redeploy"
	@echo "  make run-tunnel-backend - Run Cloudflare tunnel for backend"
	@echo "  make run-tunnel-frontend- Run Cloudflare tunnel for frontend"
	@echo ""
	@echo "Maintenance:"
	@echo "  make stop              - Stop all running servers"
	@echo "  make clean             - Clean build artifacts and caches"

install:
	@echo "Installing Claude Code CLI globally..."
	sudo npm install -g @anthropic-ai/claude-code || echo "Warning: Failed to install Claude Code CLI globally. You may need to run with sudo."
	@echo "Installing backend dependencies with uv..."
	uv sync
	@echo "Installing frontend dependencies..."
	cd frontend && npm install
	@echo "Done!"

run-backend:
	@echo "Starting backend server..."
	cd backend && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8001

run-frontend:
	@echo "Starting frontend server..."
	cd frontend && npm run dev

run-tunnel-backend:
	@echo "Starting Cloudflare tunnel for backend..."
	cloudflared tunnel --url http://localhost:8001

run-tunnel-frontend:
	@echo "Starting Cloudflare tunnel for frontend..."
	cloudflared tunnel --url http://localhost:5173

dev:
	@echo "Starting backend and frontend..."
	@echo "Backend will run on http://localhost:8000"
	@echo "Frontend will run on http://localhost:5173"
	@echo "For remote access, run 'make run-tunnel-backend' and 'make run-tunnel-frontend' in separate terminals"
	@echo "Press Ctrl+C to stop all servers"
# 	@$(MAKE) -j3 run-backend run-frontend run-tunnel-backend
	@$(MAKE) -j3 run-backend run-frontend

dev-win:
	@echo "Starting backend and frontend (Windows)..."
	@powershell.exe -ExecutionPolicy Bypass -File scripts/windows/dev.ps1

dev-sqlite:
	@echo "Starting backend and frontend with SQLite..."
	@echo "Backend will run on http://localhost:8000"
	@echo "Frontend will run on http://localhost:5173"
	@echo "SQLite database: ./chitchats.db"
	@echo "Press Ctrl+C to stop all servers"
	USE_SQLITE=true $(MAKE) -j3 run-backend run-frontend

prod:
	@echo "Starting production deployment..."
	@echo "This will:"
	@echo "  1. Start backend server (port 8001)"
	@echo "  2. Start cloudflared tunnel"
	@echo "  3. Auto-update VITE_API_BASE_URL on Vercel"
	@echo "  4. Trigger Vercel redeploy"
	@echo ""
	@echo "Prerequisites: vercel CLI logged in (run 'vercel login' first)"
	@echo ""
	@# Start backend in background (port 8001 to avoid conflict with dev)
	@cd backend && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8001 &
	@sleep 2
	@# Run tunnel script (handles URL detection, Vercel update, and redeploy)
	@./scripts/deploy/update_vercel_backend_url.sh

stop:
	@echo "Stopping servers..."
	@pkill -f "uvicorn main:app" || true
	@pkill -f "vite" || true
	@pkill -f "cloudflared" || true
	@echo "Servers stopped."

clean:
	@echo "Cleaning build artifacts..."
	rm -rf backend/__pycache__
	rm -rf backend/**/__pycache__
	rm -rf backend/*.db
	rm -rf frontend/dist
	rm -rf frontend/node_modules/.vite
	@echo "Clean complete!"

env:
	@echo "Creating .env file..."
	@uv run python scripts/setup/create_env.py

generate-hash:
	@echo "Generating password hash..."
	uv run python scripts/setup/generate_hash.py

simulate:
	@echo "Running chatroom simulation..."
	@echo "Usage: make simulate ARGS='--password \"yourpass\" --scenario \"text\" --agents \"agent1,agent2\"'"
	@if [ -z "$(ARGS)" ]; then \
		./scripts/simulation/simulate_chatroom.sh --help; \
	else \
		./scripts/simulation/simulate_chatroom.sh $(ARGS); \
	fi

# Windows executable build
# Requires PowerShell (pwsh on Linux/macOS, powershell.exe on Windows)
build-exe:
	@echo "Building Windows executable..."
	@if command -v pwsh >/dev/null 2>&1; then \
		echo "Using PowerShell Core (pwsh)..."; \
		pwsh -ExecutionPolicy Bypass -File scripts/windows/build_exe.ps1 $(if $(CLEAN),-Clean,) $(if $(SKIP_FRONTEND),-SkipFrontend,); \
	elif command -v powershell.exe >/dev/null 2>&1; then \
		echo "Using Windows PowerShell via WSL..."; \
		powershell.exe -ExecutionPolicy Bypass -File scripts/windows/build_exe.ps1 $(if $(CLEAN),-Clean,) $(if $(SKIP_FRONTEND),-SkipFrontend,); \
	else \
		echo ""; \
		echo "PowerShell not found. To build the Windows executable:"; \
		echo ""; \
		echo "  Option 1: Install PowerShell Core"; \
		echo "    Ubuntu/Debian: sudo apt install powershell"; \
		echo "    macOS: brew install powershell"; \
		echo ""; \
		echo "  Option 2: Run directly on Windows"; \
		echo "    .\\scripts\\windows\\build_exe.ps1"; \
		echo ""; \
		echo "  Options:"; \
		echo "    -Clean         Clean build artifacts first"; \
		echo "    -SkipFrontend  Skip frontend build (use existing dist)"; \
		exit 1; \
	fi
