# Contributor Guide

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

Guide for developers contributing to Instant Workflow. Follow these steps to set up your environment, make changes, and submit pull requests.

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker + Docker Compose
- PostgreSQL 15+ (or use Docker)
- Git

---

## Development Setup

### 1. Clone Repository

```bash
git clone <repo-url>
cd PythonWorkflow
```

### 2. Backend Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r backend/requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your settings

# Run migrations
cd backend
alembic upgrade head
cd ..
```

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
# Frontend runs at http://localhost:9000
```

### 4. Start Services

```bash
# Start PostgreSQL (if not using Docker)
sudo systemctl start postgresql

# Start backend
cd backend
uvicorn app.main:app --reload --port 8000
# API runs at http://localhost:8000

# Or use Docker
docker compose up -d postgres backend
```

### 5. Create Admin User

```bash
docker compose exec backend python -m app.scripts.create_admin
# Or manually via API
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123", "email": "admin@example.com", "role": "admin"}'
```

---

## Making Changes

### 1. Create Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

### 2. Make Changes

Follow the [Adding Features](./adding-features.md) guide for implementation patterns.

### 3. Test Your Changes

```bash
# Run backend tests
cd backend
python -m pytest tests/ -v

# Run frontend type check
cd frontend
npx tsc --noEmit

# Run E2E tests (if applicable)
bash tests/e2e/run-e2e.sh
```

### 4. Commit Changes

```bash
git add .
git commit -m "feat: add your feature description"
# or
git commit -m "fix: resolve bug description"
```

**Commit message format:**
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation only
- `refactor:` Code refactoring
- `test:` Adding tests
- `chore:` Maintenance tasks

---

## Code Standards

### Python

- Follow PEP 8
- Use type hints
- Maximum line length: 100 characters
- Docstrings for public functions/classes

```python
def calculate_total(items: List[Dict]) -> float:
    """Calculate total price for items.
    
    Args:
        items: List of item dictionaries with 'price' and 'qty' keys
        
    Returns:
        Total price as float
    """
    return sum(item['price'] * item['qty'] for item in items)
```

### TypeScript/React

- Use functional components
- Add prop types or interfaces
- Maximum line length: 100 characters
- Prefer const over let

```typescript
interface UserProps {
  name: string
  email: string
  onClick?: () => void
}

export const UserCard: React.FC<UserProps> = ({ name, email, onClick }) => {
  return (
    <div onClick={onClick}>
      <h3>{name}</h3>
      <p>{email}</p>
    </div>
  )
}
```

### Git

- Write clear commit messages
- Squash small commits before pushing
- Keep branches up to date with main

---

## Pull Request Process

### 1. Push Your Branch

```bash
git push origin feature/your-feature-name
```

### 2. Create Pull Request

- Go to repository → Pull Requests → New Pull Request
- Select your branch as source, `master` as target
- Fill in PR template:
  - **Description:** What does this PR do?
  - **Related Issues:** Links to issues this addresses
  - **Testing:** How did you test this?
  - **Screenshots:** If UI changes

### 3. Address Review Feedback

- Respond to comments
- Make requested changes
- Update tests if needed
- Re-request review

### 4. Merge

Once approved, maintainers will merge your PR.

---

## Testing Requirements

All PRs must include:

- [ ] Unit tests for new logic
- [ ] Integration tests for API changes
- [ ] E2E tests for user-facing features (if applicable)
- [ ] Updated documentation (if public API changes)
- [ ] No breaking changes (or documented migration path)

---

## Issue Reporting

### Before Creating an Issue

1. Search existing issues
2. Check documentation
3. Try reproducing in latest version

### Issue Template

```markdown
**Description**
Brief description of the issue.

**Steps to Reproduce**
1. Go to '...'
2. Click on '...'
3. See error

**Expected Behavior**
What should happen.

**Actual Behavior**
What actually happens.

**Environment**
- OS: [e.g., Ubuntu 22.04]
- Browser: [e.g., Chrome 120]
- Version: [e.g., 1.0.0]

**Additional Context**
Screenshots, logs, etc.
```

---

## Documentation Standards

### Writing Docs

- Use Markdown
- Include code examples
- Add screenshots for UI changes
- Keep it current (update when features change)

### Doc Structure

Follow existing patterns in `docs/`:

```
docs/
├── features/          # Feature documentation
├── administration/    # Admin guides
├── development/       # Developer resources
└── deployment/        # Deployment guides
```

---

## Getting Help

- **Questions:** Open a discussion or issue
- **Bug reports:** Use issue template
- **Feature requests:** Describe use case and expected behavior
- **Security issues:** Email maintainers privately

---

## Recognition

Contributors are recognized in:
- `CHANGELOG.md` under "Contributors"
- Repository README (if significant contributions)
- Release notes

---

## Related Documentation

- [Architecture Overview](./architecture.md)
- [Adding Features](./adding-features.md)
- [Testing Guide](./testing.md)
- [Coding Standards](./coding-standards.md)

---

*Thank you for contributing to Instant Workflow!*
