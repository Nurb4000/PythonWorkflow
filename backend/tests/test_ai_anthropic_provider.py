"""F3: Anthropic Claude provider parity with the M8 provider/fallback layer.

Pins the same contracts as the OpenAI provider tests, plus provider parity:
explicit dispatch/attribution, wire-compatible Messages API requests, fallback
and aggregate errors, masked settings, and a config-only health check.
"""
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from app.api.ai import ai_health
from app.api.system_settings import get_settings, update_ai_settings
from app.core.config import settings
from app.services import ai_service as ai_service_mod
from app.services.ai_service import AIService, get_current_ai_provider, reset_current_ai_provider


@pytest.fixture(autouse=True)
def _restore_ai_settings():
    keys = (
        "ai_provider", "ai_fallback_providers",
        "openai_api_key", "openai_model", "openai_base_url",
        "anthropic_api_key", "anthropic_model", "anthropic_base_url",
    )
    saved = {k: getattr(settings, k) for k in keys}
    reset_current_ai_provider()
    yield
    for k, v in saved.items():
        object.__setattr__(settings, k, v)  # pydantic-settings ignores plain assignment
    reset_current_ai_provider()


def _set(attr, value):
    object.__setattr__(settings, attr, value)


@pytest.fixture()
def service():
    return AIService()


# --- dispatch / attribution ---------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_routes_to_anthropic(service, monkeypatch):
    calls = []

    async def fake_anthropic(prompt):
        calls.append(("anthropic", prompt))
        return "from-claude"

    async def fake_llama(prompt):
        calls.append(("llama_cpp", prompt))
        return "from-llama"

    monkeypatch.setattr(service, "_call_anthropic", fake_anthropic)
    monkeypatch.setattr(service, "_call_llama_cpp", fake_llama)
    _set("ai_provider", "anthropic")
    _set("ai_fallback_providers", "")

    assert await service._call_ai("hi") == "from-claude"
    assert get_current_ai_provider() == "anthropic"
    assert calls == [("anthropic", "hi")]


@pytest.mark.asyncio
async def test_anthropic_without_key_raises(service):
    _set("anthropic_api_key", "")
    with pytest.raises(ValueError, match="Anthropic API key not configured"):
        await service._call_anthropic("hi")


# --- Messages API wire compatibility -----------------------------------------


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeClient:
    last_request = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, *, headers=None, json=None, timeout=None):
        _FakeClient.last_request = {
            "url": url, "headers": headers, "json": json, "timeout": timeout,
        }
        return _FakeResp({"content": [{"type": "text", "text": "claude reply"}]})


@pytest.mark.asyncio
async def test_anthropic_request_is_wire_compliant(service, monkeypatch):
    _set("anthropic_api_key", "sk-ant-test")
    _set("anthropic_model", "claude-sonnet-5-5")
    _set("anthropic_base_url", "https://api.anthropic.com/v1")
    monkeypatch.setattr(ai_service_mod.httpx, "AsyncClient", _FakeClient)

    result = await service._call_anthropic("Explain photosynthesis")

    assert result == "claude reply"
    req = _FakeClient.last_request
    assert req["url"].rstrip("/").endswith("/messages")
    assert req["headers"]["x-api-key"] == "sk-ant-test"
    assert req["headers"]["anthropic-version"] == "2026-10-21"
    body = req["json"]
    assert body["model"] == "claude-sonnet-5-5"
    assert body["max_tokens"] == 2000
    assert body["system"] == "You are a helpful assistant that generates JSON responses."
    assert body["messages"] == [{"role": "user", "content": "Explain photosynthesis"}]
    # API version 2026-10-21 rejects these sampling parameters entirely.
    for key in ("temperature", "top_p", "top_k"):
        assert key not in body


@pytest.mark.asyncio
async def test_anthropic_uses_first_text_block(service, monkeypatch):
    _set("anthropic_api_key", "sk-ant-test")

    class _MixedClient(_FakeClient):
        async def post(self, url, *, headers=None, json=None, timeout=None):
            return _FakeResp({"content": [
                {"type": "thinking", "thinking": "internal"},
                {"type": "text", "text": "answer"},
            ]})

    monkeypatch.setattr(ai_service_mod.httpx, "AsyncClient", _MixedClient)
    assert await service._call_anthropic("hi") == "answer"


# --- fallback parity (M8) -----------------------------------------------------


@pytest.mark.asyncio
async def test_anthropic_fallback_retries_same_prompt_and_is_attributed(service, monkeypatch):
    calls = []

    async def fake_openai(prompt):
        calls.append(("openai", prompt))
        raise ValueError("OpenAI error: boom")

    async def fake_anthropic(prompt):
        calls.append(("anthropic", prompt))
        return "from-claude"

    monkeypatch.setattr(service, "_call_openai", fake_openai)
    monkeypatch.setattr(service, "_call_anthropic", fake_anthropic)
    _set("ai_provider", "openai")
    _set("ai_fallback_providers", "anthropic")

    assert await service._call_ai("same prompt") == "from-claude"
    assert calls == [("openai", "same prompt"), ("anthropic", "same prompt")]
    assert get_current_ai_provider() == "anthropic"


@pytest.mark.asyncio
async def test_all_failed_chain_names_anthropic(service, monkeypatch):
    async def boom(prompt):
        raise ValueError("boom")

    monkeypatch.setattr(service, "_call_openai", boom)
    monkeypatch.setattr(service, "_call_anthropic", boom)
    _set("ai_provider", "openai")
    _set("ai_fallback_providers", "anthropic")

    with pytest.raises(
        ValueError, match="All AI providers failed: openai: boom; anthropic: boom"
    ):
        await service._call_ai("hi")


# --- settings / health parity -------------------------------------------------


@pytest.mark.asyncio
async def test_settings_accept_anthropic_and_mask_key():
    admin = SimpleNamespace(role="admin")
    result = await update_ai_settings(
        ai_provider="anthropic",
        anthropic_api_key="sk-ant-real",
        anthropic_model="claude-opus-5-5",
        ai_fallback_providers=" openai, anthropic ",
        current_user=admin,
    )
    assert settings.anthropic_api_key == "sk-ant-real"
    assert settings.ai_fallback_providers == "openai,anthropic"
    assert result["settings"]["anthropic_model"] == "claude-opus-5-5"

    payload = await get_settings(current_user=admin)
    assert payload["anthropic_api_key"] == "***"

    # Sending the mask back must not overwrite the stored key.
    await update_ai_settings(
        ai_provider="anthropic", anthropic_api_key="***", current_user=admin
    )
    assert settings.anthropic_api_key == "sk-ant-real"

    with pytest.raises(HTTPException) as exc:
        await update_ai_settings(
            ai_provider="anthropic",
            ai_fallback_providers="bogus",
            current_user=admin,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_health_reports_claude_without_paid_probe(monkeypatch):
    class _NoHttp:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Claude health must not make a paid probe")

    monkeypatch.setattr(httpx, "AsyncClient", _NoHttp)
    _set("ai_provider", "anthropic")
    _set("ai_fallback_providers", "")
    _set("anthropic_api_key", "sk-ant-test")
    _set("anthropic_model", "claude-sonnet-5-5")

    payload = await ai_health()
    assert payload["provider"] == "anthropic"
    assert payload["providers"]["anthropic"] == {
        "status": "configured", "model": "claude-sonnet-5-5",
    }
    assert payload["status"] == "healthy"
