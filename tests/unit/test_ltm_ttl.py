from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from maas.ltm.models import AddMemoryRequest, MemoryCategory, SearchMemoryRequest
from maas.ltm.service import LTMService


@pytest.mark.unit
async def test_add_memory_with_explicit_ttl() -> None:
    memory = AsyncMock()
    memory.add = AsyncMock(return_value={"id": "1"})
    service = LTMService(memory, default_ttl_seconds=0)
    request = AddMemoryRequest(
        messages="hello",
        category=MemoryCategory.SEMANTIC,
        user_id="user-1",
        ttl_seconds=3600,
    )

    before = int(time.time())
    await service.add(request)
    after = int(time.time())

    call_kwargs = memory.add.call_args[1]
    expires_at = call_kwargs["metadata"]["expires_at"]
    assert before + 3600 <= expires_at <= after + 3600


@pytest.mark.unit
async def test_add_memory_with_default_ttl() -> None:
    memory = AsyncMock()
    memory.add = AsyncMock(return_value={"id": "1"})
    service = LTMService(memory, default_ttl_seconds=120)
    request = AddMemoryRequest(
        messages="hello",
        category=MemoryCategory.SEMANTIC,
        user_id="user-1",
    )

    before = int(time.time())
    await service.add(request)
    after = int(time.time())

    call_kwargs = memory.add.call_args[1]
    expires_at = call_kwargs["metadata"]["expires_at"]
    assert before + 120 <= expires_at <= after + 120


@pytest.mark.unit
async def test_add_memory_no_ttl() -> None:
    memory = AsyncMock()
    memory.add = AsyncMock(return_value={"id": "1"})
    service = LTMService(memory, default_ttl_seconds=0)
    request = AddMemoryRequest(
        messages="hello",
        category=MemoryCategory.SEMANTIC,
        user_id="user-1",
        ttl_seconds=0,
    )

    await service.add(request)

    call_kwargs = memory.add.call_args[1]
    assert "expires_at" not in call_kwargs["metadata"]


@pytest.mark.unit
async def test_search_filters_expired() -> None:
    past_time = int(time.time()) - 3600
    memory = AsyncMock()
    memory.search = AsyncMock(
        return_value={
            "results": [
                {"id": "1", "metadata": {"expires_at": past_time}},
            ]
        }
    )
    service = LTMService(memory)
    request = SearchMemoryRequest(query="find", user_id="user-1")

    result = await service.search(request)

    assert result["results"] == []


@pytest.mark.unit
async def test_search_keeps_non_expired() -> None:
    future_time = int(time.time()) + 3600
    memory = AsyncMock()
    memory.search = AsyncMock(
        return_value={
            "results": [
                {"id": "1", "metadata": {"expires_at": future_time}},
            ]
        }
    )
    service = LTMService(memory)
    request = SearchMemoryRequest(query="find", user_id="user-1")

    result = await service.search(request)

    assert result["results"][0]["id"] == "1"


@pytest.mark.unit
async def test_get_all_filters_expired() -> None:
    past_time = int(time.time()) - 3600
    memory = AsyncMock()
    memory.get_all = AsyncMock(
        return_value={
            "results": [
                {"id": "1", "metadata": {"expires_at": past_time}},
            ]
        }
    )
    service = LTMService(memory)

    result = await service.get_all(user_id="user-1")

    assert result["results"] == []


@pytest.mark.unit
async def test_delete_expired() -> None:
    memory = AsyncMock()
    # The new delete_expired() queries the vector store directly.
    mock_collection = MagicMock()
    mock_collection.find.return_value = [
        {"_id": "1"},
        {"_id": "3"},
    ]
    memory.vector_store = MagicMock()
    memory.vector_store.collection = mock_collection
    memory.delete = AsyncMock(return_value={"deleted": True})
    service = LTMService(memory)

    result = await service.delete_expired()

    assert result == {"deleted": 2, "ids": ["1", "3"]}
    assert memory.delete.await_args_list == [call("1"), call("3")]


@pytest.mark.unit
async def test_is_expired_with_no_metadata() -> None:
    assert LTMService._is_expired({"id": "1"}) is False
