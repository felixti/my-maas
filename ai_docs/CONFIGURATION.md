# MaaS — Configuration & Deployment Guide

## Configuration System

All configuration is managed via environment variables loaded from a `.env` file using `pydantic-settings`. The `Settings` class in `src/maas/config.py` defines all variables with sensible defaults.

### Configuration Hierarchy

```
.env file → Environment variables → Settings defaults
(highest priority)                   (lowest priority)
```

Docker Compose overrides `REDIS_URL`, `MONGODB_URI`, and `OTEL_EXPORTER_OTLP_ENDPOINT` via the `environment:` section in `docker-compose.yml` for container service discovery.

---

## All Configuration Variables

### LLM Provider

| Variable | Type | Default | Description |
|---|---|---|---|
| `LLM_PROVIDER` | enum | `openai` | LLM provider name |
| `LLM_API_KEY` | string | `""` | API key for the LLM provider |
| `LLM_MODEL` | string | `gpt-4.1-mini` | Model name for chat completions |
| `LLM_BASE_URL` | string | `""` | Custom base URL (overrides provider lookup) |
| `LLM_TEMPERATURE` | float | `0.1` | Sampling temperature |
| `LLM_MAX_TOKENS` | int | `4096` | Maximum output tokens |

**Provider → Base URL mapping:**

| Provider Value | Base URL |
|---|---|
| `openai` | `https://api.openai.com/v1` |
| `grok` | `https://api.x.ai/v1` |
| `anthropic` | `https://api.anthropic.com/v1` |
| `openrouter` | `https://openrouter.ai/api/v1` |
| `kimi` | `https://api.moonshot.cn/v1` |
| `glm` | `https://open.bigmodel.cn/api/paas/v4` |
| `minimax` | `https://api.minimax.chat/v1` |
| `together` | `https://api.together.xyz/v1` |
| `deepseek` | `https://api.deepseek.com/v1` |

If `LLM_BASE_URL` is set, it takes precedence over the provider lookup.

### Embedding Provider

| Variable | Type | Default | Description |
|---|---|---|---|
| `EMBEDDING_PROVIDER` | enum | `openai` | Embedding provider |
| `EMBEDDING_API_KEY` | string | `""` | API key (not sent for huggingface/fastembed/ollama) |
| `EMBEDDING_MODEL` | string | `text-embedding-3-small` | Embedding model name |
| `EMBEDDING_BASE_URL` | string | `""` | Custom base URL |
| `EMBEDDING_DIMS` | int | `1536` | Embedding vector dimensions |

**Supported providers:** `openai`, `azure_openai`, `cohere`, `huggingface`, `fastembed`, `ollama`

### STM (Redis)

| Variable | Type | Default | Description |
|---|---|---|---|
| `REDIS_URL` | string | `redis://localhost:6379` | Redis connection URL |
| `STM_DEFAULT_STRATEGY` | enum | `sliding_window` | Default strategy |
| `STM_MAX_MESSAGES` | int | `50` | Max messages for sliding window |
| `STM_MAX_TOKENS` | int | `8000` | Token threshold for summarization |
| `STM_SUMMARIZATION_MODEL` | string | `""` | Model for summarization (falls back to `LLM_MODEL`) |

### LTM (MongoDB / Azure DocumentDB)

| Variable | Type | Default | Description |
|---|---|---|---|
| `MONGODB_URI` | string | `mongodb://localhost:27017` | MongoDB connection URI |
| `MONGODB_DB_NAME` | string | `maas` | Database name |
| `MONGODB_COLLECTION_NAME` | string | `memories` | Collection name |
| `VECTOR_STORE_PROVIDER` | enum | `mongodb` | Vector store backend |

**Vector store providers:**
- `mongodb` — Uses mem0's built-in Atlas MongoDB adapter with `$vectorSearch`
- `azure_documentdb` — Uses custom `AzureDocumentDB` adapter with `cosmosSearch`

### Observability

| Variable | Type | Default | Description |
|---|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | string | `http://localhost:4318` | OTEL Collector OTLP HTTP endpoint |
| `OTEL_SERVICE_NAME` | string | `my-maas` | Service name in traces |
| `LANGFUSE_PUBLIC_KEY` | string | `""` | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | string | `""` | Langfuse secret key |
| `LANGFUSE_BASE_URL` | string | `http://localhost:3000` | Langfuse base URL |

---

## Deployment Modes

### 1. Local Development (Docker Compose)

Full stack with all services:

```bash
cp .env.example .env
# Edit .env — set LLM_API_KEY and EMBEDDING_API_KEY

docker compose up -d
curl http://localhost:8000/health
```

**Services started:**
- `maas` on `:8000` — The MaaS API
- `redis` on `:6379` — STM store
- `mongodb` on `:27017` — LTM vector store (Atlas Local)
- `langfuse` on `:3000` — Trace visualization UI
- `langfuse-db` — PostgreSQL for Langfuse
- `langfuse-redis` — Redis for Langfuse
- `otel-collector` on `:4317/:4318` — Trace pipeline

### 2. Local Dev (Hot Reload)

Run only backing services in Docker, app on host:

```bash
docker compose up -d redis mongodb
uv run uvicorn maas.main:app --reload
```

### 3. Production (Azure DocumentDB)

```bash
# .env for production
VECTOR_STORE_PROVIDER=azure_documentdb
MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster>.mongocluster.cosmos.azure.com/?tls=true&authMechanism=SCRAM-SHA-256&retrywrites=false&maxIdleTimeMS=120000

LLM_PROVIDER=openai
LLM_API_KEY=sk-prod-key
EMBEDDING_PROVIDER=openai
EMBEDDING_API_KEY=sk-prod-key

OTEL_EXPORTER_OTLP_ENDPOINT=https://your-collector.example.com
LANGFUSE_PUBLIC_KEY=pk-lf-prod
LANGFUSE_SECRET_KEY=sk-lf-prod
LANGFUSE_BASE_URL=https://your-langfuse.example.com
```

**Azure DocumentDB requirements:**
- TLS enabled (included in connection string)
- SCRAM-SHA-256 authentication
- `retrywrites=false` (DocumentDB doesn't support retryable writes)
- HNSW vector index auto-created on first startup

---

## Dockerfile Details

Multi-stage build for minimal image size:

```dockerfile
# Stage 1: Base image with uv
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Stage 2: Install dependencies only
FROM base AS deps
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Stage 3: Runtime image
FROM base AS runtime
COPY --from=deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"  # Critical: uv doesn't install the package itself
COPY src/ ./src/
CMD ["uvicorn", "maas.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Key detail**: `PYTHONPATH="/app/src"` is required because `uv sync --no-install-project` doesn't install the `maas` package — it only installs dependencies. The `PYTHONPATH` makes `import maas` work.

---

## Docker Compose Override Example

For production, create a `docker-compose.override.yml`:

```yaml
services:
  maas:
    environment:
      VECTOR_STORE_PROVIDER: azure_documentdb
      MONGODB_URI: mongodb+srv://...
      REDIS_URL: redis://your-redis:6379
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 512M
```

---

## Health Check

The `/health` endpoint returns `{"status": "ok"}` when the FastAPI application is running. It does **not** check backing service connectivity (Redis, MongoDB). For deeper health checks, use the STM and LTM endpoints directly.
