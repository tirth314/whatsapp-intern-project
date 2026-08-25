"""
Converts what the customer said ("tomorrow morning", "Friday around 5",
"call me back this evening") into an actual datetime we can book.

Uses Groq (same free provider as the main conversation) rather than a
rules-based date parser — testing showed libraries like `dateparser` fail
or misparse on exactly the vague phrasing real customers use ("tomorrow
morning" -> None, "Friday around 5" -> wrong date entirely). One small,
cheap LLM call handles natural phrasing far more reliably.
"""
from __future__ import annotations
import os
import json
from datetime import datetime
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL = "openai/gpt-oss-120b"

_TOOL = [{
    "type": "function",
    "function": {
        "name": "resolve_datetime",
        "description": "Resolve a spoken time phrase into a concrete future datetime.",
        "parameters": {
            "type": "object",
            "properties": {
                "iso_datetime": {
                    "type": "string",
                    "description": "The resolved datetime in ISO 8601 format (YYYY-MM-DDTHH:MM:SS). Use sensible defaults for vague times: morning=09:00, afternoon=14:00, evening=18:00, night=20:00.",
                },
                "confident": {
                    "type": "boolean",
                    "description": "False if the phrase was too vague/ambiguous to resolve confidently.",
                },
            },
            "required": ["confident"],
        },
    },
}]


def parse_spoken_time(spoken_text: str, reference_time: datetime | None = None) -> datetime | None:
    """
    Resolves a spoken time phrase into a concrete datetime using the LLM.
    Returns None if it can't confidently parse — caller should then ask
    the customer to clarify rather than silently booking a wrong slot.
    """
    reference_time = reference_time or datetime.now()

    prompt = (
        f"Current date and time: {reference_time.strftime('%A, %Y-%m-%d %H:%M')}\n"
        f"Customer said: \"{spoken_text}\"\n"
        f"Resolve this into a concrete future datetime for a callback booking. "
        f"Call the resolve_datetime tool with your answer."
    )

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=200,
        tools=_TOOL,
        tool_choice={"type": "function", "function": {"name": "resolve_datetime"}},
        messages=[{"role": "user", "content": prompt}],
    )

    message = response.choices[0].message
    if not message.tool_calls:
        return None

    try:
        result = json.loads(message.tool_calls[0].function.arguments)
    except json.JSONDecodeError:
        return None

    if not result.get("confident") or "iso_datetime" not in result:
        return None

    try:
        return datetime.fromisoformat(result["iso_datetime"])
    except ValueError:
        return None


def book_callback(spoken_text: str) -> dict:
    """
    Placeholder booking action. Wire this to Google Calendar API or your
    own DB later. For now, returns the resolved slot so the caller can
    log/confirm it.
    """
    parsed = parse_spoken_time(spoken_text)
    return {
        "raw_text": spoken_text,
        "resolved_datetime": parsed.isoformat() if parsed else None,
        "success": parsed is not None,
    }