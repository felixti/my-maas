from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from maas.config import Settings
from maas.dependencies import lifespan_resources
from maas.stm.models import Message, MessageRole
from maas.stm.store import MessageStore


@pytest.mark.unit
async def test_append_messages_sets_ttl() -> None:
    redis = AsyncMock()
    redis.zadd = AsyncMock()
    redis.expire = AsyncMock()
    store = MessageStore(redis, encoding_name="cl100k_base", ttl_seconds=3600)

    await store.append_messages("session", [Message(role=MessageRole.USER, content="hello")])

    redis.zadd.assert_awaited_once()
    redis.expire.assert_awaited_once_with("stm:session:session:messages", 3600)


@pytest.mark.unit
async def test_append_messages_no_ttl_when_zero() -> None:
    redis = AsyncMock()
    redis.zadd = AsyncMock()
    redis.expire = AsyncMock()
    store = MessageStore(redis, encoding_name="cl100k_base", ttl_seconds=0)

    await store.append_messages("session", [Message(role=MessageRole.USER, content="hello")])

    redis.zadd.assert_awaited_once()
    redis.expire.assert_not_called()


@pytest.mark.unit
async def test_replace_messages_sets_ttl() -> None:
    redis = AsyncMock()
    redis.delete = AsyncMock()
    redis.zadd = AsyncMock()
    redis.expire = AsyncMock()
    store = MessageStore(redis, encoding_name="cl100k_base", ttl_seconds=3600)

    await store.replace_messages("session", [Message(role=MessageRole.USER, content="hello")])

    redis.zadd.assert_awaited_once()
    redis.expire.assert_awaited_once_with("stm:session:session:messages", 3600)


@pytest.mark.unit
async def test_config_key_ttl_on_update(client) -> None:
    redis = AsyncMock()
    redis.set = AsyncMock()
    redis.expire = AsyncMock()
    lifespan_resources.redis = redis
    lifespan_resources.settings = Settings(stm_session_ttl_seconds=3600)

    response = await client.put(
        "/stm/test-session/config",
        json={"strategy": "sliding_window", "max_messages": 10},
    )

    assert response.status_code == 200
    redis.expire.assert_awaited_once_with("stm:session:test-session:config", 3600)
