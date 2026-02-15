# MaaS — Project Overview

## What Is This?

**Memory as a Service (MaaS)** is a FastAPI microservice that provides both **Short-Term Memory (STM)** and **Long-Term Memory (LTM)** for AI agents. It is designed to be the memory backend for any AI system that needs session-scoped working memory and persistent semantic recall.

## Problem Statement

AI agents need memory that persists across interactions. Current approaches either bake memory into the agent framework (non-portable) or rely on ad-hoc solutions (fragile). MaaS provides a dedicated, API-driven memory layer that any agent can consume via HTTP.

## Core Capabilities

| Capability | Implementation |
|---|---|
| **Short-Term Memory** | Redis-backed session message buffers with sliding window and token-threshold summarization |
| **Long-Term Memory** | mem0 `AsyncMemory` with MongoDB vector store — semantic, episodic, fact, and preference categories |
| **LLM Gateway** | OpenAI Chat Completions API protocol — works with any compatible provider |
| **Embedding Gateway** | Configurable providers: OpenAI, Azure OpenAI, Cohere, HuggingFace, FastEmbed, Ollama |
| **Observability** | OpenTelemetry → OTEL Collector → Langfuse with GenAI span semantics via OpenLIT |
| **Containerization** | Multi-stage Dockerfile + Docker Compose (7 services) for shift-left testing |

## Build Phases Completed

| Phase | Scope | Status |
|---|---|---|
| **0** | Project scaffold, Dockerfile, Docker Compose, OTEL config | ✅ Complete |
| **1** | LLM gateway, config system, provider registry, lifespan deps | ✅ Complete |
| **2** | STM service — Redis store, strategies, 5-endpoint router | ✅ Complete |
| **3** | LTM service — mem0 wrapper, 7-endpoint router | ✅ Complete |
| **4** | Cohere embedding — custom `EmbeddingBase` subclass for mem0 | ✅ Complete |
| **5** | Observability — OTEL tracing, FastAPI + OpenLIT instrumentation | ✅ Complete |
| **6** | Lint sweep — ruff check + format across all files | ✅ Complete |
| **7** | Unit tests — 41 tests (later expanded to 62) | ✅ Complete |
| **8** | Docker Compose smoke test — end-to-end in containers | ✅ Complete |
| **9** | Azure DocumentDB vector store adapter — custom `VectorStoreBase` subclass | ✅ Complete |

## Key Metrics

| Metric | Value |
|---|---|
| Source files | 18 Python modules across 6 packages |
| Test files | 9 test modules |
| Total tests | 62 (all passing) |
| API endpoints | 13 (1 health + 5 STM + 7 LTM) |
| Docker services | 7 (maas, redis, mongodb, langfuse, langfuse-db, langfuse-redis, otel-collector) |
| Ruff rules | E, W, F, I, N, UP, B, A, C4, SIM, TCH, RUF, S, DTZ, PT, RET, ARG |

## Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Framework | FastAPI + AsyncIO |
| STM Backend | Redis 7 (sorted sets) |
| LTM Engine | mem0 v1.0.3 (AsyncMemory) |
| LTM Backend (dev) | MongoDB Atlas Local |
| LTM Backend (prod) | Azure Cosmos DB for MongoDB (DocumentDB) |
| LLM Protocol | OpenAI Chat Completions API |
| Observability | OpenTelemetry + Langfuse + OpenLIT |
| Package Manager | uv |
| Linter/Formatter | Ruff |
| Test Framework | pytest + pytest-asyncio |
| Container | Docker multi-stage build |

## Architecture Decision Summary

| Decision | Choice | Rationale |
|---|---|---|
| Python version | 3.12 (not 3.14) | mem0 only tested up to 3.12 |
| STM design | Pure message buffer, no mem0 | STM is a session cache, not semantic memory |
| LTM sub-types | Metadata categories, single mem0 instance | Simpler than multiple instances, same vector space |
| LLM gateway | OpenAI client + configurable `base_url` | User requirement: "always OpenAI Chat Completions API" |
| Vector store (dev) | MongoDB Atlas Local | Full Atlas API for development |
| Vector store (prod) | Custom `VectorStoreBase` subclass | DocumentDB uses different vector search API |
| Cohere embeddings | Custom `EmbeddingBase` subclass | Not built into mem0, ~40 lines |

## Repository Structure

```
my-maas/
├── ai_docs/              # Project documentation (this folder)
├── otel/                 # OTEL collector config
├── src/maas/             # Application source
│   ├── llm/              # LLM gateway + embeddings
│   ├── stm/              # Short-Term Memory service
│   ├── ltm/              # Long-Term Memory service
│   ├── vector_stores/    # Custom vector store adapters
│   └── observability/    # Tracing + instrumentation
├── tests/                # Test suite
│   ├── unit/             # 62 unit tests
│   └── integration/      # (placeholder for future integration tests)
├── Dockerfile            # Multi-stage container build
├── docker-compose.yml    # Full development stack
├── pyproject.toml        # Project config (deps, ruff, pytest)
└── .env.example          # All configuration variables
```
