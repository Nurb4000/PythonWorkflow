# Backup Procedures

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

Back up the database and configuration to prevent data loss. The system uses PostgreSQL with named volumes for persistence.

### What to Back Up

| Component | Location | Frequency |
|-----------|----------|-----------|
| **Database** | PostgreSQL volume | Daily |
| **Configuration** | `.env` file | After changes |
| **Custom data** | `backend/backend_data/` | Weekly |
| **Knowledge base** | `knowledge-base/` | After edits |

---

## Database Backup

### Automated Backup (Recommended)

Set up a cron job to run daily backups.

**Cron expression:** `0 2 * * *` (daily at 2 AM)

**Script:**
```bash
#!/bin/bash
# backup.sh — Run via cron

BACKUP_DIR="/backups/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
CONTAINER="pythonworkflow-postgres-1"

mkdir -p $BACKUP_DIR

# Stop container to ensure consistent backup
docker stop $CONTAINER

# Create backup
docker run --rm \
  -v pythonworkflow_postgres_data:/var/lib/postgresql/data \
  -v $BACKUP_DIR:/backups \
  postgres:15-alpine \
  sh -c "pg_dumpall -U workflow_user > /backups/workflow_db_$DATE.sql"

# Restart container
docker start $CONTAINER

# Remove backups older than 30 days
find $BACKUP_DIR -name "*.sql" -mtime +30 -delete

echo "Backup completed: workflow_db_$DATE.sql"
```

**Schedule:**
```bash
# Edit crontab
crontab -e

# Add line (run daily at 2 AM)
0 2 * * * /path/to/backup.sh >> /var/log/backup.log 2>&1
```

### Manual Backup

```bash
# Stop container
docker stop pythonworkflow-postgres-1

# Create backup
docker run --rm \
  -v pythonworkflow_postgres_data:/var/lib/postgresql/data \
  -v $(pwd):/backups \
  postgres:15-alpine \
  sh -c "pg_dumpall -U workflow_user > /backups/workflow_db_$(date +%Y%m%d).sql"

# Start container
docker start pythonworkflow-postgres-1
```

### Restore Database

```bash
# Stop containers
docker compose down

# Remove existing volume (BACKUP FIRST!)
docker volume rm pythonworkflow_postgres_data

# Create fresh volume
docker volume create pythonworkflow_postgres_data

# Start containers (creates fresh database)
docker compose up -d postgres

# Stop again to restore
docker stop pythonworkflow-postgres-1

# Restore from backup
docker run --rm \
  -v pythonworkflow_postgres_data:/var/lib/postgresql/data \
  -v /path/to/backup:/backups \
  postgres:15-alpine \
  sh -c "cat /backups/workflow_db_YYYYMMDD.sql | psql -U workflow_user -d workflow_db"

# Start all containers
docker compose up -d
```

---

## Configuration Backup

### Environment File

Back up `.env` after any changes:

```bash
cp .env .env.backup.$(date +%Y%m%d)
```

**Contents to back up:**
- `DATABASE_URL`
- `SECRET_KEY`
- `LLAMA_CPP_URL` (if using local AI)
- `OPENAI_API_KEY` (if using OpenAI)
- `SMTP_*` settings
- `LDAP_*` settings

### Docker Compose Override

If using `docker-compose.prod.yml`, back up that file too.

---

## Custom Data Backup

### Backend Data Directory

```bash
# Backup custom data
tar -czf backend_data_backup_$(date +%Y%m%d).tar.gz \
  backend/backend_data/

# Restore
tar -xzf backend_data_backup_YYYYMMDD.tar.gz -C /
```

**Contents:**
- Email attachments
- Uploaded files
- Custom configurations

### Knowledge Base

```bash
# Backup knowledge base
tar -czf knowledge_base_backup_$(date +%Y%m%d).tar.gz \
  knowledge-base/

# Restore
tar -xzf knowledge_base_backup_YYYYMMDD.tar.gz -C /
```

---

## Backup Verification

### Test Restores

Quarterly, test restoring from backup in a staging environment:

1. Create staging database
2. Restore backup
3. Verify data integrity
4. Run tests
5. Confirm application works

### Backup Integrity

Verify backups are valid:

```bash
# Check SQL file is not corrupted
head -5 workflow_db_*.sql
# Should show PostgreSQL dump header

# Check file size
ls -lh workflow_db_*.sql
# Should be reasonable size (not 0 bytes)

# Test restore to temp database
createdb test_restore
psql -d test_restore -f workflow_db_backup.sql
```

---

## Backup Storage

### Local Storage

Store backups on the same server (fast recovery).

**Risk:** Server failure loses both primary and backup.

### Remote Storage

Upload backups to cloud storage (S3, Azure Blob, etc.).

**Example with AWS S3:**
```bash
aws s3 cp workflow_db_$(date +%Y%m%d).sql s3://your-bucket/backups/
```

**Risk:** Slower recovery, requires internet.

### Hybrid Approach

Keep recent backups locally, archive older ones remotely.

**Retention policy:**
- Daily backups: Keep 7 days locally
- Weekly backups: Keep 4 weeks remotely
- Monthly backups: Keep 12 months remotely

---

## Disaster Recovery

### RTO (Recovery Time Objective)

Target: Restore within 4 hours.

**Steps:**
1. Identify failure scope (database? server? all?)
2. Stop affected services
3. Restore from latest backup
4. Verify data integrity
5. Restart services
6. Test application

### RPO (Recovery Point Objective)

Target: Lose no more than 24 hours of data.

**Achieved by:** Daily backups at consistent time.

---

## Monitoring Backups

### Backup Success/Failure

Monitor backup script output:

```bash
tail -f /var/log/backup.log
```

Set up alerts for:
- Backup script failures
- Unusually small backup files
- Missing daily backups

### Disk Space

Monitor backup storage:

```bash
df -h /backups
```

Alert when usage exceeds 80%.

---

## Related Documentation

- [Docker Deployment](../deployment/docker.md)
- [Production Setup](../deployment/production.md)
- [Monitoring and Logs](./monitoring.md)

---

*Next: [Monitoring and Logs](./monitoring.md)*
