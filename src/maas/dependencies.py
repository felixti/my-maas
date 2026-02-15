from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import redis.asyncio as aioredis

from maas.config import get_settings
from maas.llm.embeddings import register_cohere_embedder
from maas.llm.gateway import create_llm_client
from maas.vector_stores.documentdb import register_documentdb_vector_store

if TYPE_CHECKING:
    from openai import AsyncOpenAI

    from maas.config import Settings


@dataclass
class LifespanResources:
    settings: Settings = field(default_factory=get_settings)
    redis: aioredis.Redis | None = None
    llm_client: AsyncOpenAI | None = None

    async def startup(self) -> None:
        # Register custom providers with mem0 before creating any Memory instances
        register_cohere_embedder()
        register_documentdb_vector_store()

        self.settings = get_settings()
        self.redis = aioredis.from_url(self.settings.redis_url, decode_responses=True)
        self.llm_client = create_llm_client(self.settings)

    async def shutdown(self) -> None:
        if self.redis:
            await self.redis.aclose()


lifespan_resources = LifespanResources()
