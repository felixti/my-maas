from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from mem0 import AsyncMemory

    from maas.ltm.models import AddMemoryRequest, SearchMemoryRequest


class LTMService:
    def __init__(self, memory: AsyncMemory, default_ttl_seconds: int = 0):
        self._memory = memory
        self._default_ttl_seconds = default_ttl_seconds

    async def add(self, request: AddMemoryRequest) -> dict:
        metadata = {**(request.metadata or {}), "category": request.category}
        ttl = request.ttl_seconds if request.ttl_seconds is not None else self._default_ttl_seconds
        if ttl > 0:
            metadata["expires_at"] = int(time.time()) + ttl
        return await self._memory.add(
            messages=request.messages,
            user_id=request.user_id,
            agent_id=request.agent_id,
            run_id=request.session_id,
            metadata=metadata,
        )

    @staticmethod
    def _is_expired(item: dict) -> bool:
        expires_at = (item.get("metadata") or {}).get("expires_at")
        if expires_at is None:
            return False
        return int(time.time()) > expires_at

    async def search(self, request: SearchMemoryRequest) -> dict:
        filters: dict[str, object] = {}
        if request.categories:
            filters["category"] = {"in": [category.value for category in request.categories]}
        result = await self._memory.search(
            query=request.query,
            user_id=request.user_id,
            agent_id=request.agent_id,
            run_id=request.session_id,
            limit=request.limit,
            filters=filters if filters else None,
        )
        if "results" in result:
            result["results"] = [r for r in result["results"] if not self._is_expired(r)]
        return result

    async def get(self, memory_id: str) -> dict:
        return cast("dict", await self._memory.get(memory_id))

    async def get_all(
        self,
        user_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> dict:
        result = await self._memory.get_all(
            user_id=user_id,
            agent_id=agent_id,
            run_id=session_id,
            limit=limit,
        )
        if "results" in result:
            result["results"] = [r for r in result["results"] if not self._is_expired(r)]
        return result

    async def _get_all_unfiltered(
        self,
        user_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> dict:
        return await self._memory.get_all(
            user_id=user_id,
            agent_id=agent_id,
            run_id=session_id,
            limit=limit,
        )

    async def delete_expired(self) -> dict:
        all_memories = await self._get_all_unfiltered(limit=10000)
        expired_ids = [m["id"] for m in (all_memories.get("results") or []) if self._is_expired(m)]
        deleted = 0
        for memory_id in expired_ids:
            await self._memory.delete(memory_id)
            deleted += 1
        return {"deleted": deleted, "ids": expired_ids}

    async def update(self, memory_id: str, data: str) -> dict:
        return await self._memory.update(memory_id, data)

    async def delete(self, memory_id: str) -> dict:
        return await self._memory.delete(memory_id)

    async def history(self, memory_id: str) -> list:
        return await self._memory.history(memory_id)

    async def batch_add(self, items: list[AddMemoryRequest]) -> list[dict]:
        async def _safe_add(index: int, item: AddMemoryRequest) -> dict:
            try:
                result = await self.add(item)
                return {"index": index, "success": True, "result": result, "error": None}
            except Exception as exc:
                return {"index": index, "success": False, "result": None, "error": str(exc)}

        tasks = [_safe_add(i, item) for i, item in enumerate(items)]
        return list(await asyncio.gather(*tasks))

    async def batch_search(self, items: list[SearchMemoryRequest]) -> list[dict]:
        async def _safe_search(index: int, item: SearchMemoryRequest) -> dict:
            try:
                result = await self.search(item)
                return {"index": index, "success": True, "result": result, "error": None}
            except Exception as exc:
                return {"index": index, "success": False, "result": None, "error": str(exc)}

        tasks = [_safe_search(i, item) for i, item in enumerate(items)]
        return list(await asyncio.gather(*tasks))

    async def batch_delete(self, memory_ids: list[str]) -> list[dict]:
        async def _safe_delete(index: int, memory_id: str) -> dict:
            try:
                result = await self.delete(memory_id)
                return {"index": index, "success": True, "result": result, "error": None}
            except Exception as exc:
                return {"index": index, "success": False, "result": None, "error": str(exc)}

        tasks = [_safe_delete(i, mid) for i, mid in enumerate(memory_ids)]
        return list(await asyncio.gather(*tasks))
