from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from maas.config import STMStrategy
from maas.dependencies import lifespan_resources

if TYPE_CHECKING:
    from httpx import AsyncClient


class FakeRedis:
    def __init__(self) -> None:
        self._zsets: dict[str, list[tuple[float, str]]] = {}
        self._values: dict[str, str] = {}

    async def zadd(self, key: str, mapping: dict[str, float]) -> None:
        entries = self._zsets.setdefault(key, [])
        for member, score in mapping.items():
            entries.append((score, member))
        entries.sort(key=lambda item: item[0])

    async def zrange(self, key: str, start: int, end: int) -> list[str]:
        entries = self._zsets.get(key, [])
        if end == -1:
            end = len(entries) - 1
        if start < 0:
            start = len(entries) + start
        if end < 0:
            end = len(entries) + end
        if start < 0 or end < 0 or start >= len(entries):
            return []
        end = min(end, len(entries) - 1)
        return [member for _, member in entries[start : end + 1]]

    async def zcard(self, key: str) -> int:
        return len(self._zsets.get(key, []))

    async def delete(self, key: str) -> None:
        self._zsets.pop(key, None)
        self._values.pop(key, None)

    async def set(self, key: str, value: str) -> None:
        self._values[key] = value

    async def get(self, key: str) -> str | None:
        return self._values.get(key)


class FakeLLMResponseMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeLLMChoice:
    def __init__(self, content: str) -> None:
        self.message = FakeLLMResponseMessage(content)


class FakeLLMResponse:
    def __init__(self, content: str) -> None:
        self.choices = [FakeLLMChoice(content)]


class FakeCompletions:
    def __init__(self, content: str) -> None:
        self._content = content

    async def create(self, **_kwargs: Any) -> FakeLLMResponse:
        return FakeLLMResponse(self._content)


class FakeChat:
    def __init__(self, content: str) -> None:
        self.completions = FakeCompletions(content)


class FakeLLMClient:
    def __init__(self, content: str) -> None:
        self.chat = FakeChat(content)


# Original comprehensive end-to-end test
@pytest.mark.unit
async def test_stm_endpoints(client: AsyncClient) -> None:
    """End-to-end test of STM endpoints with FakeRedis and FakeLLMClient."""
    lifespan_resources.redis = FakeRedis()
    lifespan_resources.llm_client = FakeLLMClient("summary")

    add_response = await client.post(
        "/stm/test-session/messages",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert add_response.status_code == 200
    assert add_response.json()["session_id"] == "test-session"

    context_response = await client.get("/stm/test-session/context")
    assert context_response.status_code == 200
    context_data = context_response.json()
    assert context_data["session_id"] == "test-session"
    assert context_data["strategy"] == "sliding_window"

    config_response = await client.put(
        "/stm/test-session/config",
        json={"strategy": "sliding_window", "max_messages": 1},
    )
    assert config_response.status_code == 200
    assert config_response.json()["config"]["strategy"] == "sliding_window"

    delete_response = await client.delete("/stm/test-session")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True


# Additional unit tests with mocks
@pytest.fixture
def mock_redis():
    """Fixture providing a mocked Redis client for dependency override."""
    mock = AsyncMock()
    mock.get.return_value = None
    mock.set.return_value = True
    mock.delete.return_value = 1
    mock.zadd.return_value = 1
    mock.zrange.return_value = []
    mock.zcard.return_value = 0
    return mock


@pytest.fixture
def mock_llm_client():
    """Fixture providing a mocked LLM client for dependency override."""
    mock = MagicMock()
    mock.chat = MagicMock()
    mock.chat.completions = MagicMock()
    mock.chat.completions.create = AsyncMock()
    return mock


@pytest.mark.unit
async def test_add_messages(client: AsyncClient, mock_redis: AsyncMock, mock_llm_client: MagicMock) -> None:
    """Test POST /{session_id}/messages endpoint."""
    lifespan_resources.redis = mock_redis
    lifespan_resources.llm_client = mock_llm_client

    session_id = "test-session"
    request_data = {
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
    }

    mock_redis.zadd.return_value = 2

    response = await client.post(f"/stm/{session_id}/messages", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "Hello"
    assert "id" in data["messages"][0]
    assert "timestamp" in data["messages"][0]
    assert "token_count" in data["messages"][0]

    # Verify Redis was called
    mock_redis.zadd.assert_called_once()


@pytest.mark.unit
async def test_get_context_sliding_window(
    client: AsyncClient,
    mock_redis: AsyncMock,
    mock_llm_client: MagicMock,
) -> None:
    """Test GET /{session_id}/context with sliding window strategy."""
    lifespan_resources.redis = mock_redis
    lifespan_resources.llm_client = mock_llm_client

    session_id = "test-session"

    # Mock session config (no config = default strategy)
    mock_redis.get.return_value = json.dumps({"strategy": "sliding_window"})

    # Mock stored messages
    stored_message = {
        "id": "msg-1",
        "role": "user",
        "content": "Hello",
        "timestamp": 1000.0,
        "token_count": 5,
    }
    mock_redis.zrange.return_value = [json.dumps(stored_message)]

    response = await client.get(f"/stm/{session_id}/context")

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["strategy"] == STMStrategy.SLIDING_WINDOW
    assert len(data["messages"]) == 1
    assert data["messages"][0]["content"] == "Hello"
    assert data["total_tokens"] == 5

    # Verify Redis was queried
    mock_redis.get.assert_called_once()
    mock_redis.zrange.assert_called_once()


@pytest.mark.unit
async def test_get_context_with_config(
    client: AsyncClient,
    mock_redis: AsyncMock,
    mock_llm_client: MagicMock,
) -> None:
    """Test GET /{session_id}/context with configured strategy."""
    lifespan_resources.redis = mock_redis
    lifespan_resources.llm_client = mock_llm_client

    session_id = "test-session"

    # Mock session config with token threshold strategy
    config = {"strategy": "token_threshold", "max_tokens": 1000}
    mock_redis.get.return_value = json.dumps(config)

    # Mock stored messages (under threshold)
    stored_message = {
        "id": "msg-1",
        "role": "user",
        "content": "Hello",
        "timestamp": 1000.0,
        "token_count": 10,
    }
    mock_redis.zrange.return_value = [json.dumps(stored_message)]

    response = await client.get(f"/stm/{session_id}/context")

    assert response.status_code == 200
    data = response.json()
    assert data["strategy"] == STMStrategy.TOKEN_THRESHOLD


@pytest.mark.unit
async def test_delete_session(client: AsyncClient, mock_redis: AsyncMock, mock_llm_client: MagicMock) -> None:
    """Test DELETE /{session_id} endpoint."""
    lifespan_resources.redis = mock_redis
    lifespan_resources.llm_client = mock_llm_client

    session_id = "test-session"
    mock_redis.delete.return_value = 1

    response = await client.delete(f"/stm/{session_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["deleted"] is True

    # Verify Redis delete was called twice (messages + config)
    assert mock_redis.delete.call_count == 2
    delete_calls = [call[0][0] for call in mock_redis.delete.call_args_list]
    assert "stm:session:test-session:messages" in delete_calls
    assert "stm:session:test-session:config" in delete_calls


@pytest.mark.unit
async def test_update_config(client: AsyncClient, mock_redis: AsyncMock, mock_llm_client: MagicMock) -> None:
    """Test PUT /{session_id}/config endpoint."""
    lifespan_resources.redis = mock_redis
    lifespan_resources.llm_client = mock_llm_client

    session_id = "test-session"
    config_data = {
        "strategy": "token_threshold",
        "max_messages": 100,
        "max_tokens": 5000,
    }

    mock_redis.set.return_value = True

    response = await client.put(f"/stm/{session_id}/config", json=config_data)

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["config"]["strategy"] == "token_threshold"
    assert data["config"]["max_messages"] == 100
    assert data["config"]["max_tokens"] == 5000

    # Verify Redis set was called
    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args
    assert call_args[0][0] == "stm:session:test-session:config"


@pytest.mark.unit
async def test_update_config_defaults_to_strategy(
    client: AsyncClient,
    mock_redis: AsyncMock,
    mock_llm_client: MagicMock,
) -> None:
    """Test PUT /{session_id}/config with partial config (defaults to configured strategy)."""
    lifespan_resources.redis = mock_redis
    lifespan_resources.llm_client = mock_llm_client

    session_id = "test-session"
    config_data = {"max_messages": 50}

    mock_redis.set.return_value = True

    response = await client.put(f"/stm/{session_id}/config", json=config_data)

    assert response.status_code == 200
    data = response.json()
    # Should default to configured strategy (sliding_window in default settings)
    assert data["config"]["strategy"] == STMStrategy.SLIDING_WINDOW
    assert data["config"]["max_messages"] == 50


@pytest.mark.unit
async def test_redis_unavailable(client: AsyncClient, mock_llm_client: MagicMock) -> None:
    """Test that endpoints return 503 when Redis is unavailable."""
    # Set Redis to None to simulate unavailability
    lifespan_resources.redis = None
    lifespan_resources.llm_client = mock_llm_client

    session_id = "test-session"

    # Test add_messages
    response = await client.post(f"/stm/{session_id}/messages", json={"messages": []})
    assert response.status_code == 503

    # Test get_context
    response = await client.get(f"/stm/{session_id}/context")
    assert response.status_code == 503

    # Test delete_session
    response = await client.delete(f"/stm/{session_id}")
    assert response.status_code == 503


@pytest.mark.unit
async def test_llm_unavailable(client: AsyncClient, mock_redis: AsyncMock) -> None:
    """Test that endpoints return 503 when LLM client is unavailable."""
    # Set LLM client to None
    lifespan_resources.redis = mock_redis
    lifespan_resources.llm_client = None

    session_id = "test-session"
    mock_redis.get.return_value = None
    mock_redis.zrange.return_value = []

    # Test get_context (requires LLM client)
    response = await client.get(f"/stm/{session_id}/context")
    assert response.status_code == 503


@pytest.mark.unit
async def test_add_empty_messages(client: AsyncClient, mock_redis: AsyncMock, mock_llm_client: MagicMock) -> None:
    """Test adding empty message list."""
    lifespan_resources.redis = mock_redis
    lifespan_resources.llm_client = mock_llm_client

    session_id = "test-session"
    request_data = {"messages": []}

    response = await client.post(f"/stm/{session_id}/messages", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert len(data["messages"]) == 0

    # Redis zadd should not be called for empty list
    mock_redis.zadd.assert_not_called()
