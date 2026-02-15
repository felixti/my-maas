from __future__ import annotations

import json

import pytest

from maas.stm.models import Message, MessageRole
from maas.stm.store import MessageStore


class FakeRedis:
    def __init__(self) -> None:
        self._zsets: dict[str, list[tuple[float, str]]] = {}

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


@pytest.mark.unit
async def test_append_and_get_messages() -> None:
    redis = FakeRedis()
    store = MessageStore(redis, encoding_name="cl100k_base")
    messages = [Message(role=MessageRole.USER, content="hello")]

    stored = await store.append_messages("session", messages)
    assert len(stored) == 1
    assert stored[0].token_count > 0

    fetched = await store.get_messages("session")
    assert len(fetched) == 1
    assert fetched[0].content == "hello"


@pytest.mark.unit
async def test_get_message_count_and_delete() -> None:
    redis = FakeRedis()
    store = MessageStore(redis, encoding_name="cl100k_base")
    await store.append_messages("session", [Message(role=MessageRole.USER, content="one")])

    count = await store.get_message_count("session")
    assert count == 1

    await store.delete_session("session")
    count = await store.get_message_count("session")
    assert count == 0


@pytest.mark.unit
async def test_replace_messages() -> None:
    redis = FakeRedis()
    store = MessageStore(redis, encoding_name="cl100k_base")
    await store.append_messages("session", [Message(role=MessageRole.USER, content="one")])

    await store.replace_messages(
        "session",
        [Message(role=MessageRole.ASSISTANT, content="two")],
    )

    fetched = await store.get_messages("session")
    assert len(fetched) == 1
    assert fetched[0].content == "two"


@pytest.mark.unit
async def test_serialization_schema() -> None:
    redis = FakeRedis()
    store = MessageStore(redis, encoding_name="cl100k_base")
    stored = await store.append_messages("session", [Message(role=MessageRole.USER, content="hi")])
    key = "stm:session:session:messages"
    payload = json.loads(redis._zsets[key][0][1])
    assert payload["id"] == stored[0].id
