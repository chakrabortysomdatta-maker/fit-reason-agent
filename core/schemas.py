"""Every model boundary returns one of these validated objects, never free text."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

Category = Literal["fit", "quality", "colour_mismatch", "wismo", "refund", "exchange", "cod_payment", "other"]


class ItemTag(BaseModel):
    """What a return comment or support ticket is about."""

    category: Category = Field(description="Main topic of the message")
    sub_tag: str = Field(
        description="Specific reason in snake_case, e.g. runs_small, runs_large, length_short, length_long, "
        "fabric_feel, colour_differs, damaged, where_is_order, delayed, refund_status, exchange_request, "
        "changed_mind, insufficient_information"
    )
    urgency: Literal["low", "medium", "high"] = Field(description="high = angry, repeated, or time-bound")
    language: Literal["hinglish", "hindi", "english", "other"] = Field(
        description="hinglish = Hindi and English mixed or Hindi written in Roman script"
    )
    order_id: Optional[str] = Field(description="Order ID like DH-48213 if written in the message, else null")
    confidence: float = Field(description="0 to 1: how sure you are of the category")
    evidence_span: str = Field(description="The exact words from the message that justify the category")


class IssueTitle(BaseModel):
    title: str = Field(description="One plain-English line, at most 9 words, naming the problem and the vendor")


class ReplyDraft(BaseModel):
    reply: str = Field(description="The reply to the customer, in the customer's language and register")
    language: Literal["hinglish", "hindi", "english"]
    facts_used: list[str] = Field(description="Keys of the facts the reply relies on, e.g. order.status")
    can_answer: bool = Field(description="False if the facts are not enough to answer without guessing")


class FactCheck(BaseModel):
    passed: bool = Field(description="True only if every date, size, amount and promise is in the facts")
    problems: list[str] = Field(description="Each unsupported or wrong claim, quoted, with why")


class TaggedItem(ItemTag):
    ref: str = Field(description="The item reference exactly as given, e.g. R-20011 or T-30042")


class TagBatch(BaseModel):
    items: list[TaggedItem] = Field(description="One entry per input message, same refs, same order")
