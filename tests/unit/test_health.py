from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from fastapi import FastAPI
    from httpx import AsyncClient


@pytest.mark.unit
async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.unit
async def test_stm_context_stub(client: AsyncClient) -> None:
    """Test STM context endpoint with mocked dependencies."""
    from maas.dependencies import lifespan_resources

    # Mock Redis
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None  # No session config
    stored_message = {
        "id": "msg-1",
        "role": "user",
        "content": "Test",
        "timestamp": 1000.0,
        "token_count": 2,
    }
    mock_redis.zrange.return_value = [json.dumps(stored_message)]

    # Mock LLM client
    mock_llm = MagicMock()

    # Set lifespan resources
    lifespan_resources.redis = mock_redis
    lifespan_resources.llm_client = mock_llm

    response = await client.get("/stm/test-session/context")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "test-session"


@pytest.mark.unit
async def test_ltm_search_stub(app: FastAPI, client: AsyncClient) -> None:
    """Test LTM search endpoint with mocked service."""
    from maas.ltm.router import get_ltm_service

    # Mock LTM service
    mock_service = AsyncMock()
    mock_service.search.return_value = {
        "results": [
            {
                "id": "mem-1",
                "memory": "Test memory",
                "score": 0.95,
            }
        ]
    }

    # Override dependency
    app.dependency_overrides[get_ltm_service] = lambda: mock_service

    request_data = {
        "query": "test",
        "user_id": "user-1",
    }
    response = await client.post("/ltm/memories/search", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert "results" in data

    # Cleanup
    app.dependency_overrides.clear()
