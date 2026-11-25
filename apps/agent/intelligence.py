"""The slow path: analyses caller turns while the conversation continues.

Turns are queued and handled one batch at a time in the background. A reply
never waits for this, and a failure here never stops the call.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass

from packages.core.leads.models import Extraction, LeadFacts
from packages.core.leads.scoring import score_lead
from packages.core.leads.state import merge, needs_follow_up
from packages.core.leads.store import LeadStore

logger = logging.getLogger("sales-agent")

Analyzer = Callable[[str], Awaitable[Extraction]]

# Failed turns are analysed again with the next one, up to this many.
MAX_RETRY_TURNS = 10

_NEXT_QUESTION = {
    "need": "what problem they want to solve",
    "timeline": "when they would like to start",
    "authority": "who decides on this purchase",
    "budget": "what monthly budget they have in mind",
}


@dataclass(frozen=True)
class CallerTurn:
    id: str
    text: str
    agent_said: str  # what the agent said just before, so "yes" can be understood


class LiveIntelligence:
    def __init__(
        self,
        analyze: Analyzer,
        store: LeadStore,
        call_id: str,
        lead_id: str,
        min_monthly_budget: int,
        on_update: Callable[[dict], None] | None = None,
    ) -> None:
        self._analyze = analyze
        self._store = store
        self._call_id = call_id
        self._lead_id = lead_id
        self._min_budget = min_monthly_budget
        self._on_update = on_update
        self._queue: asyncio.Queue[CallerTurn] = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self._writes: asyncio.Lock = asyncio.Lock()
        self._retry: list[CallerTurn] = []  # turns whose analysis failed
        self.facts = LeadFacts()
        self.sentiments: list[str] = []
        self.latest_reason = ""
        self.returning = False

    @property
    def score(self):
        return score_lead(self.facts, self._min_budget)

    async def start(self) -> None:
        self.facts = await asyncio.to_thread(
            self._store.start_call, self._call_id, self._lead_id
        )
        self.returning = self.facts != LeadFacts()
        self._worker = asyncio.create_task(self._run())
        self._publish()

    async def record(self, turn_id: str, speaker: str, text: str, language: str) -> None:
        """Save one turn of the transcript."""
        try:
            async with self._writes:  # keeps turns in the order they were spoken
                await asyncio.to_thread(
                    self._store.add_turn, turn_id, self._call_id, speaker, text, language
                )
        except Exception:
            logger.exception("could not save a transcript turn")

    def submit(self, turn: CallerTurn) -> None:
        self._queue.put_nowait(turn)

    async def close(self, timeout: float = 7.0) -> None:
        """Finish pending analysis, then mark the call ended."""
        if self._worker is None:
            return
        try:
            await asyncio.wait_for(self._drain(), timeout)
        except asyncio.TimeoutError:
            logger.warning("analysis did not finish before the call closed")
        except Exception as error:
            logger.warning("final turn analysis failed: %s", type(error).__name__)
        self._worker.cancel()
        async with self._writes:
            await asyncio.to_thread(self._store.end_call, self._call_id)

    async def _drain(self) -> None:
        await self._queue.join()
        if self._retry:  # one last attempt for anything that failed
            turns, self._retry = self._retry, []
            await self._process(turns)

    def guidance(self) -> str:
        """Notes for the next reply: known facts, one thing to learn, and mood."""
        lines = []
        known = [
            f"{label}: {value}"
            for label, value in (
                ("name", self.facts.name),
                ("company", self.facts.company),
                ("need", self.facts.need and self.facts.need.detail),
                ("budget", self.facts.budget and self.facts.budget.detail),
                ("decision role", self.facts.authority and self.facts.authority.detail),
                ("timeline", self.facts.timeline and self.facts.timeline.detail),
                ("concerns", "; ".join(self.facts.objections)),
            )
            if value
        ]
        if known:
            source = " (some from an earlier call)" if self.returning else ""
            lines.append(f"Already known about the caller{source}, so do not ask again:")
            lines.extend(f"- {item}" for item in known)
        if missing := self.score.missing:
            lines.append(
                f"If it fits naturally after answering, ask {_NEXT_QUESTION[missing[0]]}."
            )
        if self.sentiments and self.sentiments[-1] == "negative":
            lines.append(
                f"The caller sounds unhappy ({self.latest_reason}). "
                "Acknowledge it before anything else and do not push."
            )
        return "\n".join(lines)

    def snapshot(self) -> dict:
        return {
            "facts": self.facts.model_dump(),
            "score": asdict(self.score),
            "sentiments": self.sentiments[-20:],
            "sentiment_reason": self.latest_reason,
            "follow_up": needs_follow_up(self.sentiments),
            "returning": self.returning,
        }

    def _publish(self) -> None:
        if self._on_update:
            self._on_update(self.snapshot())

    async def _run(self) -> None:
        while True:
            batch = [await self._queue.get()]
            # Turns that arrived during the last request are analysed together.
            while not self._queue.empty():
                batch.append(self._queue.get_nowait())
            turns, self._retry = self._retry + batch, []
            try:
                await self._process(turns)
            except Exception as error:
                # Only the type is logged: messages can contain what the caller said.
                logger.warning("turn analysis failed: %s", type(error).__name__)
                self._retry = turns[-MAX_RETRY_TURNS:]
            finally:
                for _ in batch:
                    self._queue.task_done()

    async def _process(self, batch: list[CallerTurn]) -> None:
        caller_text = "\n".join(turn.text for turn in batch)
        request = json.dumps(
            {
                "agent_said_before": batch[0].agent_said,
                "caller_new_message": caller_text,
                "already_known": self.facts.model_dump(exclude_none=True),
            },
            ensure_ascii=False,
        )
        found = await self._analyze(request)
        self.facts, _ = merge(self.facts, found, caller_text)
        self.sentiments.append(found.sentiment.label)
        self.latest_reason = found.sentiment.reason[:80]
        score = self.score
        async with self._writes:
            await asyncio.to_thread(
                self._store.save_analysis,
                self._call_id,
                self._lead_id,
                self.facts,
                score.total,
                score.grade,
                needs_follow_up(self.sentiments),
                [turn.id for turn in batch],
                found.sentiment.label,
                self.latest_reason,
            )
        self._publish()
