"""
AI Standards Enforcer — Ensures AI-generated content follows platform standards.
"""
import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class AIStandardsEnforcer:
    """Validate AI-generated content against platform standards."""
    
    # Naming conventions
    VALID_NAME_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]{2,79}$')
    MAX_NAME_LENGTH = 80
    FORBIDDEN_PATTERNS = [r'^\s+', r'\s+$', r'[^\x20-\x7E]']  # Leading/trailing spaces, non-ASCII
    
    @staticmethod
    def validate_name(name: str) -> Dict[str, Any]:
        """Validate a name against naming standards."""
        issues = []
        
        if not name or len(name.strip()) == 0:
            return {"valid": False, "issues": ["Name cannot be empty"]}
        
        if len(name) > AIStandardsEnforcer.MAX_NAME_LENGTH:
            issues.append(f"Name must be {AIStandardsEnforcer.MAX_NAME_LENGTH} characters or fewer")
        
        if not AIStandardsEnforcer.VALID_NAME_PATTERN.match(name):
            issues.append("Name must start with a letter and contain only alphanumeric characters and underscores")
        
        for pattern in AIStandardsEnforcer.FORBIDDEN_PATTERNS:
            if re.search(pattern, name):
                issues.append(f"Name contains forbidden pattern: {pattern}")
        
        return {"valid": len(issues) == 0, "issues": issues}
    
    @staticmethod
    def validate_field_key(key: str) -> Dict[str, Any]:
        """Validate a field key against standards."""
        issues = []
        
        if not key or len(key.strip()) == 0:
            return {"valid": False, "issues": ["Field key cannot be empty"]}
        
        if not re.match(r'^[a-z][a-z0-9_]*$', key):
            issues.append("Field key must be lowercase, start with letter, contain only alphanumeric and underscores")
        
        if len(key) > 50:
            issues.append("Field key must be 50 characters or fewer")
        
        return {"valid": len(issues) == 0, "issues": issues}
    
    @staticmethod
    def validate_step_config(config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a step configuration against standards."""
        issues = []
        
        # Check for hardcoded values
        config_str = str(config)
        if re.search(r'password\s*=\s*["\'][^"\']+["\']', config_str, re.IGNORECASE):
            issues.append("Step configuration contains hardcoded password")
        
        if re.search(r'api[_-]?key\s*=\s*["\'][^"\']+["\']', config_str, re.IGNORECASE):
            issues.append("Step configuration contains hardcoded API key")
        
        # Check for suspicious URLs
        if re.search(r'https?://(127\.0\.0\.1|localhost|0\.0\.0\.0)', config_str):
            issues.append("Step configuration contains localhost URL (use environment variable)")
        
        return {"valid": len(issues) == 0, "issues": issues}
    
    @staticmethod
    def sanitize_output(output: str) -> str:
        """Sanitize AI output to remove sensitive information."""
        # Remove potential secrets
        output = re.sub(r'(password|secret|key|token)\s*[:=]\s*["\'][^"\']+["\']', r'\1: ***REDACTED***', output, flags=re.IGNORECASE)
        
        # Remove IP addresses (potential internal URLs)
        output = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '***IP_REDACTED***', output)
        
        return output


ai_standards_enforcer = AIStandardsEnforcer()
