from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from maas.ltm.models import MemoryCategory

if TYPE_CHECKING:
    from fastapi import FastAPI
    from httpx import AsyncClient


@pytest.fixture
def mock_ltm_service():
    """Fixture providing a mocked LTMService."""
    mock = AsyncMock()

    # Set default return values for common operations
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
            "prev_value": "Old memory",
            "new_value": "Updated memory",
            "event": "UPDATE",
            "timestamp": "2024-01-02T00:00:00Z",
        }
    ]

    return mock


@pytest.mark.unit
async def test_add_memory(app: FastAPI, client: AsyncClient, mock_ltm_service: AsyncMock) -> None:
    """Test POST /ltm/memories endpoint."""
    from maas.ltm.router import get_ltm_service

    app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service

    request_data = {
        "messages": "Remember this important fact",
        "category": "fact",
        "user_id": "user-123",
        "metadata": {"source": "conversation"},
    }

    response = await client.post("/ltm/memories", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["memory"] == "Test memory"

    # Verify service was called
    mock_ltm_service.add.assert_called_once()
    call_args = mock_ltm_service.add.call_args[0][0]
    assert call_args.messages == "Remember this important fact"
    assert call_args.category == MemoryCategory.FACT
    assert call_args.user_id == "user-123"

    # Cleanup
    app.dependency_overrides.clear()


@pytest.mark.unit
async def test_add_memory_missing_scope(app: FastAPI, client: AsyncClient, mock_ltm_service: AsyncMock) -> None:
    """Test POST /ltm/memories without required scope fields returns 422."""
    from maas.ltm.router import get_ltm_service

    app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service

    request_data = {
        "messages": "Remember this",
        "category": "fact",
        # Missing user_id, agent_id, and session_id
    }

    response = await client.post("/ltm/memories", json=request_data)

    assert response.status_code == 422

    # Service should not be called
    mock_ltm_service.add.assert_not_called()

    app.dependency_overrides.clear()


@pytest.mark.unit
async def test_search_memories(app: FastAPI, client: AsyncClient, mock_ltm_service: AsyncMock) -> None:
    """Test POST /ltm/memories/search endpoint."""
    from maas.ltm.router import get_ltm_service

    app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service

    request_data = {
        "query": "important fact",
        "user_id": "user-123",
        "categories": ["fact", "semantic"],
        "limit": 10,
    }

    response = await client.post("/ltm/memories/search", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert len(data["results"]) == 1
    assert data["results"][0]["id"] == "mem-123"
    assert "score" in data["results"][0]

    # Verify service was called
    mock_ltm_service.search.assert_called_once()
    call_args = mock_ltm_service.search.call_args[0][0]
    assert call_args.query == "important fact"
    assert call_args.user_id == "user-123"
    assert call_args.limit == 10

    app.dependency_overrides.clear()


@pytest.mark.unit
async def test_search_memories_missing_scope(
    app: FastAPI,
    client: AsyncClient,
    mock_ltm_service: AsyncMock,
) -> None:
    """Test POST /ltm/memories/search without scope returns 422."""
    from maas.ltm.router import get_ltm_service

    app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service

    request_data = {
        "query": "important fact",
        # Missing all scope fields
    }

    response = await client.post("/ltm/memories/search", json=request_data)

    assert response.status_code == 422
    mock_ltm_service.search.assert_not_called()

    app.dependency_overrides.clear()


@pytest.mark.unit
async def test_list_memories(app: FastAPI, client: AsyncClient, mock_ltm_service: AsyncMock) -> None:
    """Test GET /ltm/memories endpoint."""
    from maas.ltm.router import get_ltm_service

    app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service

    response = await client.get("/ltm/memories?user_id=user-123&limit=50")

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert len(data["results"]) == 1

    # Verify service was called with correct parameters
    mock_ltm_service.get_all.assert_called_once_with(
        user_id="user-123",
        agent_id=None,
        session_id=None,
        limit=50,
    )

    app.dependency_overrides.clear()


@pytest.mark.unit
async def test_list_memories_with_multiple_filters(
    app: FastAPI,
    client: AsyncClient,
    mock_ltm_service: AsyncMock,
) -> None:
    """Test GET /ltm/memories with multiple filter parameters."""
    from maas.ltm.router import get_ltm_service

    app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service

    response = await client.get("/ltm/memories?user_id=user-123&agent_id=agent-456&session_id=session-789")

    assert response.status_code == 200

    mock_ltm_service.get_all.assert_called_once_with(
        user_id="user-123",
        agent_id="agent-456",
        session_id="session-789",
        limit=100,  # default limit
    )

    app.dependency_overrides.clear()


@pytest.mark.unit
async def test_get_memory(app: FastAPI, client: AsyncClient, mock_ltm_service: AsyncMock) -> None:
    """Test GET /ltm/memories/{memory_id} endpoint."""
    from maas.ltm.router import get_ltm_service

    app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service

    memory_id = "mem-123"
    response = await client.get(f"/ltm/memories/{memory_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == memory_id
    assert data["memory"] == "Test memory"

    # Verify service was called
    mock_ltm_service.get.assert_called_once_with(memory_id)

    app.dependency_overrides.clear()


@pytest.mark.unit
async def test_update_memory(app: FastAPI, client: AsyncClient, mock_ltm_service: AsyncMock) -> None:
    """Test PUT /ltm/memories/{memory_id} endpoint."""
    from maas.ltm.router import get_ltm_service

    app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service

    memory_id = "mem-123"
    request_data = {"data": "Updated memory content"}

    response = await client.put(f"/ltm/memories/{memory_id}", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == memory_id

    # Verify service was called with correct arguments
    mock_ltm_service.update.assert_called_once_with(memory_id, "Updated memory content")

    app.dependency_overrides.clear()


@pytest.mark.unit
async def test_delete_memory(app: FastAPI, client: AsyncClient, mock_ltm_service: AsyncMock) -> None:
    """Test DELETE /ltm/memories/{memory_id} endpoint."""
    from maas.ltm.router import get_ltm_service

    app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service

    memory_id = "mem-123"
    response = await client.delete(f"/ltm/memories/{memory_id}")

    assert response.status_code == 200
    data = response.json()
    assert "message" in data

    # Verify service was called
    mock_ltm_service.delete.assert_called_once_with(memory_id)

    app.dependency_overrides.clear()


@pytest.mark.unit
async def test_get_memory_history(app: FastAPI, client: AsyncClient, mock_ltm_service: AsyncMock) -> None:
    """Test GET /ltm/memories/{memory_id}/history endpoint."""
    from maas.ltm.router import get_ltm_service

    app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service

    memory_id = "mem-123"
    response = await client.get(f"/ltm/memories/{memory_id}/history")

    assert response.status_code == 200
    data = response.json()
    assert "entries" in data
    assert len(data["entries"]) == 1
    assert data["entries"][0]["event"] == "UPDATE"

    # Verify service was called
    mock_ltm_service.history.assert_called_once_with(memory_id)

    app.dependency_overrides.clear()


@pytest.mark.unit
async def test_add_memory_with_agent_id(app: FastAPI, client: AsyncClient, mock_ltm_service: AsyncMock) -> None:
    """Test adding memory with agent_id instead of user_id."""
    from maas.ltm.router import get_ltm_service

    app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service

    request_data = {
        "messages": "Agent memory",
        "category": "episodic",
        "agent_id": "agent-456",
    }

    response = await client.post("/ltm/memories", json=request_data)

    assert response.status_code == 200

    # Verify service was called with agent_id
    call_args = mock_ltm_service.add.call_args[0][0]
    assert call_args.agent_id == "agent-456"
    assert call_args.user_id is None

    app.dependency_overrides.clear()


@pytest.mark.unit
async def test_add_memory_with_session_id(app: FastAPI, client: AsyncClient, mock_ltm_service: AsyncMock) -> None:
    """Test adding memory with session_id."""
    from maas.ltm.router import get_ltm_service

    app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service

    request_data = {
        "messages": "Session memory",
        "category": "preference",
        "session_id": "session-789",
    }

    response = await client.post("/ltm/memories", json=request_data)

    assert response.status_code == 200

    # Verify service was called with session_id
    call_args = mock_ltm_service.add.call_args[0][0]
    assert call_args.session_id == "session-789"

    app.dependency_overrides.clear()


@pytest.mark.unit
async def test_search_with_category_filter(app: FastAPI, client: AsyncClient, mock_ltm_service: AsyncMock) -> None:
    """Test searching memories with category filter."""
    from maas.ltm.router import get_ltm_service

    app.dependency_overrides[get_ltm_service] = lambda: mock_ltm_service

    request_data = {
        "query": "test",
        "user_id": "user-123",
        "categories": ["semantic"],
    }

    response = await client.post("/ltm/memories/search", json=request_data)

    assert response.status_code == 200

    # Verify category filter was passed
    call_args = mock_ltm_service.search.call_args[0][0]
    assert call_args.categories == [MemoryCategory.SEMANTIC]

    app.dependency_overrides.clear()
