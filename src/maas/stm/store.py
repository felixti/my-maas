from __future__ import annotations

import importlib
import json
import time
import uuid
from typing import Any

from maas.stm.models import Message, StoredMessage


class MessageStore:
    def __init__(
        self,
        redis: Any,
        encoding_name: str | None = None,
        model_name: str | None = None,
        ttl_seconds: int = 0,
    ) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds
        tiktoken = importlib.import_module("tiktoken")
        if encoding_name:
            self._encoding = tiktoken.get_encoding(encoding_name)
        elif model_name:
            try:
                self._encoding = tiktoken.encoding_for_model(model_name)
            except KeyError:
                self._encoding = tiktoken.get_encoding("cl100k_base")
        else:
            self._encoding = tiktoken.get_encoding("cl100k_base")

    def _session_key(self, session_id: str) -> str:
        return f"stm:session:{session_id}:messages"

    def _count_tokens(self, content: str) -> int:
        return len(self._encoding.encode(content))

    def _serialize(self, message: StoredMessage) -> str:
        return json.dumps(message.model_dump())

    def _deserialize(self, payload: str) -> StoredMessage:
        return StoredMessage.model_validate_json(payload)

    def _build_stored(self, message: Message) -> StoredMessage:
        return StoredMessage(
            id=str(uuid.uuid4()),
            role=message.role,
            content=message.content,
            metadata=message.metadata,
            timestamp=time.time(),
            token_count=self._count_tokens(message.content),
        )

    async def _touch_ttl(self, key: str) -> None:
        if self._ttl_seconds > 0 and hasattr(self._redis, "expire"):
            await self._redis.expire(key, self._ttl_seconds)

    async def append_messages(self, session_id: str, messages: list[Message]) -> list[StoredMessage]:
        if not messages:
            return []
        stored = [self._build_stored(message) for message in messages]
        key = self._session_key(session_id)
        values = {self._serialize(item): item.timestamp for item in stored}
        await self._redis.zadd(key, values)
        await self._touch_ttl(key)
        return stored

    async def get_messages(self, session_id: str, limit: int | None = None) -> list[StoredMessage]:
        key = self._session_key(session_id)
        if limit is None:
            entries = await self._redis.zrange(key, 0, -1)
        elif limit <= 0:
            entries = []
        else:
            entries = await self._redis.zrange(key, -limit, -1)
        return [self._deserialize(entry) for entry in entries]

    async def get_message_count(self, session_id: str) -> int:
        key = self._session_key(session_id)
        return int(await self._redis.zcard(key))

    async def delete_session(self, session_id: str) -> None:
        key = self._session_key(session_id)
        await self._redis.delete(key)

    async def replace_messages(self, session_id: str, messages: list[Message]) -> None:
        key = self._session_key(session_id)
        await self._redis.delete(key)
        if messages:
            stored = [self._build_stored(message) for message in messages]
            values = {self._serialize(item): item.timestamp for item in stored}
            await self._redis.zadd(key, values)
            await self._touch_ttl(key)
