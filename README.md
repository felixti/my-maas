# Memory as a Service (MaaS)

A FastAPI microservice providing **Short-Term Memory (STM)** and **Long-Term Memory (LTM)** for AI agents. STM uses Redis for session-scoped message buffers with sliding window and token-threshold summarization strategies. LTM uses [mem0](https://github.com/mem0ai/mem0) backed by MongoDB (Azure DocumentDB in production) for persistent semantic memory across four categories: semantic, episodic, fact, and preference. Observable via OpenTelemetry with Langfuse integration.

## Features

- **STM**: Session-scoped message buffers with two strategies — sliding window (keep last N messages) and token threshold (LLM-powered summarization when token count exceeds limit)
- **LTM**: Persistent semantic memory via mem0 with four categories (semantic, episodic, fact, preference) differentiated by metadata filters
- **Configurable LLM providers**: All calls use the OpenAI Chat Completions API protocol — supports OpenAI, Grok, Anthropic, OpenRouter, Kimi, GLM, Minimax, Together, DeepSeek, or any custom endpoint
- **Configurable embedding providers**: OpenAI, Azure OpenAI, Cohere, HuggingFace, FastEmbed, Ollama
- **Observability**: OpenTelemetry traces exported via OTEL Collector to Langfuse, with GenAI semantic conventions via OpenLIT auto-instrumentation
- **Containerized**: Multi-stage Dockerfile, full Docker Compose stack for local development
- **Memory TTL**: Configurable time-to-live for both STM sessions (Redis EXPIRE) and LTM memories (metadata-based expiration)
- **Batch Operations**: Bulk add, search, and delete for LTM with per-item error handling
- **CI/CD**: GitHub Actions pipeline with lint, test, integration test, Docker build, and push stages

## Tech Stack

| Component | Technology |
|---|---|
| Runtime | Python 3.12, FastAPI, AsyncIO |
| LTM Engine | mem0 (AsyncMemory) |
| STM Store | Redis (sorted sets) |
| LTM Store | DocumentDB Local (dev) / Azure DocumentDB (prod) |
| Observability | OpenTelemetry + Langfuse + OpenLIT |
| Package Manager | uv |
| Linter/Formatter | Ruff |
| Tests | PyTest (85 unit + 19 integration) |

## Architecture

### Short-Term Memory (STM)

Redis sorted sets hold per-session message buffers. Each message is scored by timestamp for ordering. Two strategies control the context window:

- **Sliding Window**: Retains the last N messages (configurable via `STM_MAX_MESSAGES`).
- **Token Threshold**: When total tokens exceed `STM_MAX_TOKENS`, older messages are summarized into a single summary message via the configured LLM, then replaced in the buffer.

### Long-Term Memory (LTM)

mem0 `AsyncMemory` backed by MongoDB vector store. A single mem0 instance handles all memory types — the four categories (semantic, episodic, fact, preference) are metadata-level filters, not separate stores. Embedding and LLM providers are fully configurable via environment variables.

### Observability

OTEL `TracerProvider` with `BatchSpanProcessor` exports traces via OTLP HTTP to an OTEL Collector, which forwards to Langfuse. OpenLIT auto-instruments LLM and mem0 calls with GenAI semantic conventions (`gen_ai.*` namespace).

## API Reference

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |

### STM (Short-Term Memory)

| Method | Path | Description |
|---|---|---|
| `POST` | `/stm/{session_id}/messages` | Add messages to a session |
| `GET` | `/stm/{session_id}/messages` | Get messages (optional `?limit=N`) |
| `GET` | `/stm/{session_id}/context` | Get context window (applies active strategy) |
| `DELETE` | `/stm/{session_id}` | Delete a session |
| `PUT` | `/stm/{session_id}/config` | Set per-session strategy config |

### LTM (Long-Term Memory)

| Method | Path | Description |
|---|---|---|
| `POST` | `/ltm/memories` | Add a memory |
| `POST` | `/ltm/memories/search` | Search memories by query |
| `DELETE` | `/ltm/memories/expired` | Delete expired memories (TTL cleanup) |
| `POST` | `/ltm/memories/batch/add` | Bulk add memories |
| `POST` | `/ltm/memories/batch/search` | Bulk search memories |
| `POST` | `/ltm/memories/batch/delete` | Bulk delete memories |
| `GET` | `/ltm/memories` | List memories (filter by user_id, agent_id, session_id) |
| `GET` | `/ltm/memories/{memory_id}` | Get a specific memory |
| `PUT` | `/ltm/memories/{memory_id}` | Update a memory |
| `DELETE` | `/ltm/memories/{memory_id}` | Delete a memory |
| `GET` | `/ltm/memories/{memory_id}/history` | Get memory change history |

## Quick Start

**Prerequisites**: Docker and Docker Compose.

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env — set LLM_API_KEY and EMBEDDING_API_KEY at minimum

# 2. Start all services
docker compose up -d

# 3. Verify
curl http://localhost:8000/health
# {"status": "ok"}

# 4. Browse API docs
open http://localhost:8000/docs
```

## Local Development

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Configure
cp .env.example .env

# Start backing services only
docker compose up -d redis documentdb

# Run dev server
uv run uvicorn maas.main:app --reload

# Run tests
uv run pytest tests/unit/ -v        # 85 unit tests
uv run pytest tests/integration/ -v  # 19 integration tests (requires Docker)

# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/
```

## Configuration

All configuration is via environment variables (loaded from `.env`).

> Docker Compose overrides `REDIS_URL`, `MONGODB_URI`, and `OTEL_EXPORTER_OTLP_ENDPOINT` for container service discovery.

### LLM

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openai` | LLM provider name (see provider list below) |
| `LLM_API_KEY` | — | API key for the LLM provider |
| `LLM_MODEL` | `gpt-4.1-mini` | Model name |
| `LLM_BASE_URL` | — | Custom base URL (overrides provider default) |
| `LLM_TEMPERATURE` | `0.1` | Sampling temperature |
| `LLM_MAX_TOKENS` | `4096` | Max output tokens |

### Embeddings

| Variable | Default | Description |
|---|---|---|
| `EMBEDDING_PROVIDER` | `openai` | Embedding provider (`openai`, `azure_openai`, `cohere`, `huggingface`, `fastembed`, `ollama`) |
| `EMBEDDING_API_KEY` | — | API key for embedding provider |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model name |
| `EMBEDDING_BASE_URL` | — | Custom base URL for embeddings |
| `EMBEDDING_DIMS` | `1536` | Embedding dimensions |

### STM (Redis)

| Variable | Default | Description |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `STM_DEFAULT_STRATEGY` | `sliding_window` | Default strategy (`sliding_window` or `token_threshold`) |
| `STM_MAX_MESSAGES` | `50` | Max messages for sliding window |
| `STM_MAX_TOKENS` | `8000` | Token threshold for summarization trigger |
| `STM_SUMMARIZATION_MODEL` | — | Model for summarization (defaults to `LLM_MODEL`) |
| `STM_SESSION_TTL_SECONDS` | `86400` | Session TTL in seconds (0 = no expiration) |

### LTM (MongoDB / Azure DocumentDB)

| Variable | Default | Description |
|---|---|---|
| `VECTOR_STORE_PROVIDER` | `mongodb` | Vector store backend (`mongodb` for DocumentDB Local, `azure_documentdb` for Azure DocumentDB) |
| `VECTOR_INDEX_TYPE` | `diskann` | Vector index type (`diskann` for scaling to 500K+, `hnsw` for legacy up to 50K) |
| `MONGODB_URI` | `mongodb://localhost:10260/?tls=true&tlsAllowInvalidCertificates=true&authMechanism=SCRAM-SHA-256&retrywrites=false` | MongoDB/DocumentDB connection URI (DocumentDB Local includes TLS params by default) |
| `MONGODB_DB_NAME` | `maas` | Database name |
| `MONGODB_COLLECTION_NAME` | `memories` | Collection name |
| `LTM_DEFAULT_TTL_SECONDS` | `0` | Memory TTL in seconds (0 = no expiration) |
| `LTM_MAX_BATCH_SIZE` | `50` | Max items per batch request |

### Observability

| Variable | Default | Description |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | OTEL Collector endpoint |
| `OTEL_SERVICE_NAME` | `my-maas` | Service name in traces |
| `LANGFUSE_PUBLIC_KEY` | — | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | — | Langfuse secret key |
| `LANGFUSE_BASE_URL` | `http://localhost:3000` | Langfuse base URL |

## LLM Provider Configuration

All LLM calls go through the OpenAI Chat Completions API. The `LLM_PROVIDER` env var selects a provider, which maps to a base URL:

| Provider | Base URL |
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

For unlisted providers, set `LLM_BASE_URL` directly to any OpenAI-compatible endpoint.

## Azure DocumentDB (Production Vector Store)

For local development, DocumentDB Local is used as the LTM backend with the same custom adapter (`azure_documentdb` provider) that works with production Azure DocumentDB. In production with Azure DocumentDB (MongoDB compatibility), set `VECTOR_STORE_PROVIDER=azure_documentdb` to use the custom adapter that translates to DocumentDB's `cosmosSearch` API.

### Key differences from MongoDB Atlas:

| Feature | Atlas (`mongodb`) | DocumentDB (`azure_documentdb`) |
|---|---|---|
| Vector search | `$vectorSearch` aggregation stage | `$search` with `cosmosSearch` operator |
| Index creation | `SearchIndexModel` API | `db.command("createIndexes")` with `cosmosSearch` key type |
| Score metadata | `$meta: "vectorSearchScore"` | `$meta: "searchScore"` |
| Index type | `vectorSearch` | Configurable (`vector-diskann` or `vector-hnsw`) |

### Configuration for Azure DocumentDB:

```bash
# .env
VECTOR_STORE_PROVIDER=azure_documentdb
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>.mongocluster.cosmos.azure.com/?tls=true&authMechanism=SCRAM-SHA-256&retrywrites=false&maxIdleTimeMS=120000
MONGODB_DB_NAME=maas
MONGODB_COLLECTION_NAME=memories
EMBEDDING_DIMS=1536  # Must match your embedding model's dimensions
```

**Note on DocumentDB Local**: The same `azure_documentdb` adapter works with DocumentDB Local during development. The default `MONGODB_URI` in `.env` is pre-configured for DocumentDB Local on port 10260 with required TLS parameters. For production Azure DocumentDB, simply update `MONGODB_URI` to your cloud cluster endpoint.

The adapter automatically creates vector indexes (DiskANN by default, configurable via `VECTOR_INDEX_TYPE`) with cosine similarity on first startup. All CRUD operations use standard pymongo and work identically across both providers.

## Docker

**Dockerfile**: Multi-stage build using `python:3.12-slim` with `uv` for dependency resolution. Dependencies are installed in a separate stage and the virtual environment is copied to the runtime image.

**Docker Compose services**:

| Service | Image | Purpose |
|---|---|---|
| `maas` | Built from Dockerfile | The MaaS API server |
| `redis` | `redis:7-alpine` | STM message store |
| `documentdb` | `ghcr.io/documentdb/documentdb/documentdb-local:latest` | LTM vector + document store (DocumentDB Local) |
| `langfuse` | `langfuse/langfuse` | Trace visualization |
| `langfuse-db` | `postgres:16-alpine` | Langfuse database |
| `langfuse-redis` | `redis:7-alpine` | Langfuse cache |
| `otel-collector` | `otel/opentelemetry-collector-contrib` | Trace pipeline |

```bash
# Build
docker compose build maas

# Run everything
docker compose up -d

# Run only backing services (for local dev)
docker compose up -d redis documentdb
```

## Project Structure

```
src/maas/
├── main.py                # FastAPI app, lifespan, health endpoint
├── config.py              # Settings, enums, provider registry
├── dependencies.py        # Lifespan resources (Redis, LLM client)
├── llm/
│   ├── gateway.py         # AsyncOpenAI client factory
│   └── embeddings.py      # Cohere embedding + mem0 registration
├── stm/
│   ├── models.py          # STM Pydantic models
│   ├── store.py           # Redis message store (sorted sets)
│   ├── strategies.py      # Window strategies (sliding, token threshold)
│   └── router.py          # STM API endpoints
├── ltm/
│   ├── models.py          # LTM Pydantic models (CRUD + batch)
│   ├── config.py          # mem0 config builder
│   ├── service.py         # LTM service (AsyncMemory wrapper + batch ops)
│   └── router.py          # LTM API endpoints (11 routes)
├── vector_stores/
│   └── documentdb.py      # Azure DocumentDB vector store adapter for mem0
└── observability/
    ├── tracing.py          # OTEL TracerProvider setup/teardown
    └── middleware.py        # FastAPI + OpenLIT instrumentation
```

## CI/CD

GitHub Actions pipeline (`.github/workflows/ci.yml`) with 5 sequential jobs:

1. **lint** — Ruff check + format verification
2. **unit-test** — 85 unit tests with pytest
3. **integration-test** — 19 integration tests with testcontainers (Redis + MongoDB)
4. **docker-build** — Multi-stage Docker build with BuildKit cache
5. **docker-push** — Push to GHCR (main branch only)

Triggers on push to `main` and pull requests targeting `main`.

## License

MIT
