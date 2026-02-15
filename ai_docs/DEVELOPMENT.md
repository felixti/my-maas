# MaaS — Development & Testing Guide

## Prerequisites

- Python 3.12
- [uv](https://github.com/astral-sh/uv) (package manager)
- Docker and Docker Compose
- A valid LLM API key (for token threshold strategy testing)

## Setup

```bash
# Clone and install
uv sync

# Configure
cp .env.example .env
# Edit .env — set LLM_API_KEY and EMBEDDING_API_KEY

# Start backing services
docker compose up -d redis mongodb
```

## Running the Application

```bash
# Development (hot reload)
uv run uvicorn maas.main:app --reload

# Production-like
uv run uvicorn maas.main:app --host 0.0.0.0 --port 8000
```

## Code Quality

### Linting

Ruff is configured in `pyproject.toml` with a strict rule set:

```bash
# Check for lint errors
uv run ruff check src/ tests/

# Auto-fix what's possible
uv run ruff check --fix src/ tests/

# Format check
uv run ruff format --check src/ tests/

# Format (apply)
uv run ruff format src/ tests/
```

**Active ruff rules:** E, W, F, I, N, UP, B, A, C4, SIM, TCH, RUF, S, DTZ, PT, RET, ARG

### Coding Conventions

| Convention | Rule |
|---|---|
| Future annotations | All files start with `from __future__ import annotations` |
| FastAPI dependencies | `Annotated[Type, Depends(fn)]` pattern (not `= Depends(fn)`) |
| Type-only imports | Go in `TYPE_CHECKING` blocks |
| Pydantic field types | Use `# noqa: TC001` for runtime-required type imports |
| String enums | All enums use `StrEnum` |
| Async patterns | Redis and LLM calls are always async |

## Testing

### Running Tests

```bash
# All tests
uv run pytest -v

# Specific test file
uv run pytest tests/unit/test_documentdb.py -v

# By marker
uv run pytest -m unit -v

# With coverage (if configured)
uv run pytest --cov=maas -v
```

### Test Suite Overview

**62 tests total, all passing.**

| Test File | Count | Scope |
|---|---|---|
| `test_health.py` | 3 | Health endpoint, STM/LTM stub verification |
| `test_stm_router.py` | 10 | STM API endpoints, error handling |
| `test_stm_store.py` | 4 | Redis message store operations |
| `test_stm_strategies.py` | 2 | Sliding window + token threshold strategies |
| `test_ltm_router.py` | 13 | LTM API endpoints, filter combinations |
| `test_ltm_models.py` | 4 | Pydantic model validation |
| `test_ltm_service.py` | 6 | LTMService + mem0 config builder |
| `test_documentdb.py` | 20 | Azure DocumentDB vector store adapter |

### Test Architecture

```
tests/
├── conftest.py           # Shared fixtures (app client, mock services)
├── unit/
│   ├── test_health.py
│   ├── test_stm_router.py
│   ├── test_stm_store.py
│   ├── test_stm_strategies.py
│   ├── test_ltm_router.py
│   ├── test_ltm_models.py
│   ├── test_ltm_service.py
│   └── test_documentdb.py
└── integration/          # Placeholder for future integration tests
```

### Test Patterns

**STM Router tests** use the FastAPI `TestClient` with mocked Redis (`fakeredis`) and a mocked LLM client:

```python
# conftest.py provides:
# - app fixture with mocked lifespan_resources
# - client fixture (httpx AsyncClient)
# - Mocked Redis, LLM client, and settings
```

**LTM Router tests** mock the `LTMService` at the dependency level:

```python
# LTM service is replaced via app.dependency_overrides
# mem0 AsyncMemory is never instantiated in unit tests
```

**DocumentDB tests** use `unittest.mock.patch` on `pymongo.MongoClient`:

```python
@pytest.fixture
def mock_mongo_client():
    with patch("maas.vector_stores.documentdb.MongoClient") as mock_cls:
        # Set up mock client → db → collection chain
        yield mock_client, mock_db, mock_collection

# Test classes use @pytest.mark.usefixtures("mock_mongo_client")
# to activate the patch without needing the fixture value
```

### Known Test Warnings

The following warnings appear during tests and are **harmless**:

1. **OpenLIT deprecation warnings** — OpenLIT uses deprecated `EventLoggerProvider` APIs. These come from the library, not our code.
2. **OTEL `ConnectionRefusedError`** — The OTEL exporter tries to send metrics/traces to `localhost:4318` which isn't running during unit tests. This happens after all tests complete and doesn't affect results.

## Docker Build

```bash
# Build the image
docker compose build maas

# Or directly
docker build -t my-maas:dev .

# Run the full stack
docker compose up -d

# View logs
docker compose logs -f maas

# Rebuild after code changes
docker compose build maas && docker compose up -d maas
```

## Project File Map

```
src/maas/
├── __init__.py
├── main.py                    # FastAPI app factory, lifespan, health
├── config.py                  # Settings, enums, provider base URLs
├── dependencies.py            # LifespanResources (Redis, LLM client)
├── llm/
│   ├── __init__.py
│   ├── gateway.py             # create_llm_client() → AsyncOpenAI
│   └── embeddings.py          # CohereEmbedding + register function
├── stm/
│   ├── __init__.py
│   ├── models.py              # Message, StoredMessage, ContextResponse
│   ├── store.py               # MessageStore (Redis sorted sets + tiktoken)
│   ├── strategies.py          # WindowStrategy ABC + implementations
│   └── router.py              # 5 STM endpoints
├── ltm/
│   ├── __init__.py
│   ├── models.py              # MemoryCategory, AddMemoryRequest, etc.
│   ├── config.py              # build_mem0_config(settings) → dict
│   ├── service.py             # LTMService (mem0 AsyncMemory wrapper)
│   └── router.py              # 7 LTM endpoints
├── vector_stores/
│   ├── __init__.py
│   └── documentdb.py          # AzureDocumentDB (VectorStoreBase)
└── observability/
    ├── __init__.py
    ├── tracing.py             # OTEL TracerProvider setup/teardown
    └── middleware.py           # FastAPI + OpenLIT instrumentation
```

## Troubleshooting

### `ImportError: No module named 'maas'`

When running in Docker: ensure `PYTHONPATH="/app/src"` is set in the Dockerfile runtime stage. `uv sync --no-install-project` doesn't install the package itself.

### `ConnectionRefusedError` on port 4318

The OTEL Collector isn't running. Start it via `docker compose up -d otel-collector`. This error is non-fatal — the app runs without observability.

### `lru_cache` and test isolation

`get_settings()` uses `@lru_cache(maxsize=1)`. Tests override settings via `lifespan_resources.settings` (the `main.py` monkeypatches `config.get_settings` to check lifespan_resources first).

### Azure DocumentDB connection failures

Ensure:
- TLS is enabled in the connection string (`tls=true`)
- Auth mechanism is `SCRAM-SHA-256`
- `retrywrites=false` is set
- IP allowlisting is configured in Azure portal
