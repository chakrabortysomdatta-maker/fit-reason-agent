"""Model access through LangChain. The provider is one setting (LLM_PROVIDER)."""
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional, Type

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from core.config import cost_inr, settings

PROMPTS = Path(__file__).resolve().parent / "prompts"


class ModelCallsDisabled(RuntimeError):
    pass


@lru_cache(maxsize=None)
def chat_model(kind: str, temperature: Optional[float] = 0.0) -> BaseChatModel:
    """kind = 'fast' (bulk tagging, checks) or 'strong' (second looks, reply drafts)."""
    name = settings.fast_model if kind == "fast" else settings.strong_model
    if settings.llm_provider == "openrouter":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=name,
            temperature=temperature,
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            max_retries=6,
            timeout=90,
        )
    from langchain_groq import ChatGroq

    return ChatGroq(
        model=name,
        temperature=temperature,
        api_key=settings.groq_api_key,
        reasoning_effort="low",  # gpt-oss thinks before answering; low keeps output tokens and cost down
        max_retries=6,  # the SDK waits and retries on 429 rate limits
        timeout=90,
    )


def load_prompt(name: str) -> tuple[str, str]:
    """Returns (version, text). Prompts are versioned files so every output row can record which one ran."""
    text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    first, _, rest = text.partition("\n")
    version = first.replace("version:", "").strip()
    return version, rest.strip()


@dataclass
class Usage:
    """Running token and cost tally for one pipeline run."""

    tokens: dict = field(default_factory=dict)
    cost: float = 0.0

    def add(self, model: str, tokens_in: int, tokens_out: int) -> None:
        t = self.tokens.setdefault(model, {"in": 0, "out": 0})
        t["in"] += tokens_in
        t["out"] += tokens_out
        self.cost += cost_inr(model, tokens_in, tokens_out)


@dataclass
class CallResult:
    parsed: Optional[BaseModel]
    error: Optional[str]
    model: str


def structured_call(
    kind: str,
    prompt_name: str,
    schema: Type[BaseModel],
    variables: dict,
    usage: Usage,
    temperature: Optional[float] = 0.0,
) -> CallResult:
    """One model call that must return `schema`. Retries once with the validation error, then gives up visibly."""
    if not settings.model_calls_enabled:
        raise ModelCallsDisabled("Model calls are switched off (MODEL_CALLS_ENABLED=false).")
    _, system = load_prompt(prompt_name)
    model = chat_model(kind, temperature)
    model_name = settings.fast_model if kind == "fast" else settings.strong_model
    runnable = model.with_structured_output(schema, method="json_schema", strict=True, include_raw=True)
    prompt = ChatPromptTemplate.from_messages([("system", system), ("human", "{input}")])
    chain = prompt | runnable

    error = None
    for attempt in range(2):
        payload = dict(variables)
        if error:
            payload["input"] = f"{variables['input']}\n\nYour previous answer was invalid: {error}. Return only the schema."
        try:
            out = chain.invoke(payload)
        except Exception as exc:  # provider rejected the generation (e.g. JSON validation) or network error
            error = str(exc)[:300]
            continue
        meta = getattr(out["raw"], "usage_metadata", None) or {}
        usage.add(model_name, meta.get("input_tokens", 0), meta.get("output_tokens", 0))
        if out.get("parsed") is not None and out.get("parsing_error") is None:
            return CallResult(out["parsed"], None, model_name)
        error = str(out.get("parsing_error"))[:300]
    return CallResult(None, error, model_name)
