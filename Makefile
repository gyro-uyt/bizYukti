.PHONY: up down logs dev-api dev-web worker seed reset migrate test typecheck build prod
up: ; docker compose up --build -d && echo "Open http://localhost:3000"
down: ; docker compose down
logs: ; docker compose logs -f api web worker
migrate: ; cd backend && alembic upgrade head
seed: ; cd backend && python -m app.seed --if-empty
reset: ; cd backend && python -m app.seed --reset
dev-api: ; cd backend && uvicorn app.main:app --reload --port 8000
worker: ; cd backend && python -m app.worker.worker
dev-web: ; cd frontend && npm run dev
test: ; cd backend && python -m pytest -q -p no:logging
typecheck: ; cd frontend && npm run typecheck
build: ; cd frontend && npm run build
prod: ; docker compose -f docker-compose.prod.yml --env-file .env up -d --build
