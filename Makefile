.PHONY: help install run-backend run-frontend run-tunnel-backend run-tunnel-frontend dev prod stop clean generate-hash simulate test-agents evaluate-agents evaluate-agents-cross load-test test-jane test-jane-questions evaluate-jane-full extract-signature

# Use bash for all commands
SHELL := /bin/bash

help:
	@echo "ChitChats - Available commands:"
	@echo ""
	@echo "Development:"
	@echo "  make dev               - Run backend + frontend (local development)"
	@echo "  make install           - Install all dependencies (backend + frontend)"
	@echo "  make run-backend       - Run backend server only"
	@echo "  make run-frontend      - Run frontend server only"
	@echo ""
	@echo "Setup:"
	@echo "  make generate-hash     - Generate password hash for authentication"
	@echo ""
	@echo "Testing & Simulation:"
	@echo "  make simulate          - Run chatroom simulation (requires args)"
	@echo "  make test-agents       - Test agent capabilities (THINKING=1 to show thinking, CHECK_ANT=1 to show model)"
	@echo "  make evaluate-agents   - Evaluate agent authenticity (sequential)"
	@echo "  make evaluate-agents-cross - Cross-evaluate two agents (SLOWER=1, SPEAKER=user|{char}, PROVIDER=claude|codex)"
	@echo "  make load-test         - Run network load test (requires args)"
	@echo ""
	@echo "Humanness Evaluation:"
	@echo "  make test-jane         - Test answer humanness (pairs 5-9 sampled, SAMPLED=0 for full)"
	@echo "  make test-jane-questions - Legacy: Test question generation quality"
	@echo "  make evaluate-jane-full - Run full evaluation on all datasets"
	@echo ""
	@echo "Deployment (Cloudflare tunnels for remote access):"
	@echo "  make prod              - Start tunnel + auto-update Vercel env + redeploy"
	@echo "  make run-tunnel-backend - Run Cloudflare tunnel for backend"
	@echo "  make run-tunnel-frontend- Run Cloudflare tunnel for frontend"
	@echo ""
	@echo "Maintenance:"
	@echo "  make stop              - Stop all running servers"
	@echo "  make clean             - Clean build artifacts and caches"
	@echo "  make extract-signature - Extract thinking signatures from session files"

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
	@mkdir -p /tmp/claude-empty
	@echo "Starting backend and frontend..."
	@echo "Backend will run on http://localhost:8000"
	@echo "Frontend will run on http://localhost:5173"
	@echo "For remote access, run 'make run-tunnel-backend' and 'make run-tunnel-frontend' in separate terminals"
	@echo "Press Ctrl+C to stop all servers"
# 	@$(MAKE) -j3 run-backend run-frontend run-tunnel-backend
	@$(MAKE) -j3 run-backend run-frontend

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

test-agents:
	@echo "Testing agent capabilities..."
	@if [ -n "$(THINKING)" ]; then \
		CHECK_ANT=$(CHECK_ANT) ./scripts/testing/test_agent_questions.sh --quiet --thinking; \
	else \
		CHECK_ANT=$(CHECK_ANT) ./scripts/testing/test_agent_questions.sh --quiet; \
	fi

evaluate-agents:
	@echo "Evaluating agent authenticity..."
	@echo "Usage: make evaluate-agents ARGS='--target-agent \"프리렌\" --evaluator \"페른\" --questions 3'"
	@if [ -z "$(ARGS)" ]; then \
		./scripts/evaluation/evaluate_authenticity.sh --help; \
	else \
		./scripts/evaluation/evaluate_authenticity.sh $(ARGS); \
	fi

evaluate-agents-cross:
	@echo "Cross-evaluating agents (both directions)..."
	@echo "Usage: make evaluate-agents-cross AGENT1=\"프리렌\" AGENT2=\"페른\" QUESTIONS=7 [SLOWER=1] [PARALLEL=5] [SPEAKER=user|{character}] [PROVIDER=claude|codex]"
	@if [ -z "$(AGENT1)" ] || [ -z "$(AGENT2)" ]; then \
		echo "Error: Both AGENT1 and AGENT2 must be specified."; \
		echo "Example: make evaluate-agents-cross AGENT1=\"프리렌\" AGENT2=\"페른\" QUESTIONS=7"; \
		exit 1; \
	fi; \
	QUESTIONS=$${QUESTIONS:-7}; \
	PARALLEL_LIMIT=$${PARALLEL:-7}; \
	SPEAKER_ARG=""; \
	if [ -n "$(SPEAKER)" ]; then \
		SPEAKER_ARG="--speaker $(SPEAKER)"; \
	fi; \
	PROVIDER_ARG=""; \
	if [ -n "$(PROVIDER)" ]; then \
		PROVIDER_ARG="--provider $(PROVIDER)"; \
	fi; \
	if [ -n "$(SLOWER)" ]; then \
		echo "Running $(AGENT1) → $(AGENT2) and $(AGENT2) → $(AGENT1) evaluations sequentially..."; \
		./scripts/evaluation/evaluate_parallel.sh --target-agent "$(AGENT2)" --evaluator "$(AGENT1)" --questions $$QUESTIONS --parallel-limit $$PARALLEL_LIMIT $$SPEAKER_ARG $$PROVIDER_ARG; \
		./scripts/evaluation/evaluate_parallel.sh --target-agent "$(AGENT1)" --evaluator "$(AGENT2)" --questions $$QUESTIONS --parallel-limit $$PARALLEL_LIMIT $$SPEAKER_ARG $$PROVIDER_ARG; \
	else \
		echo "Running $(AGENT1) → $(AGENT2) and $(AGENT2) → $(AGENT1) evaluations in parallel..."; \
		./scripts/evaluation/evaluate_parallel.sh --target-agent "$(AGENT2)" --evaluator "$(AGENT1)" --questions $$QUESTIONS --parallel-limit $$PARALLEL_LIMIT $$SPEAKER_ARG $$PROVIDER_ARG & \
		PID1=$$!; \
		./scripts/evaluation/evaluate_parallel.sh --target-agent "$(AGENT1)" --evaluator "$(AGENT2)" --questions $$QUESTIONS --parallel-limit $$PARALLEL_LIMIT $$SPEAKER_ARG $$PROVIDER_ARG & \
		PID2=$$!; \
		wait $$PID1 $$PID2; \
	fi; \
	echo "Both evaluations completed!"

load-test:
	@echo "Running network load test..."
	@echo "Usage: make load-test ARGS='--password \"yourpass\" --users 10 --rooms 2 --duration 60'"
	@if [ -z "$(ARGS)" ]; then \
		uv run python scripts/testing/load_test_network.py --help; \
	else \
		uv run python scripts/testing/load_test_network.py $(ARGS); \
	fi

# Humanness Evaluation Pipeline
# Usage: make test-jane DATASET=workforce AGENTS=jane LIMIT=10 MIN_PAIR=5 MAX_PAIR=10 SAMPLED=1
# Tests which answer (AI vs human) looks most human
DATASET ?= workforce
AGENTS ?= jane
PARALLEL ?= 5
MIN_PAIR ?= 5
MAX_PAIR ?= 10
SAMPLED ?= 1

test-jane:
	@echo "Testing answer humanness..."
	@echo "Dataset: $(DATASET)"
	@echo "Agents:  $(AGENTS)"
	@echo "Pair range: $(MIN_PAIR)-$$(( $(MAX_PAIR) - 1 ))"
	@if [ "$(SAMPLED)" = "1" ]; then \
		echo "Mode: Sampled (20 pairs)"; \
		./scripts/evaluation/parse_transcripts.sh --dataset $(DATASET) --sample 20 --min-pair $(MIN_PAIR) --max-pair $(MAX_PAIR); \
	else \
		echo "Mode: Full dataset"; \
		./scripts/evaluation/parse_transcripts.sh --dataset $(DATASET) --min-pair $(MIN_PAIR) --max-pair $(MAX_PAIR); \
	fi
	@echo ""
	@echo "Running humanness evaluation..."
	@RESULTS=$$(./scripts/evaluation/evaluate_humanness.sh --dataset $(DATASET) --agents "$(AGENTS)" --parallel $(PARALLEL) $(if $(LIMIT),--limit $(LIMIT),) $(if $(NO_HUMAN),--no-human,)); \
	echo ""; \
	echo "Analyzing results..."; \
	uv run python scripts/evaluation/analyze_results.py "$$RESULTS"

# Legacy question evaluation (evaluates question quality, not humanness)
test-jane-questions:
	@echo "Testing Jane's question generation..."
	@echo "Dataset: $(DATASET)"
	@echo "Parallel: $(PARALLEL)"
	@if [ "$(SAMPLED)" = "1" ]; then \
		echo "Mode: Sampled (20 pairs)"; \
		./scripts/evaluation/parse_transcripts.sh --dataset $(DATASET) --sample 20; \
	else \
		echo "Mode: Full dataset"; \
		./scripts/evaluation/parse_transcripts.sh --dataset $(DATASET); \
	fi
	@echo ""
	@echo "Running question evaluation ($(PARALLEL) parallel)..."
	@RESULTS=$$(./scripts/evaluation/evaluate_questions.sh --dataset $(DATASET) --parallel $(PARALLEL) $(if $(LIMIT),--limit $(LIMIT),)); \
	echo ""; \
	echo "Analyzing results..."; \
	uv run python scripts/evaluation/analyze_results.py "$$RESULTS"

evaluate-jane-full:
	@echo "Running full evaluation on all datasets..."
	@echo "This will evaluate: creatives, scientists, workforce"
	@echo "Warning: This may take several hours!"
	@echo ""
	@for dataset in creatives scientists workforce; do \
		echo "========================================"; \
		echo "Evaluating: $$dataset"; \
		echo "========================================"; \
		$(MAKE) test-jane DATASET=$$dataset; \
		echo ""; \
	done
	@echo "All evaluations complete!"
	@echo ""
	@echo "Comparing results..."
	@uv run python scripts/evaluation/analyze_results.py --compare results/evaluations/*.json 2>/dev/null || echo "Run individual analyses with: uv run python scripts/evaluation/analyze_results.py results/evaluations/<file>.json"

extract-signature:
	@echo "Extracting thinking signatures from session files..."
	@python3 scripts/collect_thinking_signatures.py > scripts/output.py
	@echo "Saved to scripts/output.py"
