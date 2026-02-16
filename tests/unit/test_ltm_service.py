from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from maas.config import EmbeddingProvider, LLMProvider, Settings, VectorIndexType, VectorStoreProvider
from maas.ltm.config import build_mem0_config
from maas.ltm.models import AddMemoryRequest, MemoryCategory, SearchMemoryRequest
from maas.ltm.service import LTMService


@pytest.mark.unit
def test_build_mem0_config_includes_keys() -> None:
    settings = Settings(
        llm_provider=LLMProvider.OPENAI,
        llm_api_key="llm-key",
        llm_model="gpt-test",
        llm_base_url="https://example.com/v1",
        llm_temperature=0.2,
        embedding_provider=EmbeddingProvider.OPENAI,
        embedding_api_key="embed-key",
        embedding_model="embed-model",
        embedding_dims=512,
        mongodb_uri="mongodb://localhost:27017",
        mongodb_db_name="maas",
        mongodb_collection_name="memories",
    )

    config = build_mem0_config(settings)

    assert config["llm"]["provider"] == "openai"
    assert config["llm"]["config"]["model"] == "gpt-test"
    assert config["llm"]["config"]["api_key"] == "llm-key"
    assert config["llm"]["config"]["openai_base_url"] == "https://example.com/v1"
    assert config["llm"]["config"]["temperature"] == 0.2
    assert config["embedder"]["config"]["api_key"] == "embed-key"
    assert config["vector_store"]["config"]["db_name"] == "maas"
    assert config["version"] == "v1.1"


@pytest.mark.unit
def test_build_mem0_config_omits_api_key_for_huggingface() -> None:
    settings = Settings(
        embedding_provider=EmbeddingProvider.HUGGINGFACE,
        embedding_api_key="embed-key",
    )

    config = build_mem0_config(settings)

    assert "api_key" not in config["embedder"]["config"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_memory_includes_category_metadata() -> None:
    memory = AsyncMock()
    memory.add = AsyncMock(return_value={"id": "1"})
    service = LTMService(memory)
    request = AddMemoryRequest(
        messages="hello",
        category=MemoryCategory.SEMANTIC,
        user_id="user-1",
        metadata={"source": "chat"},
    )

    await service.add(request)

    memory.add.assert_awaited_once_with(
        messages="hello",
        user_id="user-1",
        agent_id=None,
        run_id=None,
        metadata={"source": "chat", "category": MemoryCategory.SEMANTIC},
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_memory_builds_filters() -> None:
    memory = AsyncMock()
    memory.search = AsyncMock(return_value={"results": []})
    service = LTMService(memory)
    request = SearchMemoryRequest(
        query="find",
        user_id="user-1",
        categories=[MemoryCategory.SEMANTIC, MemoryCategory.EPISODIC],
        limit=50,
    )

    await service.search(request)

    memory.search.assert_awaited_once_with(
        query="find",
        user_id="user-1",
        agent_id=None,
        run_id=None,
        limit=50,
        filters={"category": {"in": ["semantic", "episodic"]}},
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_update_delete_history_passthrough() -> None:
    memory = AsyncMock()
    memory.get = AsyncMock(return_value={"id": "1"})
    memory.update = AsyncMock(return_value={"id": "1", "memory": "updated"})
    memory.delete = AsyncMock(return_value={"id": "1", "deleted": True})
    memory.history = AsyncMock(return_value=[{"data": "old"}])
    service = LTMService(memory)

    await service.get("1")
    await service.update("1", "new data")
    await service.delete("1")
    await service.history("1")

    memory.get.assert_any_await("1")
    assert memory.get.await_count == 2  # once for get(), once for update() re-fetch
    memory.update.assert_awaited_once_with("1", "new data")
    memory.delete.assert_awaited_once_with("1")
    memory.history.assert_awaited_once_with("1")


@pytest.mark.unit
def test_build_mem0_config_azure_documentdb_provider() -> None:
    settings = Settings(
        llm_api_key="llm-key",
        llm_model="gpt-test",
        llm_base_url="https://example.com/v1",
        embedding_provider=EmbeddingProvider.OPENAI,
        embedding_api_key="embed-key",
        embedding_dims=1536,
        mongodb_uri="mongodb+srv://user:pass@host/?tls=true",
        mongodb_db_name="maas_prod",
        mongodb_collection_name="mem_prod",
        vector_store_provider=VectorStoreProvider.AZURE_DOCUMENTDB,
    )

    config = build_mem0_config(settings)

    assert config["vector_store"]["provider"] == "azure_documentdb"
    assert config["vector_store"]["config"]["mongo_uri"] == "mongodb+srv://user:pass@host/?tls=true"
    assert config["vector_store"]["config"]["db_name"] == "maas_prod"
    assert config["vector_store"]["config"]["collection_name"] == "mem_prod"
    assert config["vector_store"]["config"]["embedding_model_dims"] == 1536


@pytest.mark.unit
def test_build_mem0_config_azure_openai_provider() -> None:
    settings = Settings(
        llm_provider=LLMProvider.AZURE_OPENAI,
        llm_api_key="azure-llm-key",
        llm_model="gpt-4o",
        azure_endpoint="https://my-resource.openai.azure.com",
        llm_api_version="2024-10-21",
        embedding_provider=EmbeddingProvider.AZURE_OPENAI,
        embedding_api_key="azure-embed-key",
        embedding_model="text-embedding-3-small",
        embedding_api_version="2024-10-21",
        embedding_dims=1536,
        mongodb_uri="mongodb://localhost:27017",
    )

    config = build_mem0_config(settings)

    assert config["llm"]["provider"] == "azure_openai"
    assert config["llm"]["config"]["model"] == "gpt-4o"
    assert config["llm"]["config"]["azure_kwargs"]["api_key"] == "azure-llm-key"
    assert config["llm"]["config"]["azure_kwargs"]["azure_deployment"] == "gpt-4o"
    assert config["llm"]["config"]["azure_kwargs"]["azure_endpoint"] == "https://my-resource.openai.azure.com"
    assert config["llm"]["config"]["azure_kwargs"]["api_version"] == "2024-10-21"
    assert "api_key" not in config["llm"]["config"]
    assert "openai_base_url" not in config["llm"]["config"]

    assert config["embedder"]["provider"] == "azure_openai"
    assert config["embedder"]["config"]["azure_kwargs"]["api_key"] == "azure-embed-key"
    assert config["embedder"]["config"]["azure_kwargs"]["azure_deployment"] == "text-embedding-3-small"
    assert config["embedder"]["config"]["azure_kwargs"]["azure_endpoint"] == "https://my-resource.openai.azure.com"
    assert "api_key" not in config["embedder"]["config"]


@pytest.mark.unit
def test_build_mem0_config_includes_index_type() -> None:
    settings = Settings(
        llm_api_key="test-key",
        embedding_api_key="test-key",
        vector_index_type=VectorIndexType.HNSW,
    )

    config = build_mem0_config(settings)

    assert "index_type" in config["vector_store"]["config"]
    assert config["vector_store"]["config"]["index_type"] == "hnsw"
