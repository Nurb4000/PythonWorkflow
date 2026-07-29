#!/bin/bash

# Database configuration switcher
# Usage: ./switch-db.sh [sqlite|postgresql]

set -e

DB_TYPE=${1:-sqlite}

echo "Switching database to: $DB_TYPE"

case $DB_TYPE in
    sqlite)
        echo "✓ Using SQLite (development)"
        export DATABASE_URL="sqlite:///./workflow.db"
        ;;
    postgresql|postgres|pg)
        echo "✓ Using PostgreSQL (production)"
        export DATABASE_URL="postgresql://workflow_user:workflow_password@postgres:5432/workflow_db"
        ;;
    *)
        echo "Error: Unknown database type '$DB_TYPE'"
        echo "Usage: $0 [sqlite|postgresql]"
        exit 1
        ;;
esac

# Update docker-compose environment
if [ -f docker-compose.yml ]; then
    echo "Updating docker-compose.yml..."
    
    # Create backup
    cp docker-compose.yml docker-compose.yml.bak
    
    # Update DATABASE_URL
    sed -i.bak "s|DATABASE_URL=.*|DATABASE_URL=$DATABASE_URL|" docker-compose.yml 2>/dev/null || \
    sed -i "" "s|DATABASE_URL=.*|DATABASE_URL=$DATABASE_URL|" docker-compose.yml 2>/dev/null || \
    echo "Manual update required for docker-compose.yml"
    
    echo "✓ Database configuration updated"
    echo ""
    echo "Now run: docker-compose up --build"
else
    echo "Warning: docker-compose.yml not found"
    echo "Set DATABASE_URL manually in your environment"
fi

echo ""
echo "Database: $DB_TYPE"
echo "URL: $DATABASE_URL"
