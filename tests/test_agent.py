"""Offline tests: real LiveKit and Gemini plugin code, with the network replaced."""

import jwt
import pytest
from fastapi.testclient import TestClient
from livekit.agents import APIConnectionError, APIConnectOptions, llm
from livekit.plugins import silero

from apps.agent import providers
from apps.agent.assistant import SalesAssistant
from apps.agent.language import Language
from apps.agent.latency import stage_latencies
from apps.agent.main import build_session
from apps.api.main import app
from packages.core.config import DISPATCH_NAME, Settings, get_settings


def settings(**overrides) -> Settings:
    values = {
        "livekit_url": "ws://127.0.0.1:7880",
        "livekit_api_key": "devkey",
        "livekit_api_secret": "secret-secret-secret-secret-secret",
        "sarvam_api_key": "test",
        "gemini_api_key": "test",
    }
    return Settings(_env_file=None, **(values | overrides))


async def test_speech_providers_accept_the_default_settings():
    stt = providers.build_stt(settings())
    tts = providers.build_tts(settings())
    assert stt.capabilities.streaming and tts.capabilities.streaming
    tts.update_options(target_language_code="hi-IN")


@pytest.mark.parametrize(
    "history",
    [
        [("user", "hello")],
        [("assistant", "Hi"), ("user", "hello")],
        [("user", "hello"), ("assistant", "Hi")],
    ],
)
async def test_llm_request_for_gemini(history, monkeypatch):
    sent = {}

    async def capture(**request):
        sent.update(request)
        raise RuntimeError("request captured, nothing sent")

    model = providers.build_llm(settings())
    monkeypatch.setattr(model._client.aio.models, "generate_content_stream", capture)

    chat_ctx = llm.ChatContext.empty()
    chat_ctx.add_message(role="system", content="be brief")
    for role, text in history:
        chat_ctx.add_message(role=role, content=text)

    with pytest.raises(APIConnectionError):
        options = APIConnectOptions(max_retry=0)
        async with model.chat(chat_ctx=chat_ctx, conn_options=options) as stream:
            async for _ in stream:
                pass

    config = sent["config"]
    assert sent["model"] == "gemini-3.5-flash-lite"
    assert config.thinking_config.thinking_level.value == "MINIMAL"
    assert config.max_output_tokens == 300
    assert config.system_instruction[0].text == "be brief"
    assert sent["contents"][-1].role == "user"


@pytest.mark.parametrize(
    "model, expected",
    [
        ("gemini-3.5-flash-lite", {"thinking_level": "minimal"}),
        ("gemini-3.8-flash", {"thinking_level": "low"}),
        ("gemini-2.5-flash", {"thinking_budget": 0}),
        ("gemini-2.5-pro", None),
    ],
)
def test_thinking_setting_depends_on_model(model, expected):
    assert providers.low_latency_thinking(model) == expected


def test_non_gemini_model_is_rejected_with_a_clear_message():
    with pytest.raises(ValueError, match="Google Gemini"):
        providers.build_llm(settings(llm_model="claude-haiku-5-5"))


class _FakeTTS:
    def __init__(self):
        self.codes = []

    def update_options(self, *, target_language_code):
        self.codes.append(target_language_code)


async def test_voice_follows_the_callers_language(monkeypatch):
    tts = _FakeTTS()
    assistant = SalesAssistant(settings())
    monkeypatch.setattr(
        SalesAssistant, "session", property(lambda self: type("S", (), {"tts": tts})())
    )

    async def say(text):
        message = llm.ChatMessage(role="user", content=[text])
        await assistant.on_user_turn_completed(llm.ChatContext.empty(), message)

    await say("We need an invoicing tool")
    await say("हमें बिल बनाने में दिक्कत है")
    await say("हमारी team को invoice software चाहिए")  # same voice language
    await say("Please tell me the price")

    assert tts.codes == ["hi-IN", "en-IN"]
    assert assistant.language == Language.ENGLISH


async def test_session_uses_stt_turns_and_vad_interruption():
    session = build_session(settings(), silero.VAD.load())
    assert session.options.turn_handling["turn_detection"] == "stt"
    assert session.options.interruption["mode"] == "vad"
    assert session.options.endpointing["min_delay"] == 0.07


def test_latency_is_reported_in_milliseconds():
    assert stage_latencies("assistant", {"e2e_latency": 1.2345}) == {"total_ms": 1234}
    assert stage_latencies("user", {"transcription_delay": 0.07}) == {"stt_ms": 70}
    assert stage_latencies("assistant", {}) == {}


def test_call_requires_consent_and_returns_scoped_token():
    configured = settings()
    app.dependency_overrides[get_settings] = lambda: configured
    try:
        client = TestClient(app)
        assert client.post("/calls", json={}).status_code == 400

        body = client.post("/calls", json={"consent": True}).json()
        claims = jwt.decode(body["token"], configured.livekit_api_secret, algorithms=["HS256"])
        assert claims["video"]["room"] == body["room"]
        assert claims["roomConfig"]["agents"][0]["agentName"] == DISPATCH_NAME
        assert claims["exp"] - claims["nbf"] <= 600
    finally:
        app.dependency_overrides.clear()
