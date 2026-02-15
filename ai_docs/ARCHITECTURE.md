# MaaS — Architecture Document

## System Context

```mermaid
graph LR
    Agent["AI Agent / Client"] -->|HTTP REST| MaaS["MaaS<br/>(FastAPI)"]
    MaaS -->|Redis Protocol| Redis["Redis 7"]
    MaaS -->|MongoDB Wire Protocol| MongoDB["MongoDB Atlas Local<br/>or Azure DocumentDB"]
    MaaS -->|OpenAI API| LLM["LLM Provider<br/>(OpenAI, Grok, etc.)"]
    MaaS -->|Embedding API| Embedder["Embedding Provider<br/>(OpenAI, Cohere, etc.)"]
    MaaS -->|OTLP HTTP| Collector["OTEL Collector"]
    Collector -->|HTTP| Langfuse["Langfuse"]
```

## High-Level Architecture

```mermaid
graph TB
    subgraph "FastAPI Application"
        Main["main.py<br/>Lifespan + Routers"]
        Config["config.py<br/>Settings + Enums"]
        Deps["dependencies.py<br/>LifespanResources"]

        subgraph "STM Module"
            STM_Router["stm/router.py<br/>5 endpoints"]
            STM_Store["stm/store.py<br/>MessageStore (Redis)"]
            STM_Strat["stm/strategies.py<br/>WindowStrategy ABC"]
            STM_Models["stm/models.py"]
        end

        subgraph "LTM Module"
            LTM_Router["ltm/router.py<br/>7 endpoints"]
            LTM_Service["ltm/service.py<br/>LTMService"]
            LTM_Config["ltm/config.py<br/>build_mem0_config()"]
            LTM_Models["ltm/models.py"]
        end

        subgraph "LLM Module"
            Gateway["llm/gateway.py<br/>AsyncOpenAI factory"]
            Embeddings["llm/embeddings.py<br/>CohereEmbedding"]
        end

        subgraph "Vector Stores"
            DocDB["vector_stores/documentdb.py<br/>AzureDocumentDB"]
        end

        subgraph "Observability"
            Tracing["observability/tracing.py<br/>TracerProvider"]
            Middleware["observability/middleware.py<br/>FastAPI + OpenLIT"]
        end
    end

    Main --> STM_Router
    Main --> LTM_Router
    Main --> Deps
    Main --> Config
    STM_Router --> STM_Store
    STM_Router --> STM_Strat
    STM_Strat --> STM_Store
    LTM_Router --> LTM_Service
    LTM_Service --> LTM_Config
    LTM_Config --> Config
    Deps --> Gateway
    DocDB -.->|registered in| LTM_Config
```

## Component Details

### 1. Configuration Layer (`config.py`)

Central pydantic-settings configuration loaded from `.env` files.

```
┌─────────────────────────────────────────────────┐
│                    Settings                      │
├─────────────────────────────────────────────────┤
│ LLM:        provider, api_key, model, base_url  │
│ Embedding:  provider, api_key, model, dims      │
│ STM:        redis_url, strategy, max_messages    │
│ LTM:        mongodb_uri, db_name, collection     │
│ OTEL:       endpoint, service_name, langfuse     │
│ Vector:     vector_store_provider                │
├─────────────────────────────────────────────────┤
│ Enums: LLMProvider, EmbeddingProvider,           │
│        STMStrategy, VectorStoreProvider           │
├─────────────────────────────────────────────────┤
│ PROVIDER_BASE_URLS: dict[LLMProvider, str]       │
│ resolved_llm_base_url: property                  │
│ resolved_stm_summarization_model: property       │
└─────────────────────────────────────────────────┘
```

### 2. Short-Term Memory (STM)

```mermaid
sequenceDiagram
    participant Client
    participant Router as STM Router
    participant Store as MessageStore
    participant Redis
    participant LLM as LLM Provider

    Note over Client,Redis: Adding Messages
    Client->>Router: POST /stm/{session}/messages
    Router->>Store: append_messages()
    Store->>Redis: ZADD (sorted set, score=timestamp)
    Redis-->>Store: OK
    Store-->>Router: StoredMessage[]
    Router-->>Client: {added: N, messages: [...]}

    Note over Client,LLM: Getting Context (Token Threshold)
    Client->>Router: GET /stm/{session}/context
    Router->>Store: get_messages()
    Store->>Redis: ZRANGE
    Redis-->>Store: all messages
    alt total_tokens > threshold
        Store->>LLM: Summarize older 60% of messages
        LLM-->>Store: summary text
        Store->>Redis: DELETE + ZADD (summary + recent)
    end
    Store-->>Router: ContextResponse
    Router-->>Client: {messages, strategy, total_tokens}
```

**Data Model:**

```
Redis Key: stm:session:{session_id}:messages
Type: Sorted Set
Score: Unix timestamp (float)
Member: JSON-serialized StoredMessage

StoredMessage:
├── id: UUID
├── role: user | assistant | system | summary
├── content: str
├── metadata: dict | null
├── timestamp: float
└── token_count: int
```

**Strategies:**

```
┌──────────────────────────┐     ┌──────────────────────────┐
│   SlidingWindowStrategy  │     │  TokenThresholdStrategy  │
├──────────────────────────┤     ├──────────────────────────┤
│ Keep last N messages     │     │ If tokens > threshold:   │
│ (STM_MAX_MESSAGES)       │     │   Split at 60%           │
│                          │     │   Summarize older portion│
│ No LLM calls             │     │   via LLM                │
│ O(1) Redis operation     │     │   Replace in Redis       │
└──────────────────────────┘     └──────────────────────────┘
```

### 3. Long-Term Memory (LTM)

```mermaid
sequenceDiagram
    participant Client
    participant Router as LTM Router
    participant Service as LTMService
    participant Mem0 as mem0 AsyncMemory
    participant Embedder as Embedding Provider
    participant VectorDB as MongoDB / DocumentDB

    Note over Client,VectorDB: Adding a Memory
    Client->>Router: POST /ltm/memories {messages, category, user_id}
    Router->>Service: add(request)
    Service->>Mem0: memory.add(messages, metadata={category})
    Mem0->>Embedder: embed(text)
    Embedder-->>Mem0: vector[1536]
    Mem0->>VectorDB: insert(vector, payload)
    VectorDB-->>Mem0: OK
    Mem0-->>Service: result
    Service-->>Router: MemoryResponse
    Router-->>Client: {id, memory, metadata}

    Note over Client,VectorDB: Searching Memories
    Client->>Router: POST /ltm/memories/search {query, categories}
    Router->>Service: search(request)
    Service->>Mem0: memory.search(query, filters={category: {in: [...]}})
    Mem0->>Embedder: embed(query)
    Embedder-->>Mem0: query_vector[1536]
    Mem0->>VectorDB: vector_search(query_vector, filters)
    VectorDB-->>Mem0: scored results
    Mem0-->>Service: results
    Service-->>Router: MemoryListResponse
    Router-->>Client: {results: [...]}
```

**Memory Categories (metadata-level differentiation):**

```
┌─────────────┬────────────────────────────────────────────────────────┐
│ Category    │ Purpose                                                │
├─────────────┼────────────────────────────────────────────────────────┤
│ semantic    │ General knowledge and concepts                         │
│ episodic    │ Specific events and interactions                       │
│ fact        │ Verified factual information                           │
│ preference  │ User preferences and settings                          │
└─────────────┴────────────────────────────────────────────────────────┘

All categories share a single vector space in one MongoDB collection.
Filtering happens via metadata payload in mem0's search API.
```

### 4. LLM Gateway

```mermaid
graph LR
    subgraph "Provider Registry"
        PR["PROVIDER_BASE_URLS<br/>dict[LLMProvider, str]"]
    end

    subgraph "Gateway"
        GW["create_llm_client(settings)<br/>→ AsyncOpenAI"]
    end

    GW --> OpenAI["OpenAI<br/>api.openai.com/v1"]
    GW --> Grok["Grok<br/>api.x.ai/v1"]
    GW --> Anthropic["Anthropic<br/>api.anthropic.com/v1"]
    GW --> OpenRouter["OpenRouter<br/>openrouter.ai/api/v1"]
    GW --> Others["Kimi, GLM, Minimax,<br/>Together, DeepSeek"]
    GW --> Custom["Custom<br/>LLM_BASE_URL"]

    PR --> GW
```

All providers use the **OpenAI Chat Completions API** protocol. The gateway creates a single `AsyncOpenAI` client with the resolved `base_url` for the configured provider.

### 5. Vector Store Architecture

```mermaid
graph TB
    subgraph "mem0 Framework"
        Factory["VectorStoreFactory<br/>provider_to_class dict"]
        Base["VectorStoreBase (ABC)<br/>11 abstract methods"]
    end

    subgraph "Built-in (mem0)"
        Atlas["MongoDB (Atlas)<br/>$vectorSearch API"]
    end

    subgraph "Custom (MaaS)"
        DocDB["AzureDocumentDB<br/>cosmosSearch API"]
    end

    Factory -->|"mongodb"| Atlas
    Factory -->|"azure_documentdb"| DocDB
    Atlas --> Base
    DocDB --> Base

    subgraph "Config Switch"
        ENV["VECTOR_STORE_PROVIDER="]
        ENV -->|"mongodb"| Atlas
        ENV -->|"azure_documentdb"| DocDB
    end
```

**Atlas vs DocumentDB API Mapping:**

```
┌──────────────────────┬───────────────────────────┬─────────────────────────────┐
│ Operation            │ Atlas (mongodb)            │ DocumentDB (azure_documentdb)│
├──────────────────────┼───────────────────────────┼─────────────────────────────┤
│ Index creation       │ SearchIndexModel +         │ db.command("createIndexes") │
│                      │ create_search_index()      │ with cosmosSearch key type  │
├──────────────────────┼───────────────────────────┼─────────────────────────────┤
│ Index listing        │ list_search_indexes()      │ db.command("listIndexes")   │
├──────────────────────┼───────────────────────────┼─────────────────────────────┤
│ Vector search        │ $vectorSearch stage        │ $search + cosmosSearch      │
├──────────────────────┼───────────────────────────┼─────────────────────────────┤
│ Score metadata       │ $meta: "vectorSearchScore" │ $meta: "searchScore"        │
├──────────────────────┼───────────────────────────┼─────────────────────────────┤
│ CRUD (insert, etc.)  │ Standard pymongo           │ Standard pymongo (same)     │
└──────────────────────┴───────────────────────────┴─────────────────────────────┘
```

### 6. Observability Pipeline

```mermaid
graph LR
    subgraph "MaaS Application"
        FastAPI["FastAPI<br/>(instrumented)"]
        OpenLIT["OpenLIT<br/>GenAI spans"]
        OTEL_SDK["OTEL SDK<br/>TracerProvider"]
    end

    subgraph "Collection"
        Collector["OTEL Collector<br/>(contrib)"]
    end

    subgraph "Visualization"
        Langfuse["Langfuse<br/>UI :3000"]
        LF_DB["PostgreSQL"]
        LF_Redis["Redis"]
    end

    FastAPI --> OTEL_SDK
    OpenLIT --> OTEL_SDK
    OTEL_SDK -->|"OTLP HTTP<br/>:4318"| Collector
    Collector -->|"HTTP"| Langfuse
    Langfuse --> LF_DB
    Langfuse --> LF_Redis
```

**Span Types:**

```
┌─────────────────────────────────────────────┐
│ HTTP Spans (FastAPIInstrumentor)             │
│  └─ gen_ai.* spans (OpenLIT)                │
│     ├─ LLM completion calls                 │
│     ├─ Embedding calls                      │
│     └─ mem0 operations                      │
└─────────────────────────────────────────────┘
```

### 7. Container Architecture

```mermaid
graph TB
    subgraph "Docker Compose Stack"
        subgraph "Application"
            MaaS["maas:dev<br/>:8000<br/>Python 3.12 + FastAPI"]
        end

        subgraph "Data Layer"
            Redis["redis:7-alpine<br/>:6379<br/>STM Store"]
            MongoDB["mongodb-atlas-local<br/>:27017<br/>LTM Vector Store"]
        end

        subgraph "Observability"
            Collector["otel-collector-contrib<br/>:4317/:4318<br/>Trace Pipeline"]
            Langfuse["langfuse:latest<br/>:3000<br/>Trace UI"]
            LF_DB["postgres:16-alpine<br/>Langfuse DB"]
            LF_Redis["redis:7-alpine<br/>Langfuse Cache"]
        end
    end

    MaaS -->|"REDIS_URL"| Redis
    MaaS -->|"MONGODB_URI"| MongoDB
    MaaS -->|"OTLP HTTP"| Collector
    Collector --> Langfuse
    Langfuse --> LF_DB
    Langfuse --> LF_Redis
```

**Dockerfile Build Stages:**

```
┌──────────────────────────────────────────────┐
│ Stage 1: base                                │
│  python:3.12-slim + uv binary               │
├──────────────────────────────────────────────┤
│ Stage 2: deps                                │
│  COPY pyproject.toml + uv.lock              │
│  RUN uv sync --frozen --no-dev              │
│  (135 packages installed)                    │
├──────────────────────────────────────────────┤
│ Stage 3: runtime                             │
│  COPY .venv from deps stage                 │
│  COPY src/ into /app/src/                   │
│  ENV PYTHONPATH="/app/src"                   │
│  CMD uvicorn maas.main:app                  │
└──────────────────────────────────────────────┘
```

## Data Flow Summary

```
                    ┌─────────────┐
                    │  AI Agent   │
                    └──────┬──────┘
                           │ HTTP
                    ┌──────▼──────┐
                    │   FastAPI   │
                    │   (main)    │
                    └──┬──────┬───┘
                       │      │
              ┌────────▼─┐  ┌─▼────────┐
              │   STM    │  │   LTM    │
              │  Router  │  │  Router  │
              └────┬─────┘  └────┬─────┘
                   │             │
              ┌────▼─────┐  ┌───▼──────┐
              │ Message  │  │  LTM     │
              │  Store   │  │ Service  │
              └────┬─────┘  └───┬──────┘
                   │            │
              ┌────▼─────┐  ┌──▼───────┐
              │  Redis   │  │   mem0   │
              │ (sorted  │  │ Async    │
              │  sets)   │  │ Memory   │
              └──────────┘  └──┬───┬───┘
                               │   │
                    ┌──────────▼┐ ┌▼──────────┐
                    │ Embedder  │ │ Vector    │
                    │ (OpenAI,  │ │ Store     │
                    │  Cohere)  │ │ (MongoDB/ │
                    └───────────┘ │ DocumentDB│
                                  └───────────┘
```

## Security Considerations

- All API keys stored in `.env` (gitignored), never in source code
- Docker Compose overrides connection URLs for container networking
- Azure DocumentDB requires TLS + SCRAM-SHA-256 authentication
- No authentication on the MaaS API itself (assumed to run behind a gateway/mesh)
- Langfuse secrets configured via environment variables
