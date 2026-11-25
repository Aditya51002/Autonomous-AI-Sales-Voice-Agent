"""Voice agent worker.

Run from the project root:  python -m apps.agent.main dev
"""

import asyncio
import json
import logging
import uuid

from dotenv import load_dotenv
from livekit.agents import (
    AgentServer,
    AgentSession,
    ChatMessage,
    ConversationItemAddedEvent,
    ErrorEvent,
    JobContext,
    JobProcess,
    UserInputTranscribedEvent,
    cli,
)
from livekit.agents.vad import VAD
from livekit.plugins import silero

from apps.agent import prompts, providers
from apps.agent.assistant import SalesAssistant
from apps.agent.intelligence import CallerTurn, LiveIntelligence
from apps.agent.latency import stage_latencies
from apps.agent.memory import ConversationMemory
from apps.agent.retrieval import ApiRetriever
from packages.core.config import DISPATCH_NAME, ROOT, Settings, get_settings
from packages.core.leads.store import LeadStore

load_dotenv(ROOT / ".env")
logger = logging.getLogger("sales-agent")


def prewarm(proc: JobProcess) -> None:
    # Load the voice activity model once per process, before any call arrives.
    proc.userdata["vad"] = silero.VAD.load()


def lead_id_from(metadata: str) -> str:
    """The lead id the API placed in the dispatch; a new one if there is none."""
    try:
        lead_id = json.loads(metadata)["lead_id"]
        return uuid.UUID(lead_id).hex
    except (ValueError, KeyError, TypeError, AttributeError):
        return uuid.uuid4().hex


def build_session(settings: Settings, vad: VAD) -> AgentSession:
    return AgentSession(
        stt=providers.build_stt(settings),
        llm=providers.build_llm(settings),
        tts=providers.build_tts(settings),
        # Sarvam decides when a turn ends; the local VAD makes interruption fast.
        vad=vad,
        turn_handling={
            "turn_detection": "stt",
            "endpointing": {"min_delay": settings.endpointing_min_delay},
            "interruption": {
                "mode": "vad",
                "min_duration": settings.interruption_min_duration,
            },
        },
    )


server = AgentServer(setup_fnc=prewarm)


@server.rtc_session(agent_name=DISPATCH_NAME)
async def entrypoint(ctx: JobContext) -> None:
    settings = get_settings()
    session = build_session(settings, ctx.proc.userdata["vad"])
    background: set[asyncio.Task] = set()

    def run_in_background(coro) -> None:
        task = asyncio.create_task(coro)
        background.add(task)
        task.add_done_callback(background.discard)

    async def send(topic: str, payload: str) -> None:
        try:
            await ctx.room.local_participant.publish_data(payload, topic=topic)
        except Exception:
            logger.debug("could not send %s to the page; the call may have ended", topic)

    def publish(topic: str, payload: dict) -> None:
        run_in_background(send(topic, json.dumps(payload)))

    def show_sources(passages: list[dict]) -> None:
        sources = [{"document": p["document"], "score": round(p["score"], 3),
                    "heading": p["content"].split("\n", 1)[0]} for p in passages]
        publish("sources", {"sources": sources})

    retriever = ApiRetriever(settings.api_url, settings.retrieval_timeout, call_id=ctx.room.name)
    ctx.add_shutdown_callback(retriever.aclose)

    analysis_client = providers.build_analysis_client(settings)
    intelligence = LiveIntelligence(
        providers.build_analyzer(settings, analysis_client),
        LeadStore(settings.leads_db),
        call_id=ctx.room.name,
        lead_id=lead_id_from(ctx.job.metadata),
        min_monthly_budget=settings.min_monthly_budget_inr,
        on_update=lambda snapshot: publish("lead", snapshot),
    )
    memory = ConversationMemory(
        providers.build_summarizer(settings, analysis_client), window=settings.memory_window
    )
    assistant = SalesAssistant(
        settings,
        retrieve=retriever,
        on_sources=show_sources,
        intelligence=intelligence,
        memory=memory,
    )
    last_agent_message = ""

    async def close_intelligence() -> None:
        await memory.aclose()
        await intelligence.close()
        await analysis_client.aio.aclose()

    ctx.add_shutdown_callback(close_intelligence)

    @session.on("user_input_transcribed")
    def on_transcript(event: UserInputTranscribedEvent) -> None:
        if event.is_final:
            assistant.note_stt_language(event.language)

    @session.on("conversation_item_added")
    def on_item(event: ConversationItemAddedEvent) -> None:
        nonlocal last_agent_message
        item = event.item
        if not isinstance(item, ChatMessage):
            return
        if text := item.text_content:
            speaker = "caller" if item.role == "user" else "agent"
            run_in_background(
                intelligence.record(item.id, speaker, text, assistant.language.value)
            )
            if item.role == "user":
                intelligence.submit(CallerTurn(item.id, text, last_agent_message))
            else:
                last_agent_message = text
        stages = stage_latencies(item.role, item.metrics)
        if not stages:
            return
        # Timings only: transcripts are not written to the logs.
        logger.info("latency %s %s", item.role, stages)
        payload = {"role": item.role, "language": assistant.language.value, **stages}
        publish("latency", payload)

    @session.on("error")
    def on_error(event: ErrorEvent) -> None:
        logger.error("pipeline error from %s: %s", type(event.source).__name__, event.error)

    async def enforce_call_limit() -> None:
        await asyncio.sleep(settings.max_call_seconds)
        await session.say(prompts.CALL_LIMIT_MESSAGE, allow_interruptions=False)
        await ctx.delete_room()

    # Connect first so the lead panel can receive the earlier facts.
    await ctx.connect()
    await intelligence.start()
    await session.start(agent=assistant, room=ctx.room)
    publish("lead", intelligence.snapshot())
    limit_task = asyncio.create_task(enforce_call_limit())

    async def stop_limit_timer() -> None:
        limit_task.cancel()

    ctx.add_shutdown_callback(stop_limit_timer)


if __name__ == "__main__":
    get_settings().require(
        "livekit_url",
        "livekit_api_key",
        "livekit_api_secret",
        "sarvam_api_key",
        "gemini_api_key",
    )
    cli.run_app(server)
