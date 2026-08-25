# Production Deployment

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

Deploy Instant Workflow to production with security, performance, and reliability in mind.

### Prerequisites

- Docker + Docker Compose v2
- PostgreSQL 15+
- Domain name (for SSL)
- SMTP server (for email)
- Optional: Redis (for caching), S3 (for file storage)

---

## Quick Start

```bash
# Clone repository
git clone <repo-url>
cd PythonWorkflow

# Copy production override
cp docker-compose.prod.yml.example docker-compose.prod.yml

# Configure environment
cp .env.example .env
# Edit .env with production values

# Build and start
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Run migrations
docker compose exec backend alembic upgrade head

# Create admin user
docker compose exec backend python -m app.scripts.create_admin
```

---

## Configuration

### Environment Variables

Edit `.env` with production values:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@postgres:5432/workflow_db

# Security
SECRET_KEY=<generate-random-key>

# SMTP (for notifications)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=noreply@example.com
SMTP_PASSWORD=app-password
SMTP_FROM=noreply@example.com

# AI (optional)
LLAMA_CPP_URL=http://llama_cpp:8080
# OR
OPENAI_API_KEY=sk-...
```

**Generate SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Docker Compose Production Override

`docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  postgres:
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
  
  backend:
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - SECRET_KEY=${SECRET_KEY}
      - DEBUG=False
    ports:
      - "6000:8000"
    depends_on:
      postgres:
        condition: service_healthy
  
  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports:
      - "9000:80"
    depends_on:
      - backend

volumes:
  postgres_data:
```

---

## Security Hardening

### HTTPS

Use a reverse proxy (nginx, Caddy) with Let's Encrypt:

```nginx
server {
    listen 443 ssl;
    server_name workflow.example.com;
    
    ssl_certificate /etc/letsencrypt/live/workflow.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/workflow.example.com/privkey.pem;
    
    location / {
        proxy_pass http://frontend:80;
    }
    
    location /api/ {
        proxy_pass http://backend:8000;
    }
}
```

### Firewall

Allow only necessary ports:

```bash
# Allow SSH
ufw allow 22/tcp

# Allow HTTPS
ufw allow 443/tcp

# Block everything else
ufw default deny incoming
ufw enable
```

### Database

- Use strong passwords
- Restrict access to backend container only
- Enable SSL for connections
- Regular backups (see [Backups](./backups.md))

### Application

- Set `DEBUG=False` in production
- Use HTTPS-only cookies
- Configure CORS origins
- Rate limit API endpoints

---

## Performance Optimization

### Database

```sql
-- Add indexes for common queries
CREATE INDEX IF NOT EXISTS idx_workflows_name ON workflows (name);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status);
CREATE INDEX IF NOT EXISTS idx_ci_items_type_id ON configuration_items (type_id);
```

### Backend

- Enable Gunicorn workers: `gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app`
- Use connection pooling: `pool_size=20, max_overflow=10`
- Cache frequently accessed data (Redis)

### Frontend

- Build for production: `npm run build`
- Enable gzip compression
- Use CDN for static assets

---

## Monitoring

### Health Checks

Add to docker-compose.yml:

```yaml
services:
  backend:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Logging

Configure log levels:

```python
# In config.py
log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

View logs:

```bash
docker compose logs -f backend
```

### Metrics

Consider adding Prometheus + Grafana for:
- Request latency
- Error rates
- Database query performance
- CPU/memory usage

---

## Backup Strategy

### Database

Daily pg_dump (see [Backups](./backups.md)):

```bash
0 2 * * * docker exec pythonworkflow-postgres-1 pg_dumpall -U workflow_user > /backups/workflow_db_$(date +\%Y\%m\%d).sql
```

### Configuration

Backup `.env` and `docker-compose.prod.yml` after changes.

### Files

Backup `backend/backend_data/` and `uploads/` directories.

---

## Updating

### Pull Latest Changes

```bash
git pull origin master
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec backend alembic upgrade head
```

### Rollback

If update fails:

```bash
# Stop services
docker compose down

# Restore database from backup
pg_restore -U workflow_user -d workflow_db backup.sql

# Restart with previous image tags
docker compose up -d
```

---

## Troubleshooting

### Backend won't start

**Check logs:**
```bash
docker compose logs backend
```

**Common issues:**
- Database connection failed → Check `DATABASE_URL`
- Migration errors → Run `alembic upgrade head`
- Port conflicts → Change port mapping

### Frontend 404

**Check:**
- Backend is running
- Proxy configuration is correct
- Frontend build completed successfully

### Slow performance

**Investigate:**
- Database query performance (slow queries log)
- API response times (add logging)
- Resource usage (docker stats)

---

## Related Documentation

- [Backup Procedures](./backups.md)
- [Monitoring and Logs](../administration/monitoring.md)
- [Security Guide](../security/overview.md)

---

*Next: [Contributor Guide](../development/contributor-guide.md)*
