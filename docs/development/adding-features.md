# Adding Features

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

This guide explains how to extend the system with new features, following established patterns.

### Prerequisites

- Familiarity with Python (FastAPI, SQLAlchemy)
- React/TypeScript knowledge
- PostgreSQL basics
- Docker Compose

---

## Feature Types

| Type | Description | Example |
|------|-------------|---------|
| **New API Endpoint** | Add REST endpoint | `/admin/custom-action` |
| **New Model** | Extend database schema | `CustomSetting` table |
| **New Executor** | Add step type | `custom_code` step |
| **New UI Page** | Frontend component | `/custom-dashboard` |
| **New Service** | Business logic module | `notification_service.py` |

---

## Step-by-Step: Adding a New API Endpoint

### 1. Define the Route

Create or edit `backend/app/api/your_module.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.models.auth import User
from app.api.auth import get_current_admin

router = APIRouter(prefix="/custom", tags=["custom"])

@router.get("/")
async def list_custom_items(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """List custom items (admin only)."""
    # Your logic here
    return {"items": []}
```

### 2. Register the Router

Edit `backend/app/main.py`:

```python
from app.api import your_module

# Add to imports
app.include_router(your_module.router, tags=["custom"])
```

### 3. Add Frontend API Client

Edit `frontend/src/services/api.ts`:

```typescript
export const customApi = {
  list: () => api.get('/custom'),
  create: (data: any) => api.post('/custom', data),
  // ...
}
```

### 4. Create Frontend Component

Create `frontend/src/pages/CustomPage.tsx`:

```tsx
import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { customApi } from '../services/api'

export const CustomPage: React.FC = () => {
  const { data, isLoading } = useQuery({
    queryKey: ['custom-items'],
    queryFn: () => customApi.list(),
  })

  if (isLoading) return <div>Loading...</div>
  
  return (
    <div>
      <h2>Custom Items</h2>
      {/* Render data */}
    </div>
  )
}
```

### 5. Add Route to App

Edit `frontend/src/App.tsx`:

```tsx
import { CustomPage } from './pages/CustomPage'

// In routes section:
<Route path="/custom" element={<CustomPage />} />
```

### 6. Run Migrations (if needed)

```bash
docker compose exec backend alembic revision --autogenerate -m "add_custom_table"
docker compose exec backend alembic upgrade head
```

---

## Step-by-Step: Adding a New Step Executor

### 1. Create Executor Class

Edit `backend/app/services/step_executors.py`:

```python
class CustomExecutor(BaseExecutor):
    """Custom step executor."""
    
    async def execute(self, input_data, step_definition, db=None):
        """Execute the custom step."""
        # Your logic here
        return {"result": "success"}
```

### 2. Register Executor

Edit `backend/app/services/workflow_engine.py`:

```python
from app.services.step_executors import CustomExecutor

# In _register_default_executors:
self.step_executors["custom"] = CustomExecutor()
```

### 3. Add to Frontend Palette

Edit `frontend/src/pages/WorkflowDesigner.tsx`:

```typescript
const STEP_TYPES = [
  // ... existing types
  { value: 'custom', label: 'Custom Step', icon: '🔧' }
]
```

---

## Step-by-Step: Adding a New Model

### 1. Define Model

Create `backend/app/models/your_model.py`:

```python
from sqlalchemy import Column, Integer, String, DateTime
from app.core.database import Base

class CustomSetting(Base):
    __tablename__ = "custom_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(String(500))
    created_at = Column(DateTime, server_default=func.now())
```

### 2. Register Model

Edit `backend/app/models/__init__.py`:

```python
from app.models.your_model import CustomSetting
```

### 3. Create Migration

```bash
docker compose exec backend alembic revision --autogenerate -m "add_custom_settings"
docker compose exec backend alembic upgrade head
```

---

## Testing Your Feature

### Backend Tests

Create `backend/tests/test_your_feature.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_list_custom_items():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/custom/")
        assert response.status_code == 200
```

### Frontend Tests

Create `frontend/src/pages/__tests__/CustomPage.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { CustomPage } from '../CustomPage'

test('renders custom items', async () => {
  render(<CustomPage />)
  expect(screen.getByText(/Custom Items/i)).toBeInTheDocument()
})
```

---

## Documentation

Update relevant docs:

- `docs/features/your-feature.md` — Feature guide
- `docs/api/your-endpoint.md` — API reference
- `CHANGELOG.md` — Release notes

---

## Code Review Checklist

Before submitting PR:

- [ ] Follows existing patterns
- [ ] Includes tests
- [ ] Updates documentation
- [ ] No hardcoded secrets
- [ ] Proper error handling
- [ ] Input validation
- [ ] Security considerations addressed
- [ ] Performance impact assessed

---

## Related Documentation

- [Architecture Overview](./architecture.md)
- [Testing Guide](./testing.md)
- [Coding Standards](./coding-standards.md)

---

*Next: [Testing Guide](./testing.md)*
