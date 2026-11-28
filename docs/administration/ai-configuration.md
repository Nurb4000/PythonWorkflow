# AI Configuration

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

The system supports three AI providers for workflow assistance:

| Provider | Use Case | Cost |
|----------|----------|------|
| **llama.cpp** (local) | Offline, private, no API keys | Hardware costs |
| **OpenAI** (cloud, GPT-4) | Faster, better quality, requires API key | Per-token costs |
| **Anthropic Claude** (cloud) | Alternative cloud model, requires API key | Per-token costs |

Choose a primary provider in **Admin → Settings → LLM Configuration**. An optional fallback chain can be configured there or with `AI_FALLBACK_PROVIDERS` (comma-separated, e.g. `openai,llama_cpp`). When the primary call fails, the same prompt is retried against each fallback in order; if all fail, the error names each provider. With an empty chain (the default) behavior is unchanged: one call, one original error.

Every `/ai/*` response that invokes the LLM includes an `X-AI-Provider` header naming the provider that answered (non-LLM utility endpoints such as standards validation do not). `GET /ai/health` reports the status of all configured providers. Cloud providers are checked by configuration only — `/ai/health` makes no paid probe request.

> **Privacy / cost:** a cloud fallback sends prompts off-host. Local-only deployments should leave `AI_FALLBACK_PROVIDERS` empty. Fallback attempts do not consume extra per-user AI quota, but they can increase provider spend within one counted request.

---

## llama.cpp (Local)

### Setup

1. Run llama.cpp server (see `docker-compose.yml` profile: `ai`)
   ```bash
   docker compose --profile ai up -d
   ```

2. Configure in Settings:
   - **Server URL:** `http://llama_cpp:8080` (or localhost if running locally)
   - **Model:** `default` (or your model name)

### Requirements

- GPU recommended (but CPU works)
- Model file in `models/` directory
- At least 4GB RAM for small models

### Pros
- No API costs
- Data stays local (privacy)
- Works offline

### Cons
- Slower than cloud
- Requires hardware setup
- Model quality depends on size

---

## OpenAI (Cloud)

### Setup

1. Get API key from [OpenAI](https://platform.openai.com/api-keys)

2. Configure in Settings:
   - **AI Provider:** Select "OpenAI"
   - **API Key:** Your OpenAI key
   - **Model:** `gpt-4o` (default). The field suggests GPT-4 presets (`gpt-4o`, `gpt-4.1`, `gpt-4-turbo`) but accepts any OpenAI-compatible model ID.
   - **Base URL:** `https://api.openai.com/v1` (default)

### Pricing

- **gpt-3.5-turbo:** ~$0.002 per 1K tokens
- **gpt-4:** ~$0.06 per 1K tokens

Typical workflow assistance: 1-5K tokens per request = $0.002-$0.03

### Pros
- Fast responses
- High quality
- No hardware setup

### Cons
- API costs
- Data sent to OpenAI
- Requires internet

---

## Anthropic Claude (Cloud, F3)

1. Get an API key from [Anthropic](https://console.anthropic.com/).

2. Configure in **Admin → Settings → LLM Configuration**:
   - **AI Provider:** Anthropic Claude
   - **API Key:** your `sk-ant-...` key (masked as `***` when read back)
   - **Model:** `claude-sonnet-5-5` (default); presets also include `claude-opus-5-5` and `claude-haiku-5-5`
   - **Base URL:** `https://api.anthropic.com/v1` (override for a compatible gateway)

Claude uses the Messages API with `anthropic-version: 2026-10-21`; sampling parameters removed in that version are not sent. Fallback ordering, `X-AI-Provider` attribution, the per-request AI quota, and `/ai/health` reporting work the same as for OpenAI. No Anthropic SDK is required — the existing `httpx` dependency is used.

---

## Switching Providers

1. Go to **Admin → Settings → LLM Configuration**
2. Change **AI Provider** dropdown
3. Fill in provider-specific fields:
   - **llama.cpp:** Server URL, Model name
   - **OpenAI / GPT-4:** API key, Model, Base URL
   - **Anthropic Claude:** API key, Model, Base URL
4. Click **Save AI Settings**

**Note:** Changes apply immediately to all AI features.

---

## AI Features

The following features use the configured AI provider:

| Feature | Description |
|---------|-------------|
| **Step Generation** | Generate step configs from natural language |
| **Query Builder Assist** | Generate SQL from descriptions |
| **Form Designer Assist** | Suggest form fields |
| **Error Diagnosis** | Explain run failures |
| **Condition Expression** | Generate Python expressions |

---

## Testing

After configuration, test with any AI feature:

1. Open a workflow in designer
2. Click **AI Assist** on a step
3. Describe what you want (e.g., "API call to get user data")
4. Verify response quality

**Troubleshooting:**
- "Service unavailable" — Check server URL or API key
- "Rate limit" — Reduce request frequency or upgrade plan
- "Invalid model" — Verify model name matches provider

---

## Related Documentation

- [LDAP Integration](./ldap-integration.md)
- [Workflow Designer](../features/workflows/designer.md)
- [Settings Guide](../getting-started/settings.md)

---

*Next: [LDAP Integration](./ldap-integration.md)*
