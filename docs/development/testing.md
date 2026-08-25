# Testing Guide

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

The test suite ensures code quality and prevents regressions. Run tests before committing changes.

### Test Types

| Type | Location | Purpose |
|------|----------|---------|
| **Unit Tests** | `backend/tests/` | Individual functions/classes |
| **Integration Tests** | `backend/tests/` | API endpoints, service interactions |
| **E2E Tests** | `tests/e2e/` | Full user flows in browser |

---

## Running Tests

### Backend Tests

```bash
# All tests
make test-backend

# Specific test file
docker compose exec backend python -m pytest tests/test_workflow.py

# Specific test class
docker compose exec backend python -m pytest tests/test_workflow.py::TestWorkflowEngine

# Specific test method
docker compose exec backend python -m pytest tests/test_workflow.py::TestWorkflowEngine::test_create_workflow

# With verbose output
docker compose exec backend python -m pytest -v

# Skip slow tests
docker compose exec backend python -m pytest -m "not slow"
```

### E2E Tests

```bash
# All E2E tests
bash tests/e2e/run-e2e.sh

# Specific test
bash tests/e2e/run-e2e.sh smoke.js

# With custom env
E2E_BASE=http://localhost:9000 E2E_ADMIN_PASS=admin123 bash tests/e2e/run-e2e.sh
```

---

## Test Structure

### Backend Test Layout

```
backend/tests/
├── conftest.py              # Shared fixtures (db_engine, etc.)
├── test_workflow.py         # Workflow engine tests
├── test_forms.py            # Form service tests
├── test_cmdb.py             # CMDB tests
├── test_tasks.py            # Task management tests
└── ...
```

### Test Patterns

**Fixture-based:**
```python
@pytest.mark.asyncio
async def test_create_workflow(db_engine):
    async with db_engine.begin() as conn:
        # Setup
        pass
```

**API client:**
```python
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_list_workflows():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/workflows/")
        assert response.status_code == 200
```

---

## Writing Tests

### Unit Test Example

```python
# tests/test_calculator.py
import pytest
from app.services.calculator import calculate_total

def test_calculate_total():
    items = [{"price": 10, "qty": 2}, {"price": 5, "qty": 3}]
    assert calculate_total(items) == 35

def test_calculate_total_empty():
    assert calculate_total([]) == 0

@pytest.mark.parametrize("items,expected", [
    ([{"price": 10}], 10),
    ([{"price": 10}, {"price": 20}], 30),
])
def test_calculate_total_param(items, expected):
    assert calculate_total(items) == expected
```

### Integration Test Example

```python
# tests/test_workflow_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_create_workflow():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        # Login
        login_resp = await client.post("/auth/login", data={
            "username": "admin",
            "password": "admin123"
        })
        token = login_resp.json()["access_token"]
        
        # Create workflow
        response = await client.post(
            "/workflows/",
            json={"name": "Test WF", "steps": []},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 201
        assert response.json()["name"] == "Test WF"
```

---

## Test Database

Tests use a dedicated PostgreSQL database:

- **Database:** `workflow_db_test`
- **Schema:** Fresh schema per test (via `db_engine` fixture)
- **Isolation:** Tests don't interfere with each other

**Fixture:**
```python
@pytest.fixture
async def db_engine():
    """Fresh-schema PostgreSQL engine."""
    # Setup in conftest.py
    yield engine
    # Teardown
```

---

## E2E Test Structure

```
tests/e2e/
├── lib.js                 # Shared test utilities
├── smoke.js               # Basic smoke tests
├── designer-save.js       # Workflow designer save flow
├── entry-form-task.js     # Entry form + task flow
└── run-e2e.sh             # Test runner script
```

### Writing E2E Tests

```javascript
// tests/e2e/my-test.js
const { BASE, connect, newPage, login, sleep } = require('./lib');

(async () => {
  const browser = await connect();
  const { page } = await newPage(browser);
  await login(page, 'admin', 'admin123');
  
  await page.goto(BASE + '/workflows');
  await sleep(1000);
  
  const count = await page.$$('tr').length;
  console.log(`Found ${count} workflows`);
  
  browser.disconnect();
})();
```

---

## Test Coverage

### Current Coverage

| Module | Coverage | Notes |
|--------|----------|-------|
| Workflow Engine | ~85% | Core execution paths tested |
| Form Service | ~80% | Submission validation covered |
| CMDB Service | ~75% | CRUD operations tested |
| Task Service | ~90% | Lifecycle fully covered |
| API Endpoints | ~70% | Happy paths tested |

### Improving Coverage

Focus on:
- Error handling paths
- Edge cases (empty data, large datasets)
- Integration scenarios (multi-step workflows)

---

## Continuous Integration

### GitHub Actions (Planned)

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
    steps:
      - uses: actions/checkout@v4
      - name: Run backend tests
        run: make test-backend
      - name: Run E2E tests
        run: bash tests/e2e/run-e2e.sh
```

---

## Debugging Tests

### Slow Tests

Identify slow tests:
```bash
docker compose exec backend python -m pytest --durations=10
```

**Solutions:**
- Mock external services
- Reduce test data
- Use async where possible

### Flaky Tests

If tests fail intermittently:
1. Check for race conditions
2. Verify test isolation
3. Add retries for external calls
4. Check database state cleanup

### Debug Mode

Run tests with debugger:
```bash
docker compose exec backend python -m pdb -c "continue" -m pytest tests/test_workflow.py::test_create_workflow
```

---

## Best Practices

1. **Test one thing per test:** Keep tests focused
2. **Use fixtures:** Share setup/teardown logic
3. **Name clearly:** `test_create_workflow_with_steps` not `test1`
4. **Assert explicitly:** Use `assert` not just print statements
5. **Clean up:** Ensure tests don't leave side effects
6. **Run before commit:** Always run relevant tests locally
7. **Cover errors:** Test failure paths, not just success

---

## Related Documentation

- [Architecture Overview](./architecture.md)
- [Adding Features](./adding-features.md)
- [Deployment Guide](../deployment/production.md)

---

*Next: [Deployment Guide](../deployment/production.md)*
