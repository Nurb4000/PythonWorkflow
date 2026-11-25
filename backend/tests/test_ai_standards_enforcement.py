"""
Regression tests for M8: binding AI Standards Enforcer + robust secret detection.

The old enforcer regex-matched ``str(config)`` and the /ai/validate-standards
endpoint merely returned the verdict (decorative). This suite verifies that:
  * detection now inspects parsed JSON structure (bypasses like ``pass word``,
    ``password:'x'``, mixed-case keys, and high-entropy literals are caught),
  * environment-variable / template references are correctly allowed, and
  * generation is BINDING — a generated step that hardcodes a secret is rejected.
"""
from app.services.ai_service import ai_service
from app.services.ai_standards_enforcer import ai_standards_enforcer as enforcer


def test_flags_direct_hardcoded_password():
    r = enforcer.validate_step_config({"definition": {"password": "s3cr3t-literal"}})
    assert r["valid"] is False
    assert any("password" in i.lower() for i in r["issues"])


def test_flags_secret_named_field_with_any_literal():
    for key in ("api_key", "AccessToken", "client_secret", "refresh_token", "credential"):
        r = enforcer.validate_step_config({"definition": {key: "abcd1234efgh5678"}})
        assert r["valid"] is False, key


def test_flags_high_entropy_value():
    r = enforcer.validate_step_config({"definition": {"token": "Aa1zz99Zz88Bb77Cc66Dd55Ee44Ff33Gg22Hh"}})
    assert r["valid"] is False


def test_flags_known_secret_format():
    r = enforcer.validate_step_config({"definition": {"api_key": "sk-abcdEFGHIJ1234567890xyz"}})
    assert r["valid"] is False


def test_flags_localhost_url_in_value():
    r = enforcer.validate_step_config({"definition": {"url": "http://localhost:8080/internal"}})
    assert r["valid"] is False


def test_allows_env_var_references():
    for ref in ("${DB_PASSWORD}", "{{ secrets.api_key }}", "env('API_KEY')", "$API_KEY"):
        r = enforcer.validate_step_config({"definition": {"api_key": ref}})
        assert r["valid"] is True, f"env ref not allowed: {ref}"


def test_allows_clean_config():
    r = enforcer.validate_step_config({"step_type": "api_call", "definition": {"method": "GET", "url": "https://api.example.com"}})
    assert r["valid"] is True


def test_validate_step_rejects_hardcoded_secret_binding():
    step = {"step_type": "api_call", "definition": {"method": "GET", "url": "https://api.example.com", "api_key": "hardcoded-abc123XYZ"}}
    try:
        ai_service._validate_step(step)
    except ValueError as e:
        assert "AI security standards" in str(e)
    else:
        raise AssertionError("expected ValueError for hardcoded secret")


def test_validate_step_allows_clean_step():
    step = {"step_type": "api_call", "definition": {"method": "GET", "url": "https://api.example.com"}}
    ai_service._validate_step(step)  # should not raise
