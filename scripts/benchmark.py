"""Phase 0: measure LLM and TTS latency with your own keys.

Run from the project root:  python -m scripts.benchmark --runs 5

This makes real, billed API calls (a few short requests per run).
STT latency is measured during live calls and shown on the web page.
"""

import argparse
import asyncio
import statistics
import time

from livekit.agents import llm, utils

from apps.agent import prompts, providers
from apps.agent.language import Language
from packages.core.config import get_settings

QUESTIONS = {
    Language.ENGLISH: "We spend too long making invoices by hand. Can you help?",
    Language.HINDI: "हम हाथ से बिल बनाते हैं और बहुत समय लगता है। क्या आप मदद कर सकती हैं?",
    Language.HINGLISH: "हमारी team manually invoice बनाती है, क्या आप help कर सकती हो?",
}


async def time_llm(model: llm.LLM, instructions: str, question: str) -> tuple[float, str]:
    chat_ctx = llm.ChatContext.empty()
    chat_ctx.add_message(role="system", content=instructions)
    chat_ctx.add_message(role="user", content=question)
    started, first, parts = time.perf_counter(), None, []
    async with model.chat(chat_ctx=chat_ctx) as stream:
        async for chunk in stream:
            if chunk.delta and chunk.delta.content:
                first = first or time.perf_counter() - started
                parts.append(chunk.delta.content)
    if first is None:
        raise RuntimeError("the model returned no text")
    return first, "".join(parts)


async def time_tts(speech, text: str) -> float:
    started = time.perf_counter()
    async with speech.stream() as stream:
        stream.push_text(text)
        stream.end_input()
        async for _ in stream:
            return time.perf_counter() - started
    raise RuntimeError("the speech service returned no audio")


def report(name: str, samples: list[float]) -> None:
    ms = sorted(s * 1000 for s in samples)
    print(f"{name:28s} median {statistics.median(ms):7.0f} ms   worst {ms[-1]:7.0f} ms")


async def main(runs: int) -> None:
    settings = get_settings()
    settings.require("sarvam_api_key", "gemini_api_key")
    print(f"LLM {settings.llm_model} | TTS {settings.tts_model} | {runs} runs per language\n")
    async with utils.http_context.open():
        model = providers.build_llm(settings)
        speech = providers.build_tts(settings)
        try:
            for language, question in QUESTIONS.items():
                speech.update_options(target_language_code=language.tts_code)
                llm_times, tts_times = [], []
                for _ in range(runs):
                    first_token, reply = await time_llm(
                        model, prompts.instructions(settings), question
                    )
                    llm_times.append(first_token)
                    tts_times.append(await time_tts(speech, reply))
                report(f"{language.value}: LLM first token", llm_times)
                report(f"{language.value}: TTS first audio", tts_times)
                print(f"  sample reply: {reply}\n")
        finally:
            await speech.aclose()
            await model.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    asyncio.run(main(parser.parse_args().runs))
