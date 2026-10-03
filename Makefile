.PHONY: setup dev stop livekit api agent web test build

# `make dev` also starts a local LiveKit server when backend/.env.local points at one.
LOCAL_LIVEKIT := $(shell grep -Eqs '^LIVEKIT_URL=wss?://(127\.0\.0\.1|localhost)' backend/.env.local && echo livekit)

setup: ## Install backend and frontend dependencies
	cd backend && uv sync
	cd frontend && npm install

dev: ## Run everything together (Ctrl-C stops all)
	$(MAKE) -j4 $(LOCAL_LIVEKIT) api agent web

stop: ## Stop a running local stack: LiveKit, API, agent and web app
	-pkill -f "livekit-server --dev"
	-pkill -f "uvicorn app.server:app"
	-pkill -f "app.agent dev"
	-pkill -f "node_modules/.bin/vite"

livekit: ## Local LiveKit server on ws://127.0.0.1:7880 (brew install livekit)
	livekit-server --dev --bind 127.0.0.1

api: ## FastAPI on http://localhost:8000
	cd backend && uv run uvicorn app.server:app --reload --port 8000

agent: ## LiveKit agent worker
	cd backend && uv run python -m app.agent dev

web: ## Web app on http://localhost:5173
	cd frontend && npm run dev

test: ## Backend tests, frontend type check and lint
	cd backend && uv run pytest -q
	cd frontend && npm run typecheck && npm run lint

build: ## Build the web app; the API then serves it on :8000
	cd frontend && npm run build
