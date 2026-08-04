.PHONY: test-backend test-e2e build-backend db-upgrade db-revision

# Run backend tests inside the app container (Python 3.11, pinned deps).
# Note: aiosqlite (added for tests) requires a backend image rebuild:
#   make build-backend
test-backend:
	docker compose exec backend python -m pytest -v

# Run frontend E2E regression (needs Chromium on 127.0.0.1:9222, see tests/e2e/README.md)
test-e2e:
	bash tests/e2e/run-e2e.sh

# Rebuild the backend image (picks up requirements.txt changes)
build-backend:
	docker compose build backend
	docker compose up -d backend

# Apply pending alembic migrations (also runs automatically on container start)
db-upgrade:
	docker compose exec backend alembic upgrade head

# Autogenerate a new migration from model changes (review it before committing!)
db-revision:
	@echo "Usage: make db-revision MSG='description of change'"
	@echo "Hint: set DATABASE_URL to an EMPTY throwaway DB before running,"
	@echo "e.g. DATABASE_URL=postgresql+asyncpg://workflow_user:workflow_password@postgres:5432/workflow_db_empty"
	docker compose exec -e DATABASE_URL="$(DATABASE_URL)" backend alembic revision --autogenerate -m "$(MSG)"
