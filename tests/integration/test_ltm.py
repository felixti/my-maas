from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

if TYPE_CHECKING:
    from fastapi import FastAPI
    from httpx import AsyncClient


@pytest.fixture
def mock_ltm_service() -> AsyncMock:
    mock = AsyncMock()
    mock.add.return_value = {
        "id": "mem-123",
        "memory": "Test memory",
        "metadata": {"category": "semantic"},
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    mock.search.return_value = {
        "results": [
            {
                "id": "mem-123",
                "memory": "Test memory",
                "metadata": {"category": "semantic"},
                "score": 0.95,
            }
        ]
    }
    mock.get_all.return_value = {
        "results": [
            {
                "id": "mem-123",
                "memory": "Test memory",
                "metadata": {"category": "semantic"},
            }
        ]
    }
    mock.get.return_value = {
        "id": "mem-123",
        "memory": "Test memory",
        "metadata": {"category": "semantic"},
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    mock.update.return_value = {
        "id": "mem-123",
        "memory": "Updated memory",
        "metadata": {"category": "semantic"},
        "updated_at": "2024-01-02T00:00:00Z",
    }
    mock.delete.return_value = {"message": "Memory deleted successfully"}
    mock.history.return_value = [
        {
            "id": "hist-1",
            "prev_value": "Old",
            "new_value": "New",
            "event": "UPDATE",
            "timestamp": "2024-01-02T00:00:00Z",
        }
    ]
    return mock


@pytest.mark.integration
async def test_add_memory(
    integration_app: FastAPI,
    integration_client: AsyncClient,
    mock_ltm_service: AsyncMock,
) -> None:
    from maas.ltm.router import get_ltm_service

    integration_app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service

    request_data = {
        "messages": "Remember this important fact",
        "category": "fact",
        "user_id": "user-123",
        "metadata": {"source": "conversation"},
    }

    try:
        response = await integration_client.post("/ltm/memories", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "mem-123"
        assert data["memory"] == "Test memory"
        mock_ltm_service.add.assert_called_once()
    finally:
        integration_app.dependency_overrides.clear()


@pytest.mark.integration
async def test_add_memory_missing_scope(
    integration_app: FastAPI,
    integration_client: AsyncClient,
    mock_ltm_service: AsyncMock,
) -> None:
    from maas.ltm.router import get_ltm_service

    integration_app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service

    request_data = {
        "messages": "Remember this",
        "category": "fact",
    }

    try:
        response = await integration_client.post("/ltm/memories", json=request_data)
        assert response.status_code == 422
        mock_ltm_service.add.assert_not_called()
    finally:
        integration_app.dependency_overrides.clear()


@pytest.mark.integration
async def test_search_memories(
    integration_app: FastAPI,
    integration_client: AsyncClient,
    mock_ltm_service: AsyncMock,
) -> None:
    from maas.ltm.router import get_ltm_service

    integration_app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service

    request_data = {
        "query": "important fact",
        "user_id": "user-123",
        "categories": ["fact", "semantic"],
        "limit": 10,
    }

    try:
        response = await integration_client.post("/ltm/memories/search", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["id"] == "mem-123"
        mock_ltm_service.search.assert_called_once()
    finally:
        integration_app.dependency_overrides.clear()


@pytest.mark.integration
async def test_list_memories(
    integration_app: FastAPI,
    integration_client: AsyncClient,
    mock_ltm_service: AsyncMock,
) -> None:
    from maas.ltm.router import get_ltm_service

    integration_app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service

    try:
        response = await integration_client.get("/ltm/memories?user_id=user-123&limit=50")
        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["id"] == "mem-123"
        mock_ltm_service.get_all.assert_called_once_with(
            user_id="user-123",
            agent_id=None,
            session_id=None,
            limit=50,
        )
    finally:
        integration_app.dependency_overrides.clear()


@pytest.mark.integration
async def test_get_memory(
    integration_app: FastAPI,
    integration_client: AsyncClient,
    mock_ltm_service: AsyncMock,
) -> None:
    from maas.ltm.router import get_ltm_service

    integration_app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service
    memory_id = "mem-123"

    try:
        response = await integration_client.get(f"/ltm/memories/{memory_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == memory_id
        mock_ltm_service.get.assert_called_once_with(memory_id)
    finally:
        integration_app.dependency_overrides.clear()


@pytest.mark.integration
async def test_update_memory(
    integration_app: FastAPI,
    integration_client: AsyncClient,
    mock_ltm_service: AsyncMock,
) -> None:
    from maas.ltm.router import get_ltm_service

    integration_app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service
    memory_id = "mem-123"
    request_data = {"data": "Updated memory content"}

    try:
        response = await integration_client.put(f"/ltm/memories/{memory_id}", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == memory_id
        mock_ltm_service.update.assert_called_once_with(memory_id, "Updated memory content")
    finally:
        integration_app.dependency_overrides.clear()


@pytest.mark.integration
async def test_delete_memory(
    integration_app: FastAPI,
    integration_client: AsyncClient,
    mock_ltm_service: AsyncMock,
) -> None:
    from maas.ltm.router import get_ltm_service

    integration_app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service
    memory_id = "mem-123"

    try:
        response = await integration_client.delete(f"/ltm/memories/{memory_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Memory deleted successfully"
        mock_ltm_service.delete.assert_called_once_with(memory_id)
    finally:
        integration_app.dependency_overrides.clear()


@pytest.mark.integration
async def test_get_memory_history(
    integration_app: FastAPI,
    integration_client: AsyncClient,
    mock_ltm_service: AsyncMock,
) -> None:
    from maas.ltm.router import get_ltm_service

    integration_app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service
    memory_id = "mem-123"

    try:
        response = await integration_client.get(f"/ltm/memories/{memory_id}/history")
        assert response.status_code == 200
        data = response.json()
        assert data["entries"][0]["event"] == "UPDATE"
        mock_ltm_service.history.assert_called_once_with(memory_id)
    finally:
        integration_app.dependency_overrides.clear()
