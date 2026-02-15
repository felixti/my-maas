from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from maas.config import Settings
from maas.dependencies import lifespan_resources
from maas.main import create_app


@pytest.fixture
def app():
    prior_redis = lifespan_resources.redis
    prior_llm = lifespan_resources.llm_client
    prior_settings = lifespan_resources.settings
    lifespan_resources.redis = AsyncMock()
    lifespan_resources.redis.get = AsyncMock(return_value=None)
    lifespan_resources.redis.zrange = AsyncMock(return_value=[])
    lifespan_resources.llm_client = AsyncMock()
    lifespan_resources.settings = Settings()
    try:
        yield create_app()
    finally:
        lifespan_resources.redis = prior_redis
        lifespan_resources.llm_client = prior_llm
        lifespan_resources.settings = prior_settings


@pytest.fixture
async def client(app) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
