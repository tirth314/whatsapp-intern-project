"""
Core decision engine. Called once per customer turn.

Uses Groq (free API, no card required) instead of a paid LLM provider.
Groq's API is OpenAI-compatible, including function/tool calling, and it's
also the fastest inference available right now — which matters a lot here
since the assignment explicitly calls out latency as a failure point
(a 3-second reply kills the conversation).

Design choice: we send the LLM a compact state summary + last few raw turns
(NOT the full transcript) to keep latency flat regardless of call length.

The model responds with:
  - what to SAY next (spoken reply)
  - tool calls to update state / classify / trigger actions

Tool calls let the model update structured fields and fire side-effects
(WhatsApp, scheduling) in the same turn it decides they're needed — this is
what makes the mid-call WhatsApp possible, instead of waiting for call-end.
"""
from __future__ import annotations
import os
import json
from groq import Groq

from app.lead_state import LeadState, Classification
from app.prompts import SYSTEM_PROMPT

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL = "openai/gpt-oss-120b"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "update_lead_info",
            "description": "Update known facts about the lead as they are mentioned. Only pass fields that were just newly learned or changed — omit fields you don't have new info for.",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget": {"type": "string", "description": "Their stated or implied budget"},
                    "product_type": {"type": "string", "description": "What they sell / their business"},
                    "product_count": {"type": "string", "description": "Roughly how many products"},
                    "timeline": {"type": "string", "description": "When they want the site live"},
                    "features_needed": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Features mentioned, e.g. payments, delivery tracking, inventory"
                    },
                    "barrier": {"type": "string", "description": "Reason they're not ready to commit now, if any"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "classify_lead",
            "description": "Set or update the lead's classification based on everything said so far. Call this whenever the classification should change.",
            "parameters": {
                "type": "object",
                "properties": {
                    "classification": {"type": "string", "enum": ["hot", "warm", "cold"]},
                    "reason": {"type": "string", "description": "Brief reason, quoting what they said"},
                },
                "required": ["classification", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_mid_call_whatsapp",
            "description": "Fire the WhatsApp message NOW, mid-call, because the lead has shown high buying intent (classified HOT). Only call this once per call.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why now — what signal triggered it"},
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_callback",
            "description": "The customer named a specific time to be called back (e.g. 'tomorrow morning', 'Friday at 5pm'). Capture the raw phrase exactly as said.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spoken_time": {"type": "string", "description": "Exact phrase the customer used for timing"},
                },
                "required": ["spoken_time"],
            },
        },
    },
]


def _build_messages(state: LeadState, latest_user_text: str) -> list[dict]:
    """Compact context: system prompt + state summary + last few turns + newest message."""
    context_block = (
        "CURRENT KNOWN STATE (do not re-ask for anything already filled in):\n"
        + json.dumps(state.summary_dict(), indent=2)
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": context_block},
    ]

    for turn in state.recent_turns():
        role = "user" if turn.role == "user" else "assistant"
        messages.append({"role": role, "content": turn.text})

    messages.append({"role": "user", "content": latest_user_text})
    return messages


def process_turn(state: LeadState, customer_said: str) -> dict:
    """
    Run one turn of the conversation.

    Returns:
        {
            "speech": str,              # what the agent should say (send to TTS)
            "actions": {
                "whatsapp_triggered": bool,
                "whatsapp_reason": str | None,
                "callback_scheduled": bool,
                "callback_spoken_time": str | None,
            }
        }
    """
    state.add_turn("user", customer_said)

    messages = _build_messages(state, customer_said)

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=400,
        tools=TOOLS,
        tool_choice="auto",
        messages=messages,
    )

    message = response.choices[0].message

    actions = {
        "whatsapp_triggered": False,
        "whatsapp_reason": None,
        "callback_scheduled": False,
        "callback_spoken_time": None,
    }

    speech = (message.content or "").strip()

    if message.tool_calls:
        for tool_call in message.tool_calls:
            try:
                tool_input = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                tool_input = {}
            _apply_tool_call(state, tool_call.function.name, tool_input, actions)

    if not speech:
        # Model only called tools with no speech (common with some models when
        # tool_choice="auto" picks a tool) — do one plain follow-up call so the
        # customer always hears something.
        followup_messages = messages + [
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in message.tool_calls
            ]},
        ]
        for tc in message.tool_calls:
            followup_messages.append({
                "role": "tool", "tool_call_id": tc.id, "content": "ok",
            })
        followup_messages.append({
            "role": "user", "content": "(Now say your next line to the customer out loud.)"
        })
        followup = client.chat.completions.create(
            model=MODEL, max_tokens=200, messages=followup_messages,
        )
        speech = (followup.choices[0].message.content or "Sorry, could you say that again?").strip()

    state.add_turn("assistant", speech)
    return {"speech": speech, "actions": actions}


def _apply_tool_call(state: LeadState, name: str, tool_input: dict, actions: dict) -> None:
    if name == "update_lead_info":
        if "budget" in tool_input:
            state.budget = tool_input["budget"]
        if "product_type" in tool_input:
            state.product_type = tool_input["product_type"]
        if "product_count" in tool_input:
            state.product_count = tool_input["product_count"]
        if "timeline" in tool_input:
            state.timeline = tool_input["timeline"]
        if "features_needed" in tool_input:
            state.features_needed = tool_input["features_needed"]
        if "barrier" in tool_input:
            state.barrier = tool_input["barrier"]

    elif name == "classify_lead":
        state.classification = Classification(tool_input["classification"])
        state.classification_reason = tool_input["reason"]

    elif name == "trigger_mid_call_whatsapp":
        if not state.whatsapp_fired:
            state.whatsapp_fired = True
            actions["whatsapp_triggered"] = True
            actions["whatsapp_reason"] = tool_input.get("reason", "")

    elif name == "schedule_callback":
        state.callback_requested_text = tool_input["spoken_time"]
        actions["callback_scheduled"] = True
        actions["callback_spoken_time"] = tool_input["spoken_time"]