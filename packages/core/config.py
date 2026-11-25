"""Settings shared by the agent worker, the API and the scripts."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

# Name the API dispatches to and the worker registers under.
DISPATCH_NAME = "sales-agent"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    sarvam_api_key: str = ""
    gemini_api_key: str = ""

    company_name: str = "Acme Cloud"
    agent_name: str = "Asha"
    product_description: str = (
        "a cloud-based billing and invoicing platform for small businesses"
    )

    llm_model: str = "gemini-3.5-flash-lite"
    llm_max_tokens: int = 300
    stt_model: str = "saaras:v4"
    stt_mode: str = "codemix"
    tts_model: str = "bulbul:v4-flash"
    tts_speaker: str = "simran_enhi_customer"
    endpointing_min_delay: float = 0.07
    interruption_min_duration: float = 0.5
    max_call_seconds: int = 600

    web_origin: str = "http://localhost:3000"
    api_url: str = "http://127.0.0.1:8000"

    knowledge_db: Path = ROOT / "data" / "knowledge.db"
    embedding_model: str = "intfloat/multilingual-e5-large"
    # Passages less similar than this are ignored. Calibrate with scripts.eval_retrieval.
    retrieval_min_score: float = 0.78
    retrieval_timeout: float = 0.8

    leads_db: Path = ROOT / "data" / "leads.db"
    analysis_model: str = "gemini-3.5-flash-lite"
    # Monthly price of the cheapest plan, used to judge whether a budget fits.
    min_monthly_budget_inr: int = 499
    memory_window: int = 12  # recent messages sent word for word

    def require(self, *names: str) -> None:
        """Fail at startup, naming every missing variable."""
        missing = [name.upper() for name in names if not getattr(self, name)]
        if missing:
            raise SystemExit(
                f"Missing settings: {', '.join(missing)}. "
                f"Copy .env.example to .env and fill them in."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
