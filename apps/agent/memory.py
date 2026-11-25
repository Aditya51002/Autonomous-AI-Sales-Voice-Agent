"""Keeps the prompt a bounded size on long calls.

Recent messages are sent as they are. Older ones are summarised in the
background and dropped from the request only once the summary covers them.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from livekit.agents import llm

logger = logging.getLogger("sales-agent")

Summarizer = Callable[[str], Awaitable[str]]

# Summarise once this many messages have aged out of the recent window.
BATCH = 6


class ConversationMemory:
    def __init__(self, summarize: Summarizer | None, window: int = 12) -> None:
        self._summarize = summarize
        self._window = window
        self._covered: set[str] = set()
        self._task: asyncio.Task | None = None
        self.summary = ""

    def compact(self, chat_ctx: llm.ChatContext) -> llm.ChatContext:
        """The context to send: instructions and messages not yet summarised."""
        messages = [
            m for m in chat_ctx.items if m.type == "message" and m.role in ("user", "assistant")
        ]
        older = [m for m in messages[: -self._window] if m.id not in self._covered]
        if self._summarize and len(older) >= BATCH and (self._task is None or self._task.done()):
            self._task = asyncio.create_task(self._extend_summary(older))
        if not self._covered:
            return chat_ctx
        compacted = chat_ctx.copy()
        compacted.items[:] = [item for item in compacted.items if item.id not in self._covered]
        return compacted

    async def _extend_summary(self, messages: list[llm.ChatMessage]) -> None:
        lines = "\n".join(
            f"{'Caller' if m.role == 'user' else 'Agent'}: {m.text_content}" for m in messages
        )
        try:
            summary = await self._summarize(
                f"Summary so far:\n{self.summary or '(none)'}\n\nNew conversation:\n{lines}"
            )
        except Exception as error:
            logger.warning("summary failed: %s", type(error).__name__)
            return  # the messages stay in the prompt and are retried later
        if summary.strip():
            self.summary = summary.strip()
            self._covered.update(m.id for m in messages)

    async def aclose(self) -> None:
        if self._task:
            self._task.cancel()
