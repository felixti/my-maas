from __future__ import annotations

from typing import Any

import pytest

from maas.config import Settings, STMStrategy
from maas.stm.models import Message, MessageRole
from maas.stm.store import MessageStore
from maas.stm.strategies import SlidingWindowStrategy, TokenThresholdStrategy


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


@pytest.mark.unit
async def test_sliding_window_truncates() -> None:
    redis = FakeRedis()
    store = MessageStore(redis, encoding_name="cl100k_base")
    settings = Settings(stm_max_messages=2)
    llm_client = FakeLLMClient("summary")
    await store.append_messages(
        "session",
        [
            Message(role=MessageRole.USER, content="one"),
            Message(role=MessageRole.USER, content="two"),
            Message(role=MessageRole.USER, content="three"),
        ],
    )

    strategy = SlidingWindowStrategy()
    result = await strategy.apply(store, "session", llm_client, settings)
    assert result.strategy == STMStrategy.SLIDING_WINDOW
    assert len(result.messages) == 2
    assert result.messages[0].content == "two"


@pytest.mark.unit
async def test_token_threshold_summarizes() -> None:
    redis = FakeRedis()
    store = MessageStore(redis, encoding_name="cl100k_base")
    settings = Settings(stm_max_tokens=1)
    llm_client = FakeLLMClient("summary text")
    await store.append_messages(
        "session",
        [
            Message(role=MessageRole.USER, content="one"),
            Message(role=MessageRole.USER, content="two"),
        ],
    )

    strategy = TokenThresholdStrategy()
    result = await strategy.apply(store, "session", llm_client, settings)
    assert result.strategy == STMStrategy.TOKEN_THRESHOLD
    assert result.messages[0].role == MessageRole.SUMMARY
    assert result.messages[0].content == "summary text"
    assert len(result.messages) >= 1
