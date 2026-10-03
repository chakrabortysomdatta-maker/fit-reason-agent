"""Settings, read from .env locally or from Hugging Face Space secrets when deployed."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _get(name: str, default: str = "") -> str:
    value = os.getenv(name, "")
    if not value:
        try:  # Streamlit Community Cloud secrets
            import streamlit as st

            value = str(st.secrets.get(name, "") or "")
            if not value:  # all settings in one line: FIT_REASON = { SUPABASE_URL = "...", ... }
                value = str(st.secrets.get("FIT_REASON", {}).get(name, "") or "")
        except Exception:
            pass
    return value.strip() or default


# USD per million tokens (input, output). Check the provider's pricing page before quoting.
PRICES = {
    "openai/gpt-oss-20b": (0.075, 0.30),
    "openai/gpt-oss-120b": (0.15, 0.60),
    "anthropic/claude-haiku-4.5": (1.00, 5.00),
    "anthropic/claude-sonnet-5.5": (2.00, 10.00),
}


class Settings:
    """Read on every access, so secrets added after the app started are still picked up."""

    supabase_url = property(lambda self: _get("SUPABASE_URL"))
    supabase_anon_key = property(lambda self: _get("SUPABASE_ANON_KEY"))
    supabase_service_key = property(lambda self: _get("SUPABASE_SERVICE_KEY"))
    supabase_db_url = property(lambda self: _get("SUPABASE_DB_URL"))
    llm_provider = property(lambda self: _get("LLM_PROVIDER", "groq"))
    groq_api_key = property(lambda self: _get("GROQ_API_KEY"))
    openrouter_api_key = property(lambda self: _get("OPENROUTER_API_KEY"))
    fast_model = property(lambda self: _get("FAST_MODEL", "openai/gpt-oss-20b"))
    strong_model = property(lambda self: _get("STRONG_MODEL", "openai/gpt-oss-120b"))
    inr_per_usd = property(lambda self: float(_get("INR_PER_USD", "88")))
    # Kill switch: set MODEL_CALLS_ENABLED=false to stop every model call.
    model_calls_enabled = property(lambda self: _get("MODEL_CALLS_ENABLED", "true").lower() != "false")


settings = Settings()


def cost_inr(model: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    usd = tokens_in * price_in / 1e6 + tokens_out * price_out / 1e6
    return usd * settings.inr_per_usd
