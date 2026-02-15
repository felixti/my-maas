from __future__ import annotations

from typing import TYPE_CHECKING

from maas.config import EmbeddingProvider

if TYPE_CHECKING:
    from maas.config import Settings


def build_mem0_config(settings: Settings) -> dict:
    embed_config: dict[str, object] = {
        "model": settings.embedding_model,
        "embedding_dims": settings.embedding_dims,
    }
    if settings.embedding_provider not in {
        EmbeddingProvider.HUGGINGFACE,
        EmbeddingProvider.FASTEMBED,
        EmbeddingProvider.OLLAMA,
    }:
        embed_config["api_key"] = settings.embedding_api_key

    return {
        "llm": {
            "provider": "openai",
            "config": {
                "model": settings.llm_model,
                "api_key": settings.llm_api_key,
                "openai_base_url": settings.resolved_llm_base_url,
                "temperature": settings.llm_temperature,
            },
        },
        "embedder": {
            "provider": settings.embedding_provider,
            "config": embed_config,
        },
        "vector_store": {
            "provider": settings.vector_store_provider,
            "config": {
                "mongo_uri": settings.mongodb_uri,
                "db_name": settings.mongodb_db_name,
                "collection_name": settings.mongodb_collection_name,
                "embedding_model_dims": settings.embedding_dims,
            },
        },
        "version": "v1.1",
    }
