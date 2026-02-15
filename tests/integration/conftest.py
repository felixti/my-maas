from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient
from testcontainers.mongodb import MongoDbContainer
from testcontainers.redis import RedisContainer

from maas.config import Settings
from maas.dependencies import lifespan_resources
from maas.main import create_app

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture(scope="session")
def mongodb_container() -> Iterator[MongoDbContainer]:
    with MongoDbContainer("mongo:7") as container:
        yield container


@pytest.fixture(scope="session")
def redis_url(redis_container: RedisContainer) -> str:
    return f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"


@pytest.fixture(scope="session")
def mongodb_url(mongodb_container: MongoDbContainer) -> str:
    return mongodb_container.get_connection_url()


@pytest.fixture
async def integration_app(redis_url: str, mongodb_url: str):
    from maas.ltm import router as ltm_router

    prior_redis = lifespan_resources.redis
    prior_llm = lifespan_resources.llm_client
    prior_settings = lifespan_resources.settings
    ltm_router._ltm_service = None
    redis = aioredis.from_url(redis_url, decode_responses=True)
    lifespan_resources.redis = redis
    lifespan_resources.llm_client = MagicMock(spec=AsyncMock)
    lifespan_resources.settings = Settings(redis_url=redis_url, mongodb_uri=mongodb_url)
    try:
        app = create_app()
        await asyncio.sleep(0)
        yield app
    finally:
        await redis.aclose()
        lifespan_resources.redis = prior_redis
        lifespan_resources.llm_client = prior_llm
        lifespan_resources.settings = prior_settings
        ltm_router._ltm_service = None


@pytest.fixture
async def integration_client(integration_app) -> AsyncClient:
    transport = ASGITransport(app=integration_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
