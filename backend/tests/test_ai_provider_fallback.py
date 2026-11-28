"""M8: automatic LLM provider fallback and request-level attribution.

Pins the four contracts that matter for existing deployments:

* an empty fallback chain is exactly the old single-provider dispatch (including
  the original exception type/message);
* a configured chain retries the same prompt in order and records the provider
  that actually answered;
* an all-failed chain produces one aggregate error naming every provider;
* the AI router adds the attribution as an additive ``X-AI-Provider`` header,
  and settings validation rejects unknown names before they reach dispatch.
"""
from types import SimpleNamespace

import httpx
import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.ai import AIRoute, ai_health
from app.api.system_settings import parse_fallback_providers, update_ai_settings
from app.core.config import settings
from app.services import ai_service as ai_service_mod
from app.services.ai_service import (
    AIService,
    ai_provider_chain,
    get_current_ai_provider,
    reset_current_ai_provider,
)


@pytest.fixture(autouse=True)
def _restore_ai_settings():
    keys = (
        "ai_provider", "ai_fallback_providers", "openai_api_key",
        "openai_model", "openai_base_url", "llama_cpp_url",
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


# --- chain parsing -----------------------------------------------------------


def test_empty_chain_is_primary_only():
    _set("ai_provider", "llama_cpp")
    _set("ai_fallback_providers", "")
    assert ai_provider_chain() == ["llama_cpp"]


def test_csv_chain_is_primary_first_deduplicated_and_validated():
    _set("ai_provider", "llama_cpp")
    _set("ai_fallback_providers", " openai, llama_cpp , bogus,openai ")
    assert ai_provider_chain() == ["llama_cpp", "openai"]


def test_json_chain_is_supported():
    _set("ai_provider", "openai")
    _set("ai_fallback_providers", '["llama_cpp", "openai", "unknown"]')
    assert ai_provider_chain() == ["openai", "llama_cpp"]


# --- dispatch behavior -------------------------------------------------------


@pytest.mark.asyncio
async def test_single_provider_raises_original_error_verbatim(monkeypatch):
    service = AIService()
    boom = RuntimeError("llama.cpp offline")

    async def fail(prompt):
        raise boom

    monkeypatch.setattr(service, "_call_llama_cpp", fail)
    ai_service_mod.current_ai_provider.set("stale-provider")  # must be cleared per call

    with pytest.raises(RuntimeError) as exc:
        await service._call_ai("prompt")
    assert exc.value is boom
    assert str(exc.value) == "llama.cpp offline"
    assert get_current_ai_provider() is None


@pytest.mark.asyncio
async def test_fallback_retries_same_prompt_and_reports_answering_provider(monkeypatch):
    service = AIService()
    calls = []

    async def fail_openai(prompt):
        calls.append(("openai", prompt))
        raise ValueError("upstream 503")

    async def ok_llama(prompt):
        calls.append(("llama_cpp", prompt))
        return "fallback answer"

    monkeypatch.setattr(service, "_call_openai", fail_openai)
    monkeypatch.setattr(service, "_call_llama_cpp", ok_llama)
    _set("ai_provider", "openai")
    _set("ai_fallback_providers", "llama_cpp")

    assert await service._call_ai("same prompt") == "fallback answer"
    assert calls == [("openai", "same prompt"), ("llama_cpp", "same prompt")]
    assert get_current_ai_provider() == "llama_cpp"


@pytest.mark.asyncio
async def test_all_providers_failed_error_names_each_provider(monkeypatch):
    service = AIService()

    async def fail_openai(prompt):
        raise ValueError("service unavailable")

    async def fail_llama(prompt):
        raise ValueError("connection refused")

    monkeypatch.setattr(service, "_call_openai", fail_openai)
    monkeypatch.setattr(service, "_call_llama_cpp", fail_llama)
    _set("ai_provider", "openai")
    _set("ai_fallback_providers", "llama_cpp")

    with pytest.raises(ValueError) as exc:
        await service._call_ai("prompt")
    message = str(exc.value)
    assert message.startswith("All AI providers failed:")
    assert "openai: service unavailable" in message
    assert "llama_cpp: connection refused" in message
    assert get_current_ai_provider() is None


# --- HTTP attribution --------------------------------------------------------


def test_ai_route_adds_provider_header_and_resets_it_per_request(monkeypatch):
    service = AIService()
    fail_first = {"value": True}

    async def openai_call(prompt):
        if fail_first["value"]:
            raise ValueError("503")
        return "from-openai"

    async def llama_call(prompt):
        return "from-llama"

    monkeypatch.setattr(service, "_call_openai", openai_call)
    monkeypatch.setattr(service, "_call_llama_cpp", llama_call)
    _set("ai_provider", "openai")
    _set("ai_fallback_providers", "llama_cpp")

    router = APIRouter(route_class=AIRoute)

    @router.get("/probe")
    async def probe():
        return {"answer": await service._call_ai("ping")}

    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        fallback = client.get("/probe")
        assert fallback.status_code == 200
        assert fallback.json() == {"answer": "from-llama"}
        assert fallback.headers["X-AI-Provider"] == "llama_cpp"

        fail_first["value"] = False
        primary = client.get("/probe")
        assert primary.json() == {"answer": "from-openai"}
        assert primary.headers["X-AI-Provider"] == "openai"

    assert get_current_ai_provider() is None


@pytest.mark.asyncio
async def test_health_reports_chain_without_paid_openai_probe(monkeypatch):
    class _FakeClient:
        urls = []

        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, **kwargs):
            self.urls.append(url)
            return SimpleNamespace(status_code=200)

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    _set("ai_provider", "openai")
    _set("ai_fallback_providers", "llama_cpp")
    _set("openai_api_key", "sk-test-key")

    payload = await ai_health()

    assert payload["provider"] == "openai"
    assert payload["fallback_providers"] == ["llama_cpp"]
    assert payload["providers"]["openai"]["status"] == "configured"
    assert payload["providers"]["llama_cpp"]["status"] == "healthy"
    assert payload["status"] == "healthy"
    # No paid Chat Completions probe: the only HTTP call is the local /health check.
    assert _FakeClient.urls == [f"{settings.llama_cpp_url}/health"]


# --- settings validation -----------------------------------------------------


def test_parse_fallback_providers_normalizes_and_rejects_unknown_names():
    assert parse_fallback_providers("") == ""
    assert parse_fallback_providers("openai, llama_cpp, openai") == "openai,llama_cpp"
    assert parse_fallback_providers('["llama_cpp", "openai"]') == "llama_cpp,openai"
    with pytest.raises(ValueError, match="Invalid fallback provider: bogus"):
        parse_fallback_providers("bogus")
    with pytest.raises(ValueError, match="Invalid fallback provider list"):
        parse_fallback_providers("[openai")


@pytest.mark.asyncio
async def test_update_ai_settings_validates_and_persists_chain():
    admin = SimpleNamespace(role="admin")
    with pytest.raises(HTTPException) as exc:
        await update_ai_settings(
            ai_provider="llama_cpp", ai_fallback_providers="bogus", current_user=admin
        )
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        await update_ai_settings(ai_provider="bogus", current_user=admin)
    assert exc.value.status_code == 400

    result = await update_ai_settings(
        ai_provider="openai",
        ai_fallback_providers=" llama_cpp, openai ",
        current_user=admin,
    )
    assert result["settings"]["ai_fallback_providers"] == "llama_cpp,openai"
    assert settings.ai_fallback_providers == "llama_cpp,openai"

    with pytest.raises(HTTPException) as exc:
        await update_ai_settings(
            ai_fallback_providers="openai", current_user=SimpleNamespace(role="user")
        )
    assert exc.value.status_code == 403
