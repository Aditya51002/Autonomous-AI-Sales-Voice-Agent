"""Per-stage latency, taken from the metrics LiveKit attaches to each message."""

from collections.abc import Mapping

# LiveKit metric name -> name shown in logs and the web page.
_USER_STAGES = {
    "transcription_delay": "stt_ms",
    "end_of_turn_delay": "end_of_turn_ms",
}
_ASSISTANT_STAGES = {
    "llm_node_ttft": "llm_first_token_ms",
    "tts_node_ttfb": "tts_first_audio_ms",
    "e2e_latency": "total_ms",
}


def stage_latencies(role: str, metrics: Mapping[str, float]) -> dict[str, int]:
    stages = _USER_STAGES if role == "user" else _ASSISTANT_STAGES
    return {
        label: round(metrics[name] * 1000)
        for name, label in stages.items()
        if metrics.get(name) is not None
    }
