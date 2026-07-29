@echo off
REM Database configuration switcher
REM Usage: switch-db.bat [sqlite|postgresql]

set DB_TYPE=%1

if "%DB_TYPE%"=="" (
    set DB_TYPE=sqlite
)

echo Switching database to: %DB_TYPE%

if "%DB_TYPE%"=="sqlite" (
    echo [OK] Using SQLite (development)
    set DATABASE_URL=sqlite:////workflow.db
) else if "%DB_TYPE%"=="postgresql" (
    echo [OK] Using PostgreSQL (production)
    set DATABASE_URL=postgresql://workflow_user:workflow_password@postgres:5432/workflow_db
) else if "%DB_TYPE%"=="postgres" (
    echo [OK] Using PostgreSQL (production)
    set DATABASE_URL=postgresql://workflow_user:workflow_password@postgres:5432/workflow_db
) else if "%DB_TYPE%"=="pg" (
    echo [OK] Using PostgreSQL (production)
    set DATABASE_URL=postgresql://workflow_user:workflow_password@postgres:5432/workflow_db
) else (
    echo Error: Unknown database type '%DB_TYPE%'
    echo Usage: switch-db.bat [sqlite|postgresql]
    exit /b 1
)

echo.
echo Database: %DB_TYPE%
echo URL: %DATABASE_URL%
echo.
echo Now run: docker-compose up --build
