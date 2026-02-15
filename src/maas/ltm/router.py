from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from mem0 import AsyncMemory

from maas.config import get_settings
from maas.ltm.config import build_mem0_config
from maas.ltm.models import (
    AddMemoryRequest,
    BatchAddRequest,
    BatchDeleteRequest,
    BatchResponse,
    BatchSearchRequest,
    HistoryResponse,
    MemoryListResponse,
    MemoryResponse,
    SearchMemoryRequest,
    UpdateMemoryRequest,
)
from maas.ltm.service import LTMService

if TYPE_CHECKING:
    from maas.config import Settings

router = APIRouter()

_ltm_service: LTMService | None = None


async def _create_async_memory(settings: Settings) -> AsyncMemory:
    return await AsyncMemory.from_config(build_mem0_config(settings))


async def get_ltm_service() -> LTMService:
    global _ltm_service
    if _ltm_service is None:
        settings = get_settings()
        _ltm_service = LTMService(
            await _create_async_memory(settings),
            default_ttl_seconds=settings.ltm_default_ttl_seconds,
        )
    return _ltm_service


@router.post("/memories", response_model=MemoryResponse)
async def add_memory(
    request: AddMemoryRequest,
    service: Annotated[LTMService, Depends(get_ltm_service)],
) -> dict:
    return await service.add(request)


@router.post("/memories/search", response_model=MemoryListResponse)
async def search_memories(
    service: Annotated[LTMService, Depends(get_ltm_service)],
    request: Annotated[SearchMemoryRequest | None, Body()] = None,
) -> dict:
    if request is None:
        return {"results": []}
    return await service.search(request)


@router.delete("/memories/expired")
async def delete_expired_memories(
    service: Annotated[LTMService, Depends(get_ltm_service)],
) -> dict:
    return await service.delete_expired()


@router.post("/memories/batch/add", response_model=BatchResponse)
async def batch_add_memories(
    request: BatchAddRequest,
    service: Annotated[LTMService, Depends(get_ltm_service)],
) -> dict:
    settings = get_settings()
    if len(request.items) > settings.ltm_max_batch_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"Batch size {len(request.items)} exceeds maximum of {settings.ltm_max_batch_size}"),
        )
    add_requests = [
        AddMemoryRequest(
            messages=item.messages,
            category=item.category,
            metadata=item.metadata,
            ttl_seconds=item.ttl_seconds,
            user_id=item.user_id,
            agent_id=item.agent_id,
            session_id=item.session_id,
        )
        for item in request.items
    ]
    results = await service.batch_add(add_requests)
    succeeded = sum(1 for r in results if r["success"])
    return {
        "results": results,
        "total": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
    }


@router.post("/memories/batch/search", response_model=BatchResponse)
async def batch_search_memories(
    request: BatchSearchRequest,
    service: Annotated[LTMService, Depends(get_ltm_service)],
) -> dict:
    settings = get_settings()
    if len(request.items) > settings.ltm_max_batch_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"Batch size {len(request.items)} exceeds maximum of {settings.ltm_max_batch_size}"),
        )
    search_requests = [
        SearchMemoryRequest(
            query=item.query,
            categories=item.categories,
            limit=item.limit,
            user_id=item.user_id,
            agent_id=item.agent_id,
            session_id=item.session_id,
        )
        for item in request.items
    ]
    results = await service.batch_search(search_requests)
    succeeded = sum(1 for r in results if r["success"])
    return {
        "results": results,
        "total": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
    }


@router.post("/memories/batch/delete", response_model=BatchResponse)
async def batch_delete_memories(
    request: BatchDeleteRequest,
    service: Annotated[LTMService, Depends(get_ltm_service)],
) -> dict:
    settings = get_settings()
    if len(request.memory_ids) > settings.ltm_max_batch_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"Batch size {len(request.memory_ids)} exceeds maximum of {settings.ltm_max_batch_size}"),
        )
    results = await service.batch_delete(request.memory_ids)
    succeeded = sum(1 for r in results if r["success"])
    return {
        "results": results,
        "total": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
    }


@router.get("/memories", response_model=MemoryListResponse)
async def list_memories(
    service: Annotated[LTMService, Depends(get_ltm_service)],
    user_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    limit: int = 100,
) -> dict:
    return await service.get_all(user_id=user_id, agent_id=agent_id, session_id=session_id, limit=limit)


@router.get("/memories/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: str,
    service: Annotated[LTMService, Depends(get_ltm_service)],
) -> dict:
    return await service.get(memory_id)


@router.put("/memories/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: str,
    request: UpdateMemoryRequest,
    service: Annotated[LTMService, Depends(get_ltm_service)],
) -> dict:
    return await service.update(memory_id, request.data)


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    service: Annotated[LTMService, Depends(get_ltm_service)],
) -> dict:
    return await service.delete(memory_id)


@router.get("/memories/{memory_id}/history", response_model=HistoryResponse)
async def get_memory_history(
    memory_id: str,
    service: Annotated[LTMService, Depends(get_ltm_service)],
) -> dict:
    return {"entries": await service.history(memory_id)}
