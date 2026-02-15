from __future__ import annotations

from typing import TYPE_CHECKING

from maas.config import EmbeddingProvider, LLMProvider

if TYPE_CHECKING:
    from maas.config import Settings


def _build_azure_kwargs(
    api_key: str,
    deployment: str,
    endpoint: str,
    api_version: str,
) -> dict[str, str]:
    return {
        "api_key": api_key,
        "azure_deployment": deployment,
        "azure_endpoint": endpoint,
        "api_version": api_version,
    }


def build_mem0_config(settings: Settings) -> dict:
    # --- LLM ---
    if settings.llm_provider == LLMProvider.AZURE_OPENAI:
        llm_config: dict[str, object] = {
            "provider": "azure_openai",
            "config": {
                "model": settings.llm_model,
                "temperature": settings.llm_temperature,
                "azure_kwargs": _build_azure_kwargs(
                    api_key=settings.llm_api_key,
                    deployment=settings.llm_model,
                    endpoint=settings.azure_endpoint,
                    api_version=settings.llm_api_version,
                ),
            },
        }
    else:
        llm_config = {
            "provider": "openai",
            "config": {
                "model": settings.llm_model,
                "api_key": settings.llm_api_key,
                "openai_base_url": settings.resolved_llm_base_url,
                "temperature": settings.llm_temperature,
            },
        }

    # --- Embedder ---
    embed_inner: dict[str, object] = {
        "model": settings.embedding_model,
        "embedding_dims": settings.embedding_dims,
    }

    if settings.embedding_provider == EmbeddingProvider.AZURE_OPENAI:
        embed_inner["azure_kwargs"] = _build_azure_kwargs(
            api_key=settings.embedding_api_key,
            deployment=settings.embedding_model,
            endpoint=settings.azure_endpoint,
            api_version=settings.embedding_api_version,
        )
    elif settings.embedding_provider not in {
        EmbeddingProvider.HUGGINGFACE,
        EmbeddingProvider.FASTEMBED,
        EmbeddingProvider.OLLAMA,
    }:
        embed_inner["api_key"] = settings.embedding_api_key

    return {
        "llm": llm_config,
        "embedder": {
            "provider": settings.embedding_provider,
            "config": embed_inner,
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
