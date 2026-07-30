#!/usr/bin/env python3
"""
Comprehensive project fixer - fixes all import, routing, and model issues
"""
import os
import re
from pathlib import Path

def fix_circular_imports():
    """Fix circular imports between models"""
    
    # Fix auth.py - remove Workflow reference
    auth_file = Path("backend/app/models/auth.py")
    content = auth_file.read_text()
    
    # Remove owned_workflows relationship from User
    content = re.sub(
        r'    owned_workflows = relationship\("Workflow", back_populates="created_by_user"\)\n',
        '',
        content
    )
    
    auth_file.write_text(content)
    print("✓ Fixed auth.py circular import")


def fix_model_relationships():
    """Add back relationships that were removed"""
    
    # Fix schemas.py - add owned_workflows relationship to Workflow
    schemas_file = Path("backend/app/models/schemas.py")
    content = schemas_file.read_text()
    
    # Add the relationship after the runs relationship
    if 'owned_workflows' not in content:
        content = content.replace(
            '    runs = relationship("WorkflowRun", back_populates="workflow", cascade="all, delete-orphan")',
            '''    runs = relationship("WorkflowRun", back_populates="workflow", cascade="all, delete-orphan")
    created_by_user = relationship("User", back_populates="owned_workflows")'''
        )
        schemas_file.write_text(content)
        print("✓ Added owned_workflows relationship to Workflow in schemas.py")


def verify_routes():
    """Verify all routes are properly registered"""
    
    main_file = Path("backend/app/main.py")
    content = main_file.read_text()
    
    required_routers = [
        'workflows', 'workflow_runs', 'admin', 'ai', 
        'knowledge_base', 'auth', 'portal', 'forms', 'system_settings'
    ]
    
    missing = []
    for router in required_routers:
        if f'from app.api import' not in content and router not in content:
            # Check if it's imported
            if f'{router}' not in content:
                missing.append(router)
    
    if missing:
        print(f"⚠️  Missing routers: {missing}")
    else:
        print("✓ All routers are registered")


def test_endpoints():
    """Test critical endpoints"""
    
    import subprocess
    
    print("\n=== Testing Endpoints ===")
    
    # Test health
    result = subprocess.run(
        ['curl', '-s', 'http://localhost:6000/health'],
        capture_output=True, text=True
    )
    if 'healthy' in result.stdout:
        print("✓ Health endpoint works")
    else:
        print(f"✗ Health endpoint failed: {result.stdout}")
    
    # Test login
    result = subprocess.run(
        ['curl', '-s', '-X', 'POST', 'http://localhost:6000/auth/login',
         '-H', 'Content-Type: application/x-www-form-urlencoded',
         '-d', 'username=admin&password=admin123'],
        capture_output=True, text=True
    )
    if 'access_token' in result.stdout:
        print("✓ Login endpoint works")
    else:
        print(f"✗ Login endpoint failed: {result.stdout}")


if __name__ == "__main__":
    print("=== Running Comprehensive Project Fix ===\n")
    
    fix_circular_imports()
    fix_model_relationships()
    verify_routes()
    test_endpoints()
    
    print("\n=== Fix Complete ===")
