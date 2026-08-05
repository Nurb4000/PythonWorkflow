# Docker Deployment Guide

## Overview
This project includes Docker support for easy testing and production deployment. You can run the entire stack with a single command.

## Quick Start

### Start all services
```bash
# Build and start all services
docker compose up --build

# Or run in background
docker compose up -d --build

# View logs
docker compose logs -f

# Stop services
docker compose down
```

## Services

### Backend (`http://localhost:6000`)
- FastAPI application
- REST API endpoints
- Swagger docs at `http://localhost:6000/docs`

### Frontend (`http://localhost:9000`)
- React application served via Nginx
- Proxy API requests to backend

### Database
- PostgreSQL 15 (configured via `DATABASE_URL` environment variable)

### AI (Optional)
- llama.cpp server for AI features
- Requires GPU and model files
- Enable with `--profile ai`

## Environment Variables

### Backend
```bash
DATABASE_URL=postgresql://user:pass@postgres:5432/workflow_db
LLAMA_CPP_URL=http://llama_cpp:8081
SECRET_KEY=your-secret-key
DEBUG=True
CORS_ORIGINS=["http://localhost:9000"]
```

### Frontend (Nginx)
Configured in `nginx.conf` to proxy `/api/` to backend.

## Docker Compose Commands

### Common Operations
```bash
# Start all services
docker compose up -d

# Restart backend only
docker compose restart backend

# View logs
docker compose logs backend
docker compose logs frontend

# Execute commands in container
docker compose exec backend python -m pytest
docker compose exec backend bash

# Stop all services
docker compose down

# Stop and remove volumes
docker compose down -v
```



## Production Deployment

### 1. Update Environment Variables
Edit `docker-compose.yml` or create `.env` file:
```bash
DATABASE_URL=postgresql://user:pass@postgres:5432/workflow_db
SECRET_KEY=your-secure-random-key
DEBUG=False
LLAMA_CPP_URL=http://llama_cpp:8081
```

### 2. Build Production Images
```bash
docker compose build
```

### 3. Deploy
```bash
docker compose up -d
```

### 4. Verify
```bash
# Check backend health
curl http://localhost:8000/health

# Check frontend
curl http://localhost:9000

# Access Swagger docs
open http://localhost:8000/docs
```

## AI Features (Optional)

### Prerequisites
- GPU with CUDA support
- llama.cpp model file (e.g., `default.gguf`)
- Place model in `./models/` directory

### Enable AI Profile
```bash
docker compose up --profile ai -d
```

### Test AI Integration
```bash
curl -X POST http://localhost:8000/api/ai/generate-step \
  -H "Content-Type: application/json" \
  -d '{"description": "Create an API call to fetch user data"}'
```

## Troubleshooting

### Backend won't start
```bash
# Check logs
docker compose logs backend

# Verify database connection
docker compose exec backend python -c "from sqlalchemy import create_engine; print('OK')"
```

### Frontend shows 404
```bash
# Rebuild frontend
docker compose build frontend

# Check nginx config
docker compose exec frontend cat /etc/nginx/conf.d/default.conf
```

### Database migration fails
```bash
# Check PostgreSQL is ready
docker compose exec postgres pg_isready

# Verify credentials
docker compose exec backend env | grep DATABASE_URL
```

## Security Notes

1. **Change default passwords** in production
2. **Use HTTPS** with reverse proxy (nginx, traefik)
3. **Enable authentication** for all API endpoints
4. **Regularly update** base images
5. **Scan images** for vulnerabilities

## Monitoring

### Health Checks
Services include health checks that can be monitored:
```bash
docker inspect --format='{{.State.Health.Status}}' <container_id>
```

### Logs
Centralized logging with:
```bash
docker compose logs -f --tail=100
```

## Scaling

For production, consider:
- Multiple backend instances behind load balancer
- PostgreSQL read replicas
- Redis for session management
- Celery for async task processing

## Development Tips

### Hot Reload
Backend uses `--reload` flag for development. Frontend rebuilds on changes.

### Database Configuration
Configure the database via the `DATABASE_URL` environment variable:
```bash
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/workflow_db
```

## Cleanup

### Remove all containers and volumes
```bash
docker compose down -v
```

### Remove images
```bash
docker compose down --rmi all
```

### Remove build cache
```bash
docker builder prune -f
```
