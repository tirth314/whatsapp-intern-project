"""
LeadState is the single source of truth for a call.

Instead of resending the full transcript to the LLM every turn (slow, expensive,
and latency grows as the call goes on), we keep a compact structured summary that
gets updated after every turn. Only this summary + the last couple of raw turns
are sent to the LLM each time.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Classification(str, Enum):
    UNKNOWN = "unknown"
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class Language(str, Enum):
    ENGLISH = "en"
    HINDI = "hi"
    TELUGU = "te"


@dataclass
class Turn:
    role: str  # "user" or "assistant"
    text: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class LeadState:
    call_sid: str

    # Discovery fields — filled in progressively as the LLM extracts them
    budget: Optional[str] = None
    product_type: Optional[str] = None          # what they sell
    product_count: Optional[str] = None          # how many products
    timeline: Optional[str] = None
    features_needed: list[str] = field(default_factory=list)

    # Barrier detected for WARM leads (e.g. "budget not decided", "partner decides")
    barrier: Optional[str] = None

    # Classification, re-evaluated after every turn
    classification: Classification = Classification.UNKNOWN
    classification_reason: str = ""

    # Language currently speaking in
    language: Language = Language.ENGLISH

    # Mid-call action tracking — so we don't fire WhatsApp twice
    whatsapp_fired: bool = False

    # Callback scheduling
    callback_requested_text: Optional[str] = None   # raw spoken phrase, e.g. "tomorrow morning"
    callback_datetime: Optional[datetime] = None
    callback_booked: bool = False

    # Rolling window of raw turns — only the last N are sent to the LLM as context.
    # Full history kept here for the post-call WhatsApp / follow-up, which needs
    # "what they actually said", not just the structured summary.
    history: list[Turn] = field(default_factory=list)

    RECENT_TURNS_FOR_LLM = 6  # last 3 exchanges (user+assistant) — keeps prompt small

    def add_turn(self, role: str, text: str) -> None:
        self.history.append(Turn(role=role, text=text))

    def recent_turns(self) -> list[Turn]:
        return self.history[-self.RECENT_TURNS_FOR_LLM:]

    def summary_dict(self) -> dict:
        """Compact state passed to the LLM every turn instead of full transcript."""
        return {
            "budget": self.budget,
            "product_type": self.product_type,
            "product_count": self.product_count,
            "timeline": self.timeline,
            "features_needed": self.features_needed,
            "barrier": self.barrier,
            "classification": self.classification.value,
            "language": self.language.value,
            "callback_requested_text": self.callback_requested_text,
        }

    def full_transcript_text(self) -> str:
        """Used for the post-call WhatsApp follow-up — needs real quotes, not the summary."""
        lines = []
        for t in self.history:
            speaker = "Customer" if t.role == "user" else "Agent"
            lines.append(f"{speaker}: {t.text}")
        return "\n".join(lines)


##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