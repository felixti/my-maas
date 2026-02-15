from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from maas.config import Settings
from maas.dependencies import lifespan_resources
from maas.ltm.models import AddMemoryRequest, MemoryCategory, SearchMemoryRequest
from maas.ltm.service import LTMService

if TYPE_CHECKING:
    from fastapi import FastAPI
    from httpx import AsyncClient


@pytest.mark.unit
async def test_batch_add_success() -> None:
    memory = AsyncMock()
    memory.add = AsyncMock(side_effect=[{"id": "1"}, {"id": "2"}])
    service = LTMService(memory)
    requests = [
        AddMemoryRequest(messages="hello", category=MemoryCategory.SEMANTIC, user_id="user-1"),
        AddMemoryRequest(messages="world", category=MemoryCategory.FACT, user_id="user-1"),
    ]

    results = await service.batch_add(requests)

    assert len(results) == 2
    assert all(result["success"] for result in results)
    assert results[0]["result"]["id"] == "1"
    assert results[1]["result"]["id"] == "2"


@pytest.mark.unit
async def test_batch_add_partial_failure() -> None:
    memory = AsyncMock()
    memory.add = AsyncMock(side_effect=[{"id": "1"}, Exception("boom")])
    service = LTMService(memory)
    requests = [
        AddMemoryRequest(messages="hello", category=MemoryCategory.SEMANTIC, user_id="user-1"),
        AddMemoryRequest(messages="world", category=MemoryCategory.FACT, user_id="user-1"),
    ]

    results = await service.batch_add(requests)

    assert results[0]["success"] is True
    assert results[1]["success"] is False
    assert results[1]["error"] == "boom"


@pytest.mark.unit
async def test_batch_search_success() -> None:
    memory = AsyncMock()
    memory.search = AsyncMock(side_effect=[{"results": [{"id": "1"}]}, {"results": [{"id": "2"}]}])
    service = LTMService(memory)
    requests = [
        SearchMemoryRequest(query="hello", user_id="user-1"),
        SearchMemoryRequest(query="world", user_id="user-1"),
    ]

    results = await service.batch_search(requests)

    assert len(results) == 2
    assert all(result["success"] for result in results)
    assert results[0]["result"]["results"][0]["id"] == "1"
    assert results[1]["result"]["results"][0]["id"] == "2"


@pytest.mark.unit
async def test_batch_delete_success() -> None:
    memory = AsyncMock()
    memory.delete = AsyncMock(side_effect=[{"id": "1"}, {"id": "2"}])
    service = LTMService(memory)

    results = await service.batch_delete(["1", "2"])

    assert len(results) == 2
    assert all(result["success"] for result in results)


@pytest.mark.unit
async def test_batch_delete_partial_failure() -> None:
    memory = AsyncMock()
    memory.delete = AsyncMock(side_effect=[{"id": "1"}, Exception("nope")])
    service = LTMService(memory)

    results = await service.batch_delete(["1", "2"])

    assert results[0]["success"] is True
    assert results[1]["success"] is False
    assert results[1]["error"] == "nope"


@pytest.mark.unit
async def test_batch_add_empty() -> None:
    memory = AsyncMock()
    service = LTMService(memory)

    results = await service.batch_add([])

    assert results == []


@pytest.mark.unit
async def test_batch_add_exceeds_max_size(app: FastAPI, client: AsyncClient) -> None:
    from maas.ltm.router import get_ltm_service

    mock_service = AsyncMock()
    app.dependency_overrides[get_ltm_service] = lambda: mock_service
    prior_settings = lifespan_resources.settings
    lifespan_resources.settings = Settings(ltm_max_batch_size=2)
    try:
        items = [
            {"messages": "a", "category": "semantic", "user_id": "u1"},
            {"messages": "b", "category": "semantic", "user_id": "u1"},
            {"messages": "c", "category": "semantic", "user_id": "u1"},
        ]
        response = await client.post("/ltm/memories/batch/add", json={"items": items})
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()
        lifespan_resources.settings = prior_settings


@pytest.mark.unit
async def test_batch_search_exceeds_max_size(app: FastAPI, client: AsyncClient) -> None:
    from maas.ltm.router import get_ltm_service

    mock_service = AsyncMock()
    app.dependency_overrides[get_ltm_service] = lambda: mock_service
    prior_settings = lifespan_resources.settings
    lifespan_resources.settings = Settings(ltm_max_batch_size=2)
    try:
        items = [
            {"query": "a", "user_id": "u1"},
            {"query": "b", "user_id": "u1"},
            {"query": "c", "user_id": "u1"},
        ]
        response = await client.post("/ltm/memories/batch/search", json={"items": items})
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()
        lifespan_resources.settings = prior_settings


@pytest.mark.unit
async def test_batch_delete_exceeds_max_size(app: FastAPI, client: AsyncClient) -> None:
    from maas.ltm.router import get_ltm_service

    mock_service = AsyncMock()
    app.dependency_overrides[get_ltm_service] = lambda: mock_service
    prior_settings = lifespan_resources.settings
    lifespan_resources.settings = Settings(ltm_max_batch_size=2)
    try:
        response = await client.post(
            "/ltm/memories/batch/delete",
            json={"memory_ids": ["1", "2", "3"]},
        )
        assert response.status_code == 400
    finally:
        app.dependency_overrides.clear()
        lifespan_resources.settings = prior_settings


@pytest.mark.unit
async def test_batch_response_structure(app: FastAPI, client: AsyncClient) -> None:
    from maas.ltm.router import get_ltm_service

    mock_service = AsyncMock()
    mock_service.batch_add = AsyncMock(
        return_value=[
            {"index": 0, "success": True, "result": {"id": "1"}, "error": None},
            {"index": 1, "success": False, "result": None, "error": "boom"},
        ]
    )
    app.dependency_overrides[get_ltm_service] = lambda: mock_service
    prior_settings = lifespan_resources.settings
    lifespan_resources.settings = Settings(ltm_max_batch_size=5)
    try:
        items = [
            {"messages": "a", "category": "semantic", "user_id": "u1"},
            {"messages": "b", "category": "semantic", "user_id": "u1"},
        ]
        response = await client.post("/ltm/memories/batch/add", json={"items": items})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["succeeded"] == 1
        assert data["failed"] == 1
        assert len(data["results"]) == 2
    finally:
        app.dependency_overrides.clear()
        lifespan_resources.settings = prior_settings
