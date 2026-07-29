#!/usr/bin/env python3
"""
Comprehensive import checker for the workflow system
"""
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

def check_imports():
    """Check all imports in API files"""
    
    api_dir = Path("backend/app/api")
    errors = []
    
    # Check each API file
    for py_file in api_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
            
        print(f"\nChecking {py_file.name}...")
        
        try:
            # Read file and check imports
            content = py_file.read_text()
            
            # Check for common import issues
            if "from app.services.auth_service import" in content and "get_current_user" in content:
                print(f"  ⚠️  WARNING: get_current_user should be imported from app.api.auth, not auth_service")
                
            if "from app.models.auth import" in content and "Workflow" in content:
                print(f"  ⚠️  WARNING: Workflow model is in app.models.schemas, not auth")
                
        except Exception as e:
            errors.append(f"{py_file.name}: {e}")
    
    if errors:
        print("\n❌ ERRORS FOUND:")
        for error in errors:
            print(f"  - {error}")
        return False
    else:
        print("\n✅ All imports look good!")
        return True

if __name__ == "__main__":
    check_imports()
