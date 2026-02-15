# MaaS — Architecture Decision Records (ADRs)

---

## ADR-001: Python 3.12 Instead of 3.14

**Status:** Accepted

**Context:** User originally requested Python 3.14. mem0 library is only tested up to Python 3.12.

**Decision:** Use Python 3.12.

**Rationale:** mem0 is the core dependency for LTM. Running on an untested Python version risks obscure runtime failures. Python 3.12 is the latest version mem0 officially supports.

**Consequences:** Cannot use Python 3.14 features (e.g., deferred evaluation of annotations is now default). Using `from __future__ import annotations` for forward-reference support.

---

## ADR-002: STM as Pure Message Buffer (No mem0)

**Status:** Accepted

**Context:** Could use mem0 for both STM and LTM, or keep STM as a simpler Redis-based buffer.

**Decision:** STM uses Redis sorted sets directly, with no mem0/vector search involvement.

**Rationale:**
- STM is a session-scoped message cache, not a semantic memory system
- Redis sorted sets give O(1) append, O(log N) range queries, natural ordering by timestamp
- No embedding overhead for short-term messages
- Simpler failure domain — Redis is independent of MongoDB/vector store

**Consequences:** Two separate storage backends to manage. STM has no semantic search capability (by design — it's a buffer, not a knowledge base).

---

## ADR-003: LTM Sub-Types as Metadata Categories

**Status:** Accepted

**Context:** Four memory types (semantic, episodic, fact, preference) need differentiation. Options:
1. Separate mem0 instances per type (4 vector collections)
2. Single mem0 instance with metadata-level category field

**Decision:** Single mem0 instance, differentiate via `metadata.category` field.

**Rationale:**
- Simpler architecture — one vector collection, one embedding model
- Cross-category search is possible (search all types at once)
- Less operational overhead
- mem0's filter API supports `{"category": {"in": ["semantic", "fact"]}}`

**Consequences:** All categories share the same vector space. A search without category filter returns results from all types (which is usually desirable).

---

## ADR-004: OpenAI Chat Completions API as Universal LLM Protocol

**Status:** Accepted (user requirement)

**Context:** User explicitly stated: "we should talk always OpenAI Chat Completions API regarding the provider or model."

**Decision:** All LLM calls go through `AsyncOpenAI` client with a configurable `base_url` per provider.

**Rationale:**
- Most LLM providers now expose OpenAI-compatible endpoints
- Single client library (`openai`) handles all providers
- Provider switching is a config change, not a code change
- `PROVIDER_BASE_URLS` dict maps provider enum → base URL

**Consequences:** Providers that don't support the OpenAI protocol can't be used. In practice, all listed providers (OpenAI, Grok, Anthropic, OpenRouter, Kimi, GLM, Minimax, Together, DeepSeek) have OpenAI-compatible endpoints.

---

## ADR-005: MongoDB Atlas Local for Development, Custom Adapter for Production

**Status:** Accepted

**Context:** Azure DocumentDB uses different vector search APIs than MongoDB Atlas. Options:
1. Use DocumentDB for both dev and prod (no local container available)
2. Use Atlas Local for dev, adapt for prod
3. Use a different vector store entirely

**Decision:** Use `mongodb/mongodb-atlas-local` container for development with mem0's built-in MongoDB adapter. Build a custom `VectorStoreBase` subclass for Azure DocumentDB in production.

**Rationale:**
- Atlas Local container works out of the box with mem0's built-in MongoDB adapter
- Development doesn't require Azure credentials or network access
- The custom adapter only needs to differ in index creation and search pipeline
- Standard CRUD operations are identical across both

**Consequences:** Two code paths for vector operations. Must test both. The `VECTOR_STORE_PROVIDER` env var switches between them.

---

## ADR-006: Custom VectorStoreBase Subclass (Not Monkey-Patching)

**Status:** Accepted (user-approved Option A)

**Context:** Need to make mem0 work with Azure DocumentDB's vector search API. Options:
- **A:** Full custom `VectorStoreBase` subclass
- **B:** Monkey-patch mem0's Atlas MongoDB adapter
- **C:** Fork mem0's MongoDB adapter

**Decision:** Full custom subclass registered with `VectorStoreFactory`.

**Rationale:**
- Clean separation — no fragile patching that breaks on mem0 updates
- Full control over all 11 methods
- Follows mem0's own extension pattern (factory + dotted class path)
- Easy to test in isolation with mocked pymongo

**Consequences:** ~350 lines of new code. Must keep in sync with mem0's `OutputData` model and `VectorStoreBase` interface if they change.

---

## ADR-007: Cohere Embedding via Custom EmbeddingBase Subclass

**Status:** Accepted

**Context:** mem0 doesn't have a built-in Cohere embedding provider. Options:
1. Custom `EmbeddingBase` subclass (~40 lines)
2. Wrap Cohere in an OpenAI-compatible proxy
3. Skip Cohere support

**Decision:** Custom `EmbeddingBase` subclass registered with `EmbedderFactory`.

**Rationale:**
- Minimal code (~40 lines)
- Uses Cohere SDK v5 `embed()` API with proper `input_type` handling
- Follows mem0's extension pattern (same as ADR-006)
- Supports `search_query` vs `search_document` input types for optimal results

**Consequences:** Must keep Cohere SDK as a dependency. If mem0 adds native Cohere support later, can remove custom code.

---

## ADR-008: OpenLIT for GenAI Span Instrumentation

**Status:** Accepted

**Context:** Need GenAI semantic conventions in OTEL traces. Options:
1. OpenLIT auto-instrumentation
2. Manual span creation
3. Langfuse SDK direct integration

**Decision:** OpenLIT `init()` for automatic GenAI span instrumentation.

**Rationale:**
- Auto-instruments LLM calls, embedding calls, and mem0 operations
- Emits standard `gen_ai.*` namespace spans
- Single line initialization
- Works with any OTEL-compatible backend

**Consequences:** OpenLIT is an additional dependency. Produces deprecation warnings in tests (harmless). OTEL `ConnectionRefusedError` when collector isn't running (expected in unit tests).

---

## ADR-009: Annotated Dependencies Pattern

**Status:** Accepted

**Context:** FastAPI supports two dependency injection patterns:
1. `param = Depends(fn)` — triggers ruff B008 (function call in default argument)
2. `param: Annotated[Type, Depends(fn)]` — clean, no lint warnings

**Decision:** Use `Annotated[Type, Depends(fn)]` everywhere.

**Rationale:**
- Avoids ruff B008 false positives
- More explicit type annotations
- Recommended by FastAPI documentation for modern Python
- Works well with `from __future__ import annotations`

**Consequences:** Slightly more verbose. Requires `from typing import Annotated`.

---

## ADR-010: PYTHONPATH Fix for Docker Image

**Status:** Accepted

**Context:** `uv sync --no-install-project` installs dependencies but not the `maas` package itself. In Docker, `import maas` fails without the package being installed.

**Decision:** Add `ENV PYTHONPATH="/app/src"` to the Dockerfile runtime stage.

**Rationale:**
- Simpler than running `uv pip install -e .` (which would require build tools)
- Makes `import maas` work by adding `src/` to the Python path
- No additional build step needed

**Consequences:** Development and Docker import resolution differ slightly (`uv sync` installs the package locally, Docker uses `PYTHONPATH`). Both work correctly.
