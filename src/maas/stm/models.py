from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from maas.config import STMStrategy  # noqa: TC001


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    SUMMARY = "summary"


class Message(BaseModel):
    role: MessageRole
    content: str
    metadata: dict[str, Any] | None = None


class StoredMessage(Message):
    id: str
    timestamp: float
    token_count: int


class AddMessagesRequest(BaseModel):
    messages: list[Message] = Field(default_factory=list)


class ContextResponse(BaseModel):
    session_id: str
    messages: list[StoredMessage]
    strategy: STMStrategy
    total_tokens: int


class SessionConfigRequest(BaseModel):
    strategy: STMStrategy | None = None
    max_messages: int | None = None
    max_tokens: int | None = None
