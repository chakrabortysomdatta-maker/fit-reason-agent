"""Settings, read from .env locally or from Hugging Face Space secrets when deployed."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _get(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    if not value:
        try:  # Streamlit secrets, when running as an app
            import streamlit as st

            value = st.secrets.get(name, default)
        except Exception:
            pass
    return value or default


# USD per million tokens (input, output). Check the provider's pricing page before quoting.
PRICES = {
    "openai/gpt-oss-20b": (0.075, 0.30),
    "openai/gpt-oss-120b": (0.15, 0.60),
    "anthropic/claude-haiku-4.5": (1.00, 5.00),
    "anthropic/claude-sonnet-5.5": (2.00, 10.00),
}


@dataclass(frozen=True)
class Settings:
    supabase_url: str = field(default_factory=lambda: _get("SUPABASE_URL"))
    supabase_anon_key: str = field(default_factory=lambda: _get("SUPABASE_ANON_KEY"))
    supabase_service_key: str = field(default_factory=lambda: _get("SUPABASE_SERVICE_KEY"))
    supabase_db_url: str = field(default_factory=lambda: _get("SUPABASE_DB_URL"))
    llm_provider: str = field(default_factory=lambda: _get("LLM_PROVIDER", "groq"))
    groq_api_key: str = field(default_factory=lambda: _get("GROQ_API_KEY"))
    openrouter_api_key: str = field(default_factory=lambda: _get("OPENROUTER_API_KEY"))
    fast_model: str = field(default_factory=lambda: _get("FAST_MODEL", "openai/gpt-oss-20b"))
    strong_model: str = field(default_factory=lambda: _get("STRONG_MODEL", "openai/gpt-oss-120b"))
    inr_per_usd: float = field(default_factory=lambda: float(_get("INR_PER_USD", "88")))
    # Kill switch: set MODEL_CALLS_ENABLED=false to stop every model call.
    model_calls_enabled: bool = field(
        default_factory=lambda: _get("MODEL_CALLS_ENABLED", "true").lower() != "false"
    )


settings = Settings()


def cost_inr(model: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    usd = tokens_in * price_in / 1e6 + tokens_out * price_out / 1e6
    return usd * settings.inr_per_usd
