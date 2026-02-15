from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from maas.config import get_settings
from maas.dependencies import lifespan_resources
from maas.stm.models import AddMessagesRequest, ContextResponse, SessionConfigRequest
from maas.stm.store import MessageStore
from maas.stm.strategies import get_strategy

if TYPE_CHECKING:
    from maas.config import Settings

router = APIRouter()


def _get_settings() -> Settings:
    if lifespan_resources.settings is not None:
        return lifespan_resources.settings
    return get_settings()


def _get_redis() -> Any:
    if lifespan_resources.redis is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis not initialized")
    return lifespan_resources.redis


def _get_llm_client() -> Any:
    if lifespan_resources.llm_client is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="LLM client not initialized")
    return lifespan_resources.llm_client


def _get_store(
    redis: Annotated[Any, Depends(_get_redis)],
    settings: Annotated[Any, Depends(_get_settings)],
) -> MessageStore:
    return MessageStore(
        redis,
        model_name=settings.resolved_stm_summarization_model,
        ttl_seconds=settings.stm_session_ttl_seconds,
    )


def _config_key(session_id: str) -> str:
    return f"stm:session:{session_id}:config"


async def _load_session_config(
    session_id: str,
    redis: Any,
    settings: Settings,
) -> SessionConfigRequest:
    raw = await redis.get(_config_key(session_id))
    if raw is None:
        return SessionConfigRequest(
            strategy=settings.stm_default_strategy,
            max_messages=settings.stm_max_messages,
            max_tokens=settings.stm_max_tokens,
        )
    if settings.stm_session_ttl_seconds > 0 and hasattr(redis, "expire"):
        await redis.expire(_config_key(session_id), settings.stm_session_ttl_seconds)
    data = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode())
    return SessionConfigRequest(
        strategy=data.get("strategy") or settings.stm_default_strategy,
        max_messages=data.get("max_messages") or settings.stm_max_messages,
        max_tokens=data.get("max_tokens") or settings.stm_max_tokens,
    )


@router.post("/{session_id}/messages")
async def add_messages(
    session_id: str,
    request: AddMessagesRequest,
    store: Annotated[MessageStore, Depends(_get_store)],
) -> dict:
    stored = await store.append_messages(session_id, request.messages)
    return {
        "session_id": session_id,
        "added": len(stored),
        "messages": [msg.model_dump() for msg in stored],
    }


@router.get("/{session_id}/context", response_model=ContextResponse)
async def get_context(
    session_id: str,
    store: Annotated[MessageStore, Depends(_get_store)],
    redis: Annotated[Any, Depends(_get_redis)],
    llm_client: Annotated[Any, Depends(_get_llm_client)],
    settings: Annotated[Any, Depends(_get_settings)],
) -> ContextResponse:
    config = await _load_session_config(session_id, redis, settings)
    strategy_impl = get_strategy(config.strategy or settings.stm_default_strategy)
    override_settings = settings.model_copy(
        update={
            "stm_default_strategy": config.strategy or settings.stm_default_strategy,
            "stm_max_messages": config.max_messages or settings.stm_max_messages,
            "stm_max_tokens": config.max_tokens or settings.stm_max_tokens,
        },
    )
    return await strategy_impl.apply(store, session_id, llm_client, override_settings)


@router.get("/{session_id}/messages")
async def get_messages(
    session_id: str,
    store: Annotated[MessageStore, Depends(_get_store)],
    limit: int | None = None,
) -> dict:
    messages = await store.get_messages(session_id, limit=limit)
    return {"session_id": session_id, "messages": [msg.model_dump() for msg in messages]}


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    store: Annotated[MessageStore, Depends(_get_store)],
    redis: Annotated[Any, Depends(_get_redis)],
) -> dict:
    await store.delete_session(session_id)
    await redis.delete(_config_key(session_id))
    return {"session_id": session_id, "deleted": True}


@router.put("/{session_id}/config")
async def update_config(
    session_id: str,
    request: SessionConfigRequest,
    redis: Annotated[Any, Depends(_get_redis)],
    settings: Annotated[Any, Depends(_get_settings)],
) -> dict:
    config = SessionConfigRequest(
        strategy=request.strategy or settings.stm_default_strategy,
        max_messages=request.max_messages,
        max_tokens=request.max_tokens,
    )
    await redis.set(_config_key(session_id), config.model_dump_json())
    if settings.stm_session_ttl_seconds > 0 and hasattr(redis, "expire"):
        await redis.expire(_config_key(session_id), settings.stm_session_ttl_seconds)
    return {"session_id": session_id, "config": config.model_dump()}
