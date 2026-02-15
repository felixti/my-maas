from __future__ import annotations

import pytest

from maas.ltm.models import AddMemoryRequest, MemoryCategory, SearchMemoryRequest


@pytest.mark.unit
def test_memory_category_values() -> None:
    assert MemoryCategory.SEMANTIC.value == "semantic"
    assert MemoryCategory.EPISODIC.value == "episodic"
    assert MemoryCategory.FACT.value == "fact"
    assert MemoryCategory.PREFERENCE.value == "preference"


@pytest.mark.unit
def test_add_memory_requires_scope() -> None:
    with pytest.raises(ValueError, match="At least one of user_id, agent_id, or session_id must be provided"):
        AddMemoryRequest(messages="hello", category=MemoryCategory.SEMANTIC)


@pytest.mark.unit
def test_search_memory_requires_scope() -> None:
    with pytest.raises(ValueError, match="At least one of user_id, agent_id, or session_id must be provided"):
        SearchMemoryRequest(query="q")


@pytest.mark.unit
def test_add_memory_serialization() -> None:
    request = AddMemoryRequest(
        messages="hello",
        category=MemoryCategory.FACT,
        user_id="user-1",
        metadata={"source": "chat"},
    )
    payload = request.model_dump()
    assert payload["category"] == MemoryCategory.FACT
    assert payload["metadata"]["source"] == "chat"
    assert payload["user_id"] == "user-1"
