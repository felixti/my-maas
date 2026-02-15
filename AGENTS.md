# AGENTS.md — MaaS Knowledge Base

## Project Identity

**Memory as a Service (MaaS)** — A FastAPI microservice providing Short-Term Memory (STM) and Long-Term Memory (LTM) for AI agents.

## Quick Facts

| Attribute | Value |
|---|---|
| Language | Python 3.12 |
| Framework | FastAPI + AsyncIO |
| Package Manager | uv |
| Linter | Ruff (strict: E,W,F,I,N,UP,B,A,C4,SIM,TCH,RUF,S,DTZ,PT,RET,ARG) |
| Tests | pytest + pytest-asyncio (85 unit + 19 integration) |
| STM Backend | Redis 7 (sorted sets) |
| LTM Engine | mem0 v1.0.3 (AsyncMemory) |
| LTM Backend | DocumentDB Local (dev, port 10260, TLS) / Azure DocumentDB (prod) |
| Container | Docker multi-stage with uv |
| Observability | OpenTelemetry → OTEL Collector → Langfuse + OpenLIT |

## Architecture Overview

```
Client → FastAPI → STM Router → MessageStore → Redis
                 → LTM Router → LTMService → mem0 AsyncMemory → Embedder + Vector Store
```

- **STM**: Pure Redis message buffer with sliding window and token-threshold summarization strategies. No vector search. No mem0.
- **LTM**: mem0 `AsyncMemory` wrapping MongoDB vector store. Four memory categories (semantic, episodic, fact, preference) as metadata filters on a single collection.
- **LLM Gateway**: Standard providers use `AsyncOpenAI` with configurable `base_url` (9 pre-mapped + custom URL override). Azure OpenAI uses `AsyncAzureOpenAI` with `azure_endpoint`, `api_version`, and deployment-based routing.
- **Vector Store**: Pluggable via `VECTOR_STORE_PROVIDER` env var. `mongodb` (DocumentDB Local) for dev, `azure_documentdb` (custom adapter) for prod.

## Source Layout

```
src/maas/
├── main.py                    # App factory, lifespan, health endpoint
├── config.py                  # pydantic-settings, enums, provider registry
├── dependencies.py            # LifespanResources (startup/shutdown)
├── llm/
│   ├── gateway.py             # AsyncOpenAI factory
│   └── embeddings.py          # CohereEmbedding (custom EmbeddingBase)
├── stm/
│   ├── models.py              # Message, StoredMessage, ContextResponse
│   ├── store.py               # MessageStore (Redis sorted sets + tiktoken)
│   ├── strategies.py          # WindowStrategy ABC + SlidingWindow/TokenThreshold
│   └── router.py              # 5 STM endpoints
├── ltm/
│   ├── models.py              # MemoryCategory, AddMemoryRequest, Batch models
│   ├── config.py              # build_mem0_config(settings) → dict
│   ├── service.py             # LTMService (AsyncMemory wrapper + batch ops)
│   └── router.py              # 11 LTM endpoints (CRUD + TTL + batch)
├── vector_stores/
│   └── documentdb.py          # AzureDocumentDB (custom VectorStoreBase)
└── observability/
    ├── tracing.py             # OTEL TracerProvider + BatchSpanProcessor
    └── middleware.py           # FastAPI + OpenLIT instrumentation
```

## Coding Conventions (MUST FOLLOW)

1. **`from __future__ import annotations`** — Every Python file, first line
2. **`Annotated[Type, Depends(fn)]`** — All FastAPI dependencies (never `= Depends(fn)`)
3. **`TYPE_CHECKING` blocks** — Type-only imports go inside `if TYPE_CHECKING:`
4. **`# noqa: TC001`** — For pydantic field types that need runtime access
5. **`StrEnum`** — All enums inherit from `StrEnum`
6. **No type suppression** — Never use `as any`, `@ts-ignore`, empty catch blocks
7. **Async everywhere** — Redis and LLM calls are always async
8. **Error handling** — Use `logger.exception()` in except blocks, not bare except

## Key Patterns

### Settings Access

```python
from maas.config import get_settings
# get_settings() is @lru_cache(maxsize=1)
# In tests, override via lifespan_resources.settings
# main.py monkeypatches config.get_settings to check lifespan_resources first
```

### mem0 Extension Pattern

Custom providers are registered with mem0's factories before creating Memory instances:

```python
# In dependencies.py startup():
register_cohere_embedder()           # EmbedderFactory
register_documentdb_vector_store()   # VectorStoreFactory

# Registration pattern (3 parts required for vector stores):
# 1. VectorStoreFactory.provider_to_class — so mem0 can instantiate the class
# 2. VectorStoreConfig._provider_configs.default — so pydantic validation accepts the provider
#    (MUST use .default because _provider_configs is a ModelPrivateAttr)
# 3. sys.modules injection — so mem0's dynamic __import__ finds the config module
```

### STM Session Config

Per-session strategy config is stored in Redis as JSON:
- Key: `stm:session:{session_id}:config`
- Falls back to global settings if no per-session config exists

### Docker PYTHONPATH

`uv sync --no-install-project` doesn't install `maas` package. Docker uses `ENV PYTHONPATH="/app/src"` to make imports work.

### TTL Pattern

- **STM**: Redis `EXPIRE` on session keys via `_touch_ttl()` method. Configurable via `stm_session_ttl_seconds` (0=disabled, default 86400=24h).
- **LTM**: `expires_at` timestamp stored in metadata. Post-filtered in `search()` and `get_all()`. `delete_expired()` queries the vector store collection directly via pymongo (bypasses mem0's scope requirement). `DELETE /memories/expired` endpoint for batch cleanup.

### Batch Operations Pattern

- mem0 has no native batch ops — individual calls wrapped with `asyncio.gather` + per-item error handling.
- All batch endpoints at `/ltm/memories/batch/{add,search,delete}` use POST.
- Max batch size enforced at router level via `settings.ltm_max_batch_size` (default 50).
- `BatchAddItem` extends `BaseMemoryRequest` (inherits scope validation).

## API Endpoints (17 total)

| Method | Path | Module |
|---|---|---|
| `GET` | `/health` | main.py |
| `POST` | `/stm/{session_id}/messages` | stm/router.py |
| `GET` | `/stm/{session_id}/messages` | stm/router.py |
| `GET` | `/stm/{session_id}/context` | stm/router.py |
| `DELETE` | `/stm/{session_id}` | stm/router.py |
| `PUT` | `/stm/{session_id}/config` | stm/router.py |
| `POST` | `/ltm/memories` | ltm/router.py |
| `POST` | `/ltm/memories/search` | ltm/router.py |
| `DELETE` | `/ltm/memories/expired` | ltm/router.py |
| `POST` | `/ltm/memories/batch/add` | ltm/router.py |
| `POST` | `/ltm/memories/batch/search` | ltm/router.py |
| `POST` | `/ltm/memories/batch/delete` | ltm/router.py |
| `GET` | `/ltm/memories` | ltm/router.py |
| `GET` | `/ltm/memories/{memory_id}` | ltm/router.py |
| `PUT` | `/ltm/memories/{memory_id}` | ltm/router.py |
| `DELETE` | `/ltm/memories/{memory_id}` | ltm/router.py |
| `GET` | `/ltm/memories/{memory_id}/history` | ltm/router.py |

## Testing

```bash
uv run pytest tests/unit/ -v          # 85 unit tests, all passing
uv run pytest tests/integration/ -v -m integration  # 19 integration tests (requires Docker)
uv run ruff check src/ tests/    # Lint
uv run ruff format --check src/ tests/  # Format check
```

- STM tests: Mock Redis with fakeredis, mock LLM client
- LTM tests: Mock LTMService at dependency level
- DocumentDB tests: Patch `pymongo.MongoClient`, use `@pytest.mark.usefixtures`
- TTL tests: Mock `time.time()` for expiration logic
- Batch tests: Mock service methods, test max-size enforcement via HTTP client
- Integration tests: testcontainers (Redis 7 Alpine + MongoDB 7), session-scoped fixtures
- Known noise: OTEL `ConnectionRefusedError` after tests (no collector running)

## Docker

```bash
docker compose up -d              # Full stack (7 services)
docker compose up -d redis mongodb  # Dev backing services only (DocumentDB Local)
docker compose build maas          # Rebuild app image
```

## Environment Variables

All config via `.env` — see `.env.example` for complete list. Key variables:

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` + `LLM_API_KEY` | LLM access (use `azure_openai` for Azure OpenAI) |
| `EMBEDDING_PROVIDER` + `EMBEDDING_API_KEY` | Embedding access (use `azure_openai` for Azure OpenAI) |
| `REDIS_URL` | STM backend |
| `MONGODB_URI` | LTM backend (DocumentDB Local for dev, Azure DocumentDB for prod) |
| `VECTOR_STORE_PROVIDER` | `mongodb` (dev) or `azure_documentdb` (prod) |
| `STM_SESSION_TTL_SECONDS` | STM session TTL (0=disabled, default 86400) |
| `LTM_DEFAULT_TTL_SECONDS` | LTM memory TTL (0=disabled, default 0) |
| `LTM_MAX_BATCH_SIZE` | Max items per batch request (default 50) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Trace export |

## Build Phases (all complete)

0. Scaffold → 1. Config/LLM → 2. STM → 3. LTM → 4. Cohere → 5. Observability → 6. Lint → 7. Tests → 8. Docker Smoke → 9. DocumentDB Adapter → 10. Integration Tests → 11. Memory TTL → 12. Batch Operations → 13. CI/CD Pipeline

## Known Gotchas

- `importlib` must be set on `builtins` in `main.py` (mem0 uses `builtins.importlib`)
- `S105` false positive on `TOKEN_THRESHOLD` string — suppressed with `# noqa: S105`
- Azure DocumentDB requires `retrywrites=false` in connection string
- mem0 `MongoDBConfig` has strict field validation — only pass expected fields
- Integration tests require Docker daemon running (testcontainers)
- Batch endpoints use POST for all operations (including delete) to avoid path conflict with `{memory_id}`
- **Azure OpenAI** requires `AsyncAzureOpenAI` client (not `AsyncOpenAI` with `base_url`) — see `gateway.py`
- **mem0 `azure_openai` embedder** requires `azure-identity` package even when using API key auth (module-level import)
- **mem0 `azure_kwargs`** structure: `{"api_key": "...", "azure_deployment": "...", "azure_endpoint": "https://...", "api_version": "2024-10-21"}`
- **mem0 filter operators**: mem0 passes `{"in": [...]}` style operators; DocumentDB adapter translates to `{"$in": [...]}` via `_translate_filter_value()`
- **mem0 `VectorStoreConfig._provider_configs`** is a pydantic v2 `ModelPrivateAttr` — must use `.default` dict for registration, not direct assignment
- **mem0 `AsyncMemory.add()`** returns `{"results": [...]}` — `LTMService.add()` unwraps the first result
- **mem0 `update()`** only returns `{"message": "..."}` — `LTMService.update()` re-fetches to return updated memory
