# Testing Guide

## Test Overview

The Python Workflow System has three layers of testing:

1. **Backend Unit/Integration Tests** (pytest) — 141 tests, run against PostgreSQL
2. **E2E Tests** (Puppeteer + Chromium) — 10 tests, verify full stack
3. **Manual Testing** — API exploration, designer UX, portal flows

## Running Tests

### Backend Tests

```bash
# Run all backend tests
make test-backend

# Run specific test file
docker compose exec backend python -m pytest backend/tests/test_workflow.py -v

# Run specific test class
docker compose exec backend python -m pytest backend/tests/test_engine_behavior.py::TestExecutors -v

# Run specific test
docker compose exec backend python -m pytest backend/tests/test_engine_behavior.py::TestExecutors::test_api_call_ssrf_protection_blocks_loopback -v

# Run with coverage
docker compose exec backend python -m pytest --cov=app --cov-report=term-missing

# Run only failing tests (from previous run)
docker compose exec backend python -m pytest --lf
```

### E2E Tests

```bash
# Run all E2E tests
make test-e2e

# Run specific E2E script
bash tests/e2e/run-e2e.sh smoke

# Run with CDP recording (Chromium DevTools Protocol)
E2E_CDP=http://127.0.0.1:9222 make test-e2e
```

### Test Commands Reference

| Command | Description |
|---------|-------------|
| `make test-backend` | Run all backend tests |
| `make test-e2e` | Run all E2E tests |
| `make build-backend` | Rebuild backend Docker image |
| `make db-upgrade` | Run alembic migrations |
| `make db-revision` | Generate new alembic migration |

## Test Structure

### Backend Tests

**Location**: `backend/tests/`

- `test_workflow.py` — Workflow CRUD, AI service, step executors (11 tests)
- `test_engine_behavior.py` — Engine regression net, condition contract, admin notices, timeout/retries, SSRF protection (65 tests)

**Key Test Classes**:
- `TestWorkflowEngine` — CRUD operations
- `TestAIService` — AI step generation validation
- `TestStepExecutors` — All executor types
- `TestRouting` — Condition routing logic
- `TestEngineLinear` — Linear workflow execution
- `TestEngineGraph` — Graph-mode execution (fan-out, conditions)
- `TestHumanStep` — Human task pause/resume
- `TestAdminNotice` — Email notification system
- `TestTimeout` — Run timeout handling
- `TestRetries` — Step retry logic
- `TestFailureHooks` — Failure hook execution
- `TestWebhooks` — Webhook secret verification
- `TestScheduler` — Scheduler integration
- `TestExecutors` — All executor types (email, DB, form, custom code, webhook, calculation, report, AI condition, programmable delay, SSRF)

### E2E Tests

**Location**: `tests/e2e/`

- `smoke.js` — Login, branding, workflow list, settings
- `designer-save.js` — Designer save/cancel, edge rendering, reload persistence

**Test Flow**:
1. Start services (`docker compose up -d`)
2. Run migrations (`make db-upgrade`)
3. Execute E2E script via Docker container
4. Verify assertions in test output

## Test Data

### Test Database

Tests use a dedicated **PostgreSQL** database (`workflow_db_test`, auto-created on first
run — override with `TEST_DATABASE_URL`). The `public` schema is dropped/recreated for
every test, so runs are fully isolated:

```python
@pytest_asyncio.fixture
async def db_engine():
    # backend/tests/conftest.py — see TEST_DATABASE_URL there
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()
```

### Test Fixtures

- `db_engine` — Fresh-schema PostgreSQL engine (from `tests/conftest.py`)
- `session` — Async session for test database
- `engine` — WorkflowEngine with patched `async_session_factory`
- `monkeypatch` — Standard pytest monkeypatch

### Live Database (Development)

For manual testing against live PostgreSQL:

```bash
# Connect to live DB
docker compose exec postgres psql -U workflow_user -d workflow_db

# Check migrations
docker compose exec backend alembic current

# Rollback last migration
docker compose exec backend alembic downgrade -1
```

## Debugging Tests

### Backend Test Failures

```bash
# Run with verbose output
docker compose exec backend python -m pytest -v

# Run with full traceback
docker compose exec backend python -m pytest --tb=long

# Run with logging
docker compose exec backend python -m pytest -s -v

# Debug specific test
docker compose exec backend python -c "
import asyncio
from tests.test_engine_behavior import TestExecutors
t = TestExecutors()
asyncio.run(t.test_api_call_ssrf_protection_blocks_loopback())
"
```

### E2E Test Failures

```bash
# Run with browser visible (for debugging)
docker compose exec e2e bash
cd /app/tests/e2e
node smoke.js  # Run individual script

# Check Chromium logs
docker logs pythonworkflow-e2e

# Inspect network requests
# Set E2E_CDP=http://127.0.0.1:9222/json/version
```

### Common Issues

1. **Test uses stale data**: Each test gets a fresh schema; if you see cross-test state, check for module-level caches
2. **Session conflicts**: Use `await session.refresh(obj)` to reload from DB
3. **Async timing**: Add `await asyncio.sleep(0.1)` for background tasks
4. **Port conflicts**: Ensure no other services on ports 5432, 6000, 9000

## Test Coverage Goals

| Component | Target Coverage | Current |
|-----------|----------------|---------|
| Workflow Engine | 90% | ~85% |
| Executors | 95% | ~90% |
| API Endpoints | 80% | ~75% |
| Frontend Components | 70% | N/A (no frontend tests) |

## Performance Testing

### Load Testing (Manual)

```bash
# Trigger multiple workflows concurrently
for i in {1..10}; do
  curl -s -X POST http://localhost:6000/workflows/1/run &
done
wait

# Check run status
curl -s http://localhost:6000/workflows/1/runs | python3 -m json.tool
```

### Database Performance

```sql
-- Check query performance
EXPLAIN ANALYZE SELECT * FROM workflow_runs WHERE workflow_id = 1;

-- Check indexes
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'workflow_runs';
```

## CI/CD Integration

### GitHub Actions (Example)

```yaml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Start services
        run: docker compose up -d
      - name: Run migrations
        run: make db-upgrade
      - name: Backend tests
        run: make test-backend
      - name: E2E tests
        run: make test-e2e
```

## Test Maintenance

### Adding New Tests

1. **Backend tests**: Add to appropriate class in `test_engine_behavior.py` or `test_workflow.py`
2. **E2E tests**: Add new `.js` file in `tests/e2e/`, update `run-e2e.sh`
3. **Update regression net**: Pin behavior before refactors

### Test Naming Conventions

- Backend: `test_<feature>_<scenario>` (e.g., `test_api_call_ssrf_protection_blocks_loopback`)
- E2E: Descriptive script names (e.g., `smoke.js`, `designer-save.js`)

### Test Dependencies

- pytest >= 7.4
- pytest-asyncio >= 0.21
- SQLAlchemy >= 2.0
- httpx (for async HTTP)
- Puppeteer (for E2E)

## Quick Reference

| What | Command |
|------|---------|
| Run all backend tests | `make test-backend` |
| Run all E2E tests | `make test-e2e` |
| Run specific backend test | `docker compose exec backend python -m pytest path/to/test.py::test_name -v` |
| Run specific E2E script | `bash tests/e2e/run-e2e.sh <script_name>` |
| Reset test database | `docker compose down -v && docker compose up -d` |
| Check test coverage | `docker compose exec backend python -m pytest --cov=app` |
