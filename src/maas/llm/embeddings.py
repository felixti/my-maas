"""Custom embedding implementations for mem0 compatibility."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal

import cohere
from mem0.embeddings.base import EmbeddingBase

if TYPE_CHECKING:
    from mem0.configs.embeddings.base import BaseEmbedderConfig


class CohereEmbedding(EmbeddingBase):
    """Cohere embedding implementation for mem0.

    Compatible with Cohere SDK v5+ embed v2 API.
    """

    def __init__(self, config: BaseEmbedderConfig | None = None):
        super().__init__(config)

        self.config.model = self.config.model or "embed-english-v3.0"
        self.config.embedding_dims = self.config.embedding_dims or 1024

        api_key = self.config.api_key or os.getenv("COHERE_API_KEY")
        if not api_key:
            raise ValueError("Cohere API key must be provided via config or COHERE_API_KEY environment variable")

        self.client = cohere.Client(api_key=api_key)
        self.model = self.config.model

    def embed(self, text: str, memory_action: Literal["add", "search", "update"] | None = None) -> list:
        """Get the embedding for the given text using Cohere."""
        input_type = "search_query" if memory_action == "search" else "search_document"
        text = text.replace("\n", " ")
        response = self.client.embed(texts=[text], model=self.model, input_type=input_type, embedding_types=["float"])
        return response.embeddings.float_[0]


def register_cohere_embedder() -> None:
    """Register CohereEmbedding with mem0's EmbedderFactory.

    Must be called before creating any mem0 Memory instances that use
    the Cohere embedding provider.
    """
    from mem0.utils.factory import EmbedderFactory

    EmbedderFactory.provider_to_class["cohere"] = "maas.llm.embeddings.CohereEmbedding"
