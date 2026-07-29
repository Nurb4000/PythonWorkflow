# Database Configuration Switcher
# Usage: ./switch-db.ps1 [sqlite|postgresql]

param(
    [string]$DBType = "sqlite"
)

Write-Host "Switching database to: $DBType" -ForegroundColor Cyan

switch ($DBType.ToLower()) {
    "sqlite" {
        Write-Host "[OK] Using SQLite (development)" -ForegroundColor Green
        $env:DATABASE_URL = "sqlite:///./workflow.db"
    }
    "postgresql", "postgres", "pg" {
        Write-Host "[OK] Using PostgreSQL (production)" -ForegroundColor Green
        $env:DATABASE_URL = "postgresql://workflow_user:workflow_password@postgres:5432/workflow_db"
    }
    default {
        Write-Host "Error: Unknown database type '$DBType'" -ForegroundColor Red
        Write-Host "Usage: ./switch-db.ps1 [sqlite|postgresql]" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host ""
Write-Host "Database: $DBType" -ForegroundColor Cyan
Write-Host "URL: $env:DATABASE_URL" -ForegroundColor Cyan
Write-Host ""
Write-Host "Now run: docker-compose up --build" -ForegroundColor Yellow
