from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(StrEnum):
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    GROK = "grok"
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"
    KIMI = "kimi"
    GLM = "glm"
    MINIMAX = "minimax"
    TOGETHER = "together"
    DEEPSEEK = "deepseek"


class EmbeddingProvider(StrEnum):
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    COHERE = "cohere"
    HUGGINGFACE = "huggingface"
    FASTEMBED = "fastembed"
    OLLAMA = "ollama"


class STMStrategy(StrEnum):
    SLIDING_WINDOW = "sliding_window"
    TOKEN_THRESHOLD = "token_threshold"  # noqa: S105


class VectorStoreProvider(StrEnum):
    MONGODB = "mongodb"
    AZURE_DOCUMENTDB = "azure_documentdb"


class VectorIndexType(StrEnum):
    DISKANN = "diskann"
    HNSW = "hnsw"


PROVIDER_BASE_URLS: dict[LLMProvider, str] = {
    LLMProvider.OPENAI: "https://api.openai.com/v1",
    LLMProvider.GROK: "https://api.x.ai/v1",
    LLMProvider.ANTHROPIC: "https://api.anthropic.com/v1",
    LLMProvider.OPENROUTER: "https://openrouter.ai/api/v1",
    LLMProvider.KIMI: "https://api.moonshot.cn/v1",
    LLMProvider.GLM: "https://open.bigmodel.cn/api/paas/v4",
    LLMProvider.MINIMAX: "https://api.minimax.chat/v1",
    LLMProvider.TOGETHER: "https://api.together.xyz/v1",
    LLMProvider.DEEPSEEK: "https://api.deepseek.com/v1",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: LLMProvider = LLMProvider.OPENAI
    llm_api_key: str = Field(default="")
    llm_model: str = "gpt-4.1-mini"
    llm_base_url: str = ""
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096
    llm_api_version: str = "2024-10-21"
    azure_endpoint: str = ""

    embedding_provider: EmbeddingProvider = EmbeddingProvider.OPENAI
    embedding_api_key: str = Field(default="")
    embedding_model: str = "text-embedding-3-small"
    embedding_base_url: str = ""
    embedding_dims: int = 1536
    embedding_api_version: str = "2024-10-21"

    redis_url: str = "redis://localhost:6379"
    stm_default_strategy: STMStrategy = STMStrategy.SLIDING_WINDOW
    stm_max_messages: int = 50
    stm_max_tokens: int = 8000
    stm_summarization_model: str = ""
    stm_session_ttl_seconds: int = 86400
    ltm_default_ttl_seconds: int = 0  # 0 = no expiration
    ltm_max_batch_size: int = 50

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "maas"
    mongodb_collection_name: str = "memories"
    vector_store_provider: VectorStoreProvider = VectorStoreProvider.MONGODB
    vector_index_type: VectorIndexType = Field(
        default=VectorIndexType.DISKANN,
        description="Vector index type: diskann or hnsw",
    )

    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    otel_service_name: str = "my-maas"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "http://localhost:3000"

    @property
    def resolved_llm_base_url(self) -> str:
        if self.llm_base_url:
            return self.llm_base_url
        return PROVIDER_BASE_URLS.get(self.llm_provider, PROVIDER_BASE_URLS[LLMProvider.OPENAI])

    @property
    def resolved_stm_summarization_model(self) -> str:
        return self.stm_summarization_model or self.llm_model


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
