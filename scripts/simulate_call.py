"""Places a real call with a synthetic caller and reports what happened.

Start the LiveKit server, API and agent first, then run from the project root:
    python -m scripts.simulate_call
Uses billed Sarvam and Gemini requests. It checks the pipeline, not how real
people sound: synthetic speech is clearer than a microphone in a noisy room.
"""

import asyncio
import json
import time

import aiohttp
from livekit import rtc
from livekit.agents import utils
from livekit.plugins import sarvam

from packages.core.config import get_settings

API = "http://127.0.0.1:8000"
RATE = 22050
CHUNK = RATE // 50  # 20 ms

# (what the caller says, language code, interrupt the reply to this turn?)
TURNS = [
    ("Hi, I am Priya from Sharma Traders. Making invoices by hand takes us two days.", "en-IN", False),
    ("Growth plan की कीमत कितनी है, और उसमें क्या क्या मिलता है?", "hi-IN", True),
    ("रुकिए, क्या yearly payment पर कोई discount मिलता है?", "hi-IN", False),
    ("I am the owner, we want to start next month, and our budget is two thousand rupees a month.", "en-IN", False),
]


async def synthesize(speech: sarvam.TTS, text: str, language: str) -> bytes:
    speech.update_options(target_language_code=language)
    audio = bytearray()
    async with speech.stream() as stream:
        stream.push_text(text)
        stream.end_input()
        async for event in stream:
            audio += bytes(event.frame.data)
    return bytes(audio)


class Caller:
    def __init__(self) -> None:
        self.room = rtc.Room()
        self.pending = bytearray()
        self.state = ""
        self.started = time.monotonic()
        self.events: list[tuple[float, str]] = []
        self.lines: dict[str, tuple[str, str]] = {}
        self.latency: list[dict] = []
        self.sources: list[dict] = []
        self.lead: dict = {}
        self.tasks: set[asyncio.Task] = set()

    def log(self, text: str) -> None:
        print(f"[{time.monotonic() - self.started:6.1f}s] {text}", flush=True)

    async def connect(self, url: str, token: str) -> None:
        self.room.on("participant_attributes_changed", self._attributes)
        self.room.on("data_received", self._data)
        self.room.register_text_stream_handler("lk.transcription", self._transcript)
        await self.room.connect(url, token)
        self.source = rtc.AudioSource(RATE, 1)
        track = rtc.LocalAudioTrack.create_audio_track("mic", self.source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await self.room.local_participant.publish_track(track, options)
        self._spawn(self._microphone())

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _microphone(self) -> None:
        """Streams queued speech, and silence in between, like an open microphone."""
        size = CHUNK * 2
        while True:
            data = bytes(self.pending[:size]).ljust(size, b"\0")
            del self.pending[:size]
            await self.source.capture_frame(rtc.AudioFrame(data, RATE, 1, CHUNK))

    def _attributes(self, changed, participant) -> None:
        if state := changed.get("lk.agent.state"):
            self.state = state
            self.events.append((time.monotonic(), state))
            self.log(f"agent is {state}")

    def _data(self, packet: rtc.DataPacket) -> None:
        payload = json.loads(packet.data)
        if packet.topic == "latency":
            self.latency.append(payload)
        elif packet.topic == "sources":
            self.sources = payload["sources"]
        elif packet.topic == "lead":
            self.lead = payload

    def _transcript(self, reader: rtc.TextStreamReader, sender: str) -> None:
        async def read() -> None:
            key = (reader.info.attributes or {}).get("lk.segment_id", reader.info.stream_id)
            speaker = "caller" if sender == self.room.local_participant.identity else "agent"
            text = ""
            async for chunk in reader:
                text += chunk
                self.lines[key] = (speaker, text)

        self._spawn(read())

    async def wait_for(self, state: str, since: float, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if any(t >= since and s == state for t, s in self.events):
                return True
            await asyncio.sleep(0.05)
        self.log(f"timed out waiting for the agent to be {state}")
        return False

    async def wait_until_quiet(self, quiet: float = 2.5, timeout: float = 45) -> None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            changed = self.events[-1][0] if self.events else self.started
            if self.state == "listening" and time.monotonic() - changed >= quiet:
                return
            await asyncio.sleep(0.1)

    async def speak(self, audio: bytes) -> float:
        """Plays the audio and returns the time the caller stopped speaking."""
        self.pending += audio
        while self.pending:
            await asyncio.sleep(0.02)
        return time.monotonic()


async def main() -> None:
    settings = get_settings()
    settings.require("sarvam_api_key")
    async with utils.http_context.open():
        speech = sarvam.TTS(
            target_language_code="en-IN",
            model=settings.tts_model,
            speaker="shubh_enhi_companion",
            api_key=settings.sarvam_api_key,
        )
        print("preparing the caller's audio...", flush=True)
        clips = [await synthesize(speech, text, language) for text, language, _ in TURNS]
        await speech.aclose()

        async with aiohttp.ClientSession() as http:
            async with http.post(f"{API}/calls", json={"consent": True}) as response:
                response.raise_for_status()
                call = await response.json()

            caller = Caller()
            await caller.connect(call["url"], call["token"])
            try:
                if not await caller.wait_for("speaking", caller.started, 30):
                    return
                await caller.wait_until_quiet()

                interrupting = False
                for (text, _, interrupt), audio in zip(TURNS, clips):
                    caller.log(f"CALLER: {text}")
                    began = time.monotonic()
                    done = await caller.speak(audio)
                    if interrupting:
                        stopped = [t for t, s in caller.events if t >= began and s != "speaking"]
                        if stopped:
                            caller.log(f"agent stopped {stopped[0] - began:.1f}s after the interruption began")
                    if await caller.wait_for("speaking", done, 40):
                        first = next(t for t, s in caller.events if t >= done and s == "speaking")
                        caller.log(f"reply audio began {first - done:.1f}s after the caller finished")
                    interrupting = interrupt
                    if interrupt:
                        await asyncio.sleep(2.0)  # talk over the reply
                        caller.log(f"interrupting while the agent is {caller.state}")
                    else:
                        await caller.wait_until_quiet()
                await asyncio.sleep(8)  # let the background analysis finish
            finally:
                print("\nTRANSCRIPT")
                for speaker, text in caller.lines.values():
                    print(f"  {speaker}: {text}")
                print("\nLATENCY (ms)")
                for row in caller.latency:
                    print(f"  {row}")
                print("\nLAST SOURCES:", [s["heading"] for s in caller.sources])
                if caller.lead:
                    print("LEAD:", caller.lead["score"]["grade"], caller.lead["score"]["total"],
                          caller.lead["score"]["points"])
                    print("FACTS:", {k: (v["detail"] if isinstance(v, dict) else v)
                                     for k, v in caller.lead["facts"].items() if v})
                    print("SENTIMENT:", caller.lead["sentiments"])
                await caller.room.disconnect()
                for task in list(caller.tasks):
                    task.cancel()
                # The test caller is not a real lead.
                await asyncio.sleep(10)
                await http.delete(f"{API}/leads/{call['lead_id']}")


if __name__ == "__main__":
    asyncio.run(main())
