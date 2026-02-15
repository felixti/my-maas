from __future__ import annotations

from typing import TYPE_CHECKING

from openai import AsyncAzureOpenAI, AsyncOpenAI

from maas.config import LLMProvider

if TYPE_CHECKING:
    from maas.config import Settings


def create_llm_client(settings: Settings) -> AsyncOpenAI:
    if settings.llm_provider == LLMProvider.AZURE_OPENAI:
        return AsyncAzureOpenAI(
            api_key=settings.llm_api_key,
            azure_endpoint=settings.azure_endpoint,
            azure_deployment=settings.llm_model,
            api_version=settings.llm_api_version,
        )
    return AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.resolved_llm_base_url,
    )
