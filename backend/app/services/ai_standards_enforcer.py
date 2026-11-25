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
    
    # Regexes identifying a field name that holds a secret.
    _SECRET_KEY_RE = re.compile(r'(?i)(password|passwd|secret|api[_-]?key|access[_-]?key|secret[_-]?key|token|passphrase|private[_-]?key|credential|client[_-]?secret)')
    # Known secret/key formats (OpenAI, GitHub, Slack, Google, high-entropy hex).
    _SECRET_VALUE_PATTERNS = [
        re.compile(r'^sk-[a-zA-Z0-9]{16,}$'),
        re.compile(r'^gh[pousr]-[a-zA-Z0-9]{16,}$'),
        re.compile(r'^xox[baprs]-[a-zA-Z0-9-]{10,}$'),
        re.compile(r'^AIza[0-9A-Za-z_-]{35}$'),
        re.compile(r'^[0-9a-f]{40,}$'),
    ]
    # Environment-variable / template references are NOT hardcoded secrets.
    _ENV_REF_RE = re.compile(r'^\$?\{\{.*\}\}$|^\$\{\w+\}$|^\$\w+$|^env\([^)]*\)$|^\[\[.*\]\]$')

    @classmethod
    def _is_env_ref(cls, value: str) -> bool:
        """True if *value* is an env-var/template reference rather than a literal."""
        s = value.strip()
        return bool(cls._ENV_REF_RE.match(s)) or "env(" in s.lower()

    @classmethod
    def _iter_leaves(cls, obj: Any, prefix: str = "") -> "list[tuple[str, Any]]":
        """Yield (dotted-path, value) for every scalar leaf in a nested config."""
        out: list[tuple[str, Any]] = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                child = f"{prefix}.{k}" if prefix else str(k)
                out.extend(cls._iter_leaves(v, child))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                out.extend(cls._iter_leaves(v, f"{prefix}[{i}]"))
        else:
            out.append((prefix, obj))
        return out

    @classmethod
    def _looks_like_secret_value(cls, value: Any) -> bool:
        """Heuristic: does a literal value look like a hardcoded secret?"""
        if not isinstance(value, str) or not value.strip():
            return False
        s = value.strip()
        if cls._is_env_ref(s):
            return False
        for pat in cls._SECRET_VALUE_PATTERNS:
            if pat.match(s):
                return True
        # High-entropy mixed-case+digits blob of meaningful length.
        if len(s) >= 32 and re.search(r'[a-z]', s) and re.search(r'[A-Z]', s) and re.search(r'\d', s):
            return True
        return False

    @classmethod
    def validate_step_config(cls, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a step configuration against AI standards.

        M8 fix: inspects the *parsed* JSON structure (leaf key names and values)
        instead of regex-matching ``str(config)``. This closes the bypasses that
        defeated the old regex (``pass word='x'``, ``password:'x'``, escaped
        quotes, keyword-case noise) because we look at actual field names and
        literal values, not raw text.
        """
        issues: list[str] = []
        seen: set[str] = set()

        for key, value in cls._iter_leaves(config):
            if cls._SECRET_KEY_RE.search(key) and isinstance(value, str) and value.strip() and not cls._is_env_ref(value):
                msg = f"Hardcoded secret in field '{key}'"
                if msg not in seen:
                    seen.add(msg)
                    issues.append(msg)
            if cls._looks_like_secret_value(value):
                msg = f"Field '{key}' contains a value that looks like a hardcoded secret/key"
                if msg not in seen:
                    seen.add(msg)
                    issues.append(msg)

        for key, value in cls._iter_leaves(config):
            if isinstance(value, str) and re.search(r'https?://(127\.0\.0\.1|localhost|0\.0\.0\.0)', value):
                msg = f"Field '{key}' references a localhost/loopback URL (use an environment variable)"
                if msg not in seen:
                    seen.add(msg)
                    issues.append(msg)

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
