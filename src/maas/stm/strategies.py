from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from maas.config import STMStrategy
from maas.stm.models import ContextResponse, Message, MessageRole, StoredMessage

if TYPE_CHECKING:
    from maas.config import Settings
    from maas.stm.store import MessageStore


class WindowStrategy(ABC):
    @abstractmethod
    async def apply(
        self,
        store: MessageStore,
        session_id: str,
        llm_client: Any,
        settings: Settings,
    ) -> ContextResponse: ...


class SlidingWindowStrategy(WindowStrategy):
    async def apply(
        self,
        store: MessageStore,
        session_id: str,
        llm_client: Any,
        settings: Settings,
    ) -> ContextResponse:
        _ = llm_client
        messages = await store.get_messages(session_id, limit=settings.stm_max_messages)
        total_tokens = sum(message.token_count for message in messages)
        return ContextResponse(
            session_id=session_id,
            messages=messages,
            strategy=STMStrategy.SLIDING_WINDOW,
            total_tokens=total_tokens,
        )


class TokenThresholdStrategy(WindowStrategy):
    def _format_messages(self, messages: list[StoredMessage]) -> str:
        return "\n".join(f"{message.role}: {message.content}" for message in messages)

    async def apply(
        self,
        store: MessageStore,
        session_id: str,
        llm_client: Any,
        settings: Settings,
    ) -> ContextResponse:
        messages = await store.get_messages(session_id)
        total_tokens = sum(message.token_count for message in messages)
        if total_tokens <= settings.stm_max_tokens:
            return ContextResponse(
                session_id=session_id,
                messages=messages,
                strategy=STMStrategy.TOKEN_THRESHOLD,
                total_tokens=total_tokens,
            )

        if not messages:
            return ContextResponse(
                session_id=session_id,
                messages=[],
                strategy=STMStrategy.TOKEN_THRESHOLD,
                total_tokens=0,
            )

        split_index = max(1, int(len(messages) * 0.6))
        to_summarize = messages[:split_index]
        remaining = messages[split_index:]
        summary_prompt = self._format_messages(to_summarize)

        response = await llm_client.chat.completions.create(
            model=settings.resolved_stm_summarization_model,
            messages=[
                {
                    "role": "system",
                    "content": "Summarize the following conversation concisely while preserving key facts.",
                },
                {"role": "user", "content": summary_prompt},
            ],
            temperature=settings.llm_temperature,
        )
        summary_text = response.choices[0].message.content or ""
        summary_message = Message(role=MessageRole.SUMMARY, content=summary_text)
        new_messages = [
            summary_message,
            *[Message(role=message.role, content=message.content, metadata=message.metadata) for message in remaining],
        ]
        await store.replace_messages(session_id, new_messages)
        stored_messages = await store.get_messages(session_id)
        total_tokens = sum(message.token_count for message in stored_messages)
        return ContextResponse(
            session_id=session_id,
            messages=stored_messages,
            strategy=STMStrategy.TOKEN_THRESHOLD,
            total_tokens=total_tokens,
        )


def get_strategy(strategy_name: STMStrategy) -> WindowStrategy:
    if strategy_name == STMStrategy.TOKEN_THRESHOLD:
        return TokenThresholdStrategy()
    return SlidingWindowStrategy()
