from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, model_validator


class MemoryCategory(StrEnum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    FACT = "fact"
    PREFERENCE = "preference"


class BaseMemoryRequest(BaseModel):
    user_id: str | None = None
    agent_id: str | None = None
    session_id: str | None = None

    @model_validator(mode="after")
    def check_scope(self) -> BaseMemoryRequest:
        if not (self.user_id or self.agent_id or self.session_id):
            raise ValueError("At least one of user_id, agent_id, or session_id must be provided")
        return self


class AddMemoryRequest(BaseMemoryRequest):
    messages: str | list[dict[str, Any]]
    category: MemoryCategory
    metadata: dict[str, Any] | None = None
    ttl_seconds: int | None = None  # None = use server default, 0 = no expiration


class SearchMemoryRequest(BaseMemoryRequest):
    query: str
    categories: list[MemoryCategory] | None = None
    limit: int = 100


class UpdateMemoryRequest(BaseModel):
    data: str


class MemoryResponse(BaseModel):
    id: str
    memory: str
    metadata: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None
    score: float | None = None


class MemoryListResponse(BaseModel):
    results: list[MemoryResponse]


class HistoryResponse(BaseModel):
    entries: list[dict[str, Any]]


class BatchAddItem(BaseMemoryRequest):
    messages: str | list[dict[str, Any]]
    category: MemoryCategory
    metadata: dict[str, Any] | None = None
    ttl_seconds: int | None = None


class BatchAddRequest(BaseModel):
    items: list[BatchAddItem]


class BatchSearchItem(BaseMemoryRequest):
    query: str
    categories: list[MemoryCategory] | None = None
    limit: int = 100


class BatchSearchRequest(BaseModel):
    items: list[BatchSearchItem]


class BatchDeleteRequest(BaseModel):
    memory_ids: list[str]


class BatchItemResult(BaseModel):
    index: int
    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None


class BatchResponse(BaseModel):
    results: list[BatchItemResult]
    total: int
    succeeded: int
    failed: int
