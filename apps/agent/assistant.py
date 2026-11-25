"""The conversational agent: greeting, language, memory and document grounding."""

import logging
from collections.abc import AsyncIterator, Callable

from livekit.agents import Agent, ModelSettings, llm

from apps.agent import prompts
from apps.agent.intelligence import LiveIntelligence
from apps.agent.language import Language, LanguageTracker
from apps.agent.memory import ConversationMemory
from apps.agent.retrieval import Passages, Retriever, is_small_talk
from packages.core.config import Settings

logger = logging.getLogger("sales-agent")


class SalesAssistant(Agent):
    def __init__(
        self,
        settings: Settings,
        retrieve: Retriever | None = None,
        on_sources: Callable[[Passages], None] | None = None,
        intelligence: LiveIntelligence | None = None,
        memory: ConversationMemory | None = None,
    ) -> None:
        super().__init__(instructions=prompts.instructions(settings))
        self._settings = settings
        self._retrieve = retrieve
        self._on_sources = on_sources
        self._intelligence = intelligence
        self._memory = memory
        self._last_search: tuple[str, Passages | None] | None = None
        self._language = LanguageTracker()
        self._stt_language: str | None = None

    @property
    def language(self) -> Language:
        return self._language.current

    def note_stt_language(self, code: str | None) -> None:
        """Record the language the STT reported for the latest final transcript."""
        self._stt_language = code

    async def on_enter(self) -> None:
        # Fixed text: no LLM delay, and the AI disclosure is always said.
        self.session.say(prompts.greeting(self._settings))

    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        # Runs before the reply is synthesised, so the voice matches this turn.
        previous = self._language.current
        current = self._language.update(new_message.text_content or "", self._stt_language)
        if current.tts_code != previous.tts_code:
            self.session.tts.update_options(target_language_code=current.tts_code)
        if current != previous:
            logger.info("language changed", extra={"from": previous.value, "to": current.value})

    async def llm_node(
        self, chat_ctx: llm.ChatContext, tools: list[llm.Tool], model_settings: ModelSettings
    ) -> AsyncIterator[llm.ChatChunk]:
        # Done here, not as an LLM tool call, to avoid a second model round trip.
        prepared = await self.prepare_turn(chat_ctx)
        async for chunk in Agent.default.llm_node(self, prepared, tools, model_settings):
            yield chunk

    async def prepare_turn(self, chat_ctx: llm.ChatContext) -> llm.ChatContext:
        """A copy of the context with memory, language and passages for this turn.

        The stored history is not changed, so old passages do not pile up in the prompt.
        """
        messages = [item for item in chat_ctx.items if item.type == "message"]
        if not messages or messages[-1].role != "user":
            return chat_ctx
        question = messages[-1].text_content or ""
        if not question.strip():
            return chat_ctx
        # This can run before the turn is confirmed, so the tracker is not changed here.
        language = self._language.preview(question, self._stt_language)

        passages = None
        if self._retrieve is not None and not is_small_talk(question):
            found = await self._search(self._search_query(question, messages[:-1]))
            if found is not None and self._on_sources:
                self._on_sources(found)
            passages = found or []

        compacted = self._memory.compact(chat_ctx) if self._memory else chat_ctx
        prepared = compacted.copy()
        index = prepared.index_by_id(messages[-1].id)
        context = prompts.turn_context(
            language,
            passages,
            summary=self._memory.summary if self._memory else "",
            guidance=self._intelligence.guidance() if self._intelligence else "",
        )
        prepared.items[index] = messages[-1].model_copy(
            update={"content": [context, *messages[-1].content]}
        )
        return prepared

    @staticmethod
    def _search_query(question: str, earlier: list[llm.ChatMessage]) -> str:
        """Short follow-ups ("and the yearly one?") need the previous question."""
        if len(question.split()) > 5:
            return question
        previous = next((m for m in reversed(earlier) if m.role == "user"), None)
        return f"{previous.text_content} {question}" if previous else question

    async def _search(self, query: str) -> Passages | None:
        # A preemptive reply and the confirmed reply ask the same thing; search once.
        if self._last_search and self._last_search[0] == query:
            return self._last_search[1]
        passages = await self._retrieve(query)
        if passages is not None:
            self._last_search = (query, passages)
        return passages
