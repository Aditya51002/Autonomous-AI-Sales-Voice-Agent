"""The only module that knows which vendors are used.

To change STT, TTS or LLM provider, change the factory functions here.
"""

from google import genai
from google.genai import types
from livekit.agents import llm
from livekit.plugins import google, sarvam

from apps.agent import prompts
from apps.agent.intelligence import Analyzer
from apps.agent.language import Language
from apps.agent.memory import Summarizer
from packages.core.config import Settings
from packages.core.leads.models import Extraction


def low_latency_thinking(model: str) -> dict[str, str | int] | None:
    """The thinking setting that gets a Gemini model speaking soonest.

    The accepted values differ by model, so sending the wrong one is a 400 error.
    """
    if model.startswith("gemini-3"):
        # Flash-Lite can go down to "minimal"; the larger models start at "low".
        return {"thinking_level": "minimal" if "flash-lite" in model else "low"}
    if model.startswith("gemini-2.5-flash"):
        return {"thinking_budget": 0}
    return None


def build_llm(settings: Settings) -> llm.LLM:
    if not settings.llm_model.startswith("gemini"):
        raise ValueError(
            f"LLM_MODEL is '{settings.llm_model}', but this project uses Google Gemini. "
            "Set it to a Gemini model such as gemini-3.5-flash-lite in .env."
        )
    options: dict = {}
    if thinking := low_latency_thinking(settings.llm_model):
        options["thinking_config"] = thinking
    return google.LLM(
        model=settings.llm_model,
        api_key=settings.gemini_api_key,
        # On Gemini this limit includes any thinking tokens.
        max_output_tokens=settings.llm_max_tokens,
        **options,
    )


def _text_config(model: str, instructions: str, **options) -> types.GenerateContentConfig:
    if thinking := low_latency_thinking(model):
        options["thinking_config"] = types.ThinkingConfig.model_validate(thinking)
    return types.GenerateContentConfig(system_instruction=instructions, **options)


def build_analyzer(settings: Settings, client: genai.Client) -> Analyzer:
    """Structured extraction of lead facts and sentiment."""
    model = settings.analysis_model
    config = _text_config(
        model,
        prompts.ANALYSIS_INSTRUCTIONS,
        response_mime_type="application/json",
        response_schema=Extraction,
        max_output_tokens=1500,
    )

    async def analyze(request: str) -> Extraction:
        response = await client.aio.models.generate_content(
            model=model, contents=request, config=config
        )
        return Extraction.model_validate_json(response.text or "")

    return analyze


def build_summarizer(settings: Settings, client: genai.Client) -> Summarizer:
    model = settings.analysis_model
    config = _text_config(model, prompts.SUMMARY_INSTRUCTIONS, max_output_tokens=500)

    async def summarize(text: str) -> str:
        response = await client.aio.models.generate_content(
            model=model, contents=text, config=config
        )
        return response.text or ""

    return summarize


def build_analysis_client(settings: Settings) -> genai.Client:
    # Background work may wait longer than a live reply, but not for ever.
    return genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(
            timeout=12_000, retry_options=types.HttpRetryOptions(attempts=3)
        ),
    )


def build_stt(settings: Settings) -> sarvam.STT:
    return sarvam.STT(
        language="unknown",  # detect the language on every utterance
        model=settings.stt_model,
        mode=settings.stt_mode,
        api_key=settings.sarvam_api_key,
    )


def build_tts(settings: Settings) -> sarvam.TTS:
    return sarvam.TTS(
        target_language_code=Language.ENGLISH.tts_code,
        model=settings.tts_model,
        speaker=settings.tts_speaker,
        api_key=settings.sarvam_api_key,
    )
