"""
Regression tests for the AI provider abstraction (OpenAI-compliant + llama.cpp).

The AI service speaks two backends behind one ``_call_ai`` entry point:
  * ``llama_cpp`` (local, no API key) — the default, so internal/local use always works;
  * ``openai`` (any OpenAI-compatible endpoint) — opt-in via ``AI_PROVIDER=openai`` and
    an optional ``OPENAI_API_KEY``.

These tests pin:
  * the default provider is ``llama_cpp`` (llama.cpp access is never broken by default);
  * dispatch routes to the configured provider;
  * the OpenAI path requires a key (optional — empty key raises, never silently no-ops);
  * the OpenAI request is wire-compliant: ``POST <base>/chat/completions`` with a Bearer
    token and a ``messages`` array (the standard Chat Completions body), so any OpenAI
    compatible gateway accepts it.
"""
import pytest
import httpx

from app.core.config import settings
from app.services import ai_service as ai_service_mod
from app.services.ai_service import AIService


@pytest.fixture(autouse=True)
def _restore_ai_settings():
    saved = {k: getattr(settings, k) for k in (
        "ai_provider", "openai_api_key", "openai_model", "openai_base_url")}
    yield
    for k, v in saved.items():
        object.__setattr__(settings, k, v)


def _set(attr, value):
    # pydantic-settings ignores plain assignment; use object.__setattr__.
    object.__setattr__(settings, attr, value)


@pytest.fixture()
def service():
    return AIService()


# --- provider selection ------------------------------------------------------


def test_default_provider_is_llama_cpp():
    # Out-of-the-box the local backend works with no key and no external server config.
    assert settings.ai_provider == "llama_cpp"


@pytest.mark.asyncio
async def test_dispatch_routes_to_configured_provider(service, monkeypatch):
    last = {}

    async def fake_openai(prompt):
        last["provider"] = "openai"
        last["prompt"] = prompt
        return "from-openai"

    async def fake_llama(prompt):
        last["provider"] = "llama_cpp"
        last["prompt"] = prompt
        return "from-llama"

    monkeypatch.setattr(service, "_call_openai", fake_openai)
    monkeypatch.setattr(service, "_call_llama_cpp", fake_llama)

    _set("ai_provider", "openai")
    assert await service._call_ai("hi") == "from-openai"
    assert last == {"provider": "openai", "prompt": "hi"}

    _set("ai_provider", "llama_cpp")
    assert await service._call_ai("hi") == "from-llama"
    assert last == {"provider": "llama_cpp", "prompt": "hi"}


# --- optional API key --------------------------------------------------------


@pytest.mark.asyncio
async def test_openai_without_key_raises(service):
    """No key + openai provider must fail loudly, not silently do nothing."""
    _set("ai_provider", "openai")
    _set("openai_api_key", "")
    with pytest.raises(ValueError, match="API key"):
        await service._call_openai("hi")


# --- OpenAI wire compatibility ----------------------------------------------


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
        return _FakeResp({"choices": [{"message": {"content": "hi"}}]})


@pytest.mark.asyncio
async def test_openai_request_is_wire_compliant(service, monkeypatch):
    _set("ai_provider", "openai")
    _set("openai_api_key", "sk-test-123")
    _set("openai_model", "gpt-4o")
    monkeypatch.setattr(ai_service_mod.httpx, "AsyncClient", _FakeClient)

    result = await service._call_openai("Explain photosynthesis")

    assert result == "hi"
    req = _FakeClient.last_request

    # Standard Chat Completions endpoint.
    assert req["url"].rstrip("/").endswith("/chat/completions")
    # Bearer auth with the configured key.
    assert req["headers"]["Authorization"] == "Bearer sk-test-123"
    # Standard messages body (system + user), model echoed back.
    body = req["json"]
    assert body["model"] == "gpt-4o"
    assert body["messages"][0] == {
        "role": "system",
        "content": "You are a helpful assistant that generates JSON responses.",
    }
    assert body["messages"][1] == {
        "role": "user",
        "content": "Explain photosynthesis",
    }
