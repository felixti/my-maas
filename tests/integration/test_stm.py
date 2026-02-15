from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


def _session_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


@pytest.mark.integration
async def test_add_messages(integration_client: AsyncClient) -> None:
    session_id = _session_id("add-messages")
    response = await integration_client.post(
        f"/stm/{session_id}/messages",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["added"] >= 1


@pytest.mark.integration
async def test_get_messages_returns_added(integration_client: AsyncClient) -> None:
    session_id = _session_id("get-messages")
    await integration_client.post(
        f"/stm/{session_id}/messages",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    response = await integration_client.get(f"/stm/{session_id}/messages")

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["messages"][0]["content"] == "hello"


@pytest.mark.integration
async def test_get_messages_with_limit(integration_client: AsyncClient) -> None:
    session_id = _session_id("get-messages-limit")
    await integration_client.post(
        f"/stm/{session_id}/messages",
        json={
            "messages": [
                {"role": "user", "content": "first"},
                {"role": "user", "content": "second"},
            ]
        },
    )

    response = await integration_client.get(f"/stm/{session_id}/messages?limit=1")

    assert response.status_code == 200
    data = response.json()
    assert len(data["messages"]) == 1
    assert data["messages"][0]["content"] == "second"


@pytest.mark.integration
async def test_get_context_sliding_window(integration_client: AsyncClient) -> None:
    session_id = _session_id("context")
    await integration_client.post(
        f"/stm/{session_id}/messages",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    response = await integration_client.get(f"/stm/{session_id}/context")

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["messages"]
    assert data["strategy"] == "sliding_window"
    assert isinstance(data["total_tokens"], int)


@pytest.mark.integration
async def test_delete_session_clears_messages(integration_client: AsyncClient) -> None:
    session_id = _session_id("delete-session")
    await integration_client.post(
        f"/stm/{session_id}/messages",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    delete_response = await integration_client.delete(f"/stm/{session_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True

    get_response = await integration_client.get(f"/stm/{session_id}/messages")
    assert get_response.status_code == 200
    assert get_response.json()["messages"] == []


@pytest.mark.integration
async def test_update_config(integration_client: AsyncClient) -> None:
    session_id = _session_id("update-config")
    response = await integration_client.put(
        f"/stm/{session_id}/config",
        json={"strategy": "sliding_window", "max_messages": 5},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["config"]["strategy"] == "sliding_window"
    assert data["config"]["max_messages"] == 5


@pytest.mark.integration
async def test_full_lifecycle(integration_client: AsyncClient) -> None:
    session_id = _session_id("full-lifecycle")
    await integration_client.post(
        f"/stm/{session_id}/messages",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    context_before = await integration_client.get(f"/stm/{session_id}/context")
    assert context_before.status_code == 200
    assert context_before.json()["messages"]

    update_response = await integration_client.put(
        f"/stm/{session_id}/config",
        json={"strategy": "sliding_window", "max_messages": 2},
    )
    assert update_response.status_code == 200

    context_after = await integration_client.get(f"/stm/{session_id}/context")
    assert context_after.status_code == 200
    assert context_after.json()["strategy"] == "sliding_window"

    delete_response = await integration_client.delete(f"/stm/{session_id}")
    assert delete_response.status_code == 200

    get_response = await integration_client.get(f"/stm/{session_id}/messages")
    assert get_response.status_code == 200
    assert get_response.json()["messages"] == []


@pytest.mark.integration
async def test_session_returns_data_immediately(integration_client: AsyncClient) -> None:
    session_id = _session_id("ttl-immediate")
    await integration_client.post(
        f"/stm/{session_id}/messages",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    response = await integration_client.get(f"/stm/{session_id}/messages")

    assert response.status_code == 200
    assert response.json()["messages"]


@pytest.mark.integration
async def test_empty_session_returns_empty_list(integration_client: AsyncClient) -> None:
    session_id = _session_id("empty-session")
    response = await integration_client.get(f"/stm/{session_id}/messages")

    assert response.status_code == 200
    assert response.json()["messages"] == []


@pytest.mark.integration
async def test_add_multiple_batches(integration_client: AsyncClient) -> None:
    session_id = _session_id("multiple-batches")
    await integration_client.post(
        f"/stm/{session_id}/messages",
        json={"messages": [{"role": "user", "content": "first"}]},
    )
    await integration_client.post(
        f"/stm/{session_id}/messages",
        json={"messages": [{"role": "user", "content": "second"}]},
    )

    response = await integration_client.get(f"/stm/{session_id}/messages")

    assert response.status_code == 200
    contents = [message["content"] for message in response.json()["messages"]]
    assert contents == ["first", "second"]
