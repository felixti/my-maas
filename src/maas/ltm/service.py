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
        raw = await self._memory.add(
            messages=request.messages,
            user_id=request.user_id,
            agent_id=request.agent_id,
            run_id=request.session_id,
            metadata=metadata,
        )
        # mem0 >= 1.0 returns {"results": [{"id": ..., "memory": ..., "event": ...}]}.
        # Unwrap so callers receive a flat single-memory dict.
        # An empty results list means mem0 detected a duplicate — nothing new was stored.
        if isinstance(raw, dict) and "results" in raw:
            if raw["results"]:
                return raw["results"][0]
            return {"id": None, "memory": "", "event": "NOOP"}
        return raw

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

    async def update(self, memory_id: str, data: str) -> dict:
        await self._memory.update(memory_id, data)
        # mem0's update() only returns {"message": "..."}, so re-fetch
        # the full memory to satisfy the MemoryResponse contract.
        return await self.get(memory_id)

    async def delete_expired(self) -> dict:
        """Delete all memories whose ``expires_at`` timestamp has passed.

        We bypass ``mem0.get_all()`` (which requires a scope filter) and
        query the underlying vector store directly for documents that
        carry an ``expires_at`` payload field in the past.
        """
        now = int(time.time())
        try:
            # Access the vector store directly — it's a pymongo-backed store.
            vs = self._memory.vector_store
            cursor = vs.collection.find(
                {"payload.expires_at": {"$lte": now}},
                {"_id": 1},
            )
            expired_ids: list[str] = [str(doc["_id"]) for doc in cursor]
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Failed to query expired memories from vector store")
            expired_ids = []

        deleted = 0
        for memory_id in expired_ids:
            await self._memory.delete(memory_id)
            deleted += 1
        return {"deleted": deleted, "ids": expired_ids}

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
