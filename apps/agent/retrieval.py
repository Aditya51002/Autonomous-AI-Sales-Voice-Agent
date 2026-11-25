"""Fetches document passages for the caller's latest turn.

The embedding model runs once, in the API process, so agent processes stay light.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import aiohttp

logger = logging.getLogger("sales-agent")

Passages = list[dict]
Retriever = Callable[[str], Awaitable[Passages | None]]

# Acknowledgements and greetings that never need a document search.
_SMALL_TALK = frozenset(
    "ok okay yes no yeah hmm hello hi hey thanks thank you bye goodbye sure fine great "
    "haan han ji nahi achha accha theek namaste dhanyavaad shukriya "
    "हाँ हां जी नहीं अच्छा ठीक है नमस्ते धन्यवाद शुक्रिया".split()
)


def is_small_talk(text: str) -> bool:
    words = [word.strip(".,!?।").lower() for word in text.split()]
    return all(word in _SMALL_TALK or not word for word in words)


class ApiRetriever:
    def __init__(self, api_url: str, timeout: float, call_id: str | None = None) -> None:
        self._url = f"{api_url.rstrip('/')}/search"
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._call_id = call_id
        self._session: aiohttp.ClientSession | None = None

    async def __call__(self, query: str) -> Passages | None:
        """Passages (possibly none), or None if the search itself failed."""
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        payload = {"query": query[:1000], "call_id": self._call_id}
        try:
            async with self._session.post(self._url, json=payload) as response:
                response.raise_for_status()
                return (await response.json())["passages"]
        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, ValueError) as error:
            # The conversation continues; the agent will not claim any facts.
            logger.warning("document search failed: %s", type(error).__name__)
            return None

    async def aclose(self) -> None:
        if self._session is not None:
            await self._session.close()
