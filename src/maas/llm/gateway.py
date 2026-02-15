from __future__ import annotations

from typing import TYPE_CHECKING

from openai import AsyncOpenAI

if TYPE_CHECKING:
    from maas.config import Settings


def create_llm_client(settings: Settings) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.resolved_llm_base_url,
    )
