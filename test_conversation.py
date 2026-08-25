"""
Test the full conversation logic (LLM decision engine, state tracking,
classification, mid-call WhatsApp trigger, scheduling) WITHOUT touching
Twilio, Deepgram, or ElevenLabs.

You type as the customer. The script prints:
  - what the AI would say (instead of sending it to TTS)
  - the current lead state after every turn
  - when a mid-call WhatsApp / callback would fire

This is where you should catch and fix logic bugs — it's free and instant,
unlike live call testing which costs money and takes longer per iteration.

Run:
    pip install python-dotenv   (if not already installed)
    Fill in your .env file (copy from .env.example)
    python test_conversation.py

No manual export needed — .env is loaded automatically below.
"""
from dotenv import load_dotenv
load_dotenv()

import asyncio
import uuid

from app.lead_state import LeadState
from app.llm_engine import process_turn
from app.whatsapp import send_mid_call_whatsapp, send_post_call_followup
from app.scheduler import book_callback


def print_state(state: LeadState) -> None:
    print("\n--- current state ---")
    print(f"  classification : {state.classification.value}  ({state.classification_reason})")
    print(f"  budget         : {state.budget}")
    print(f"  product_type   : {state.product_type}")
    print(f"  product_count  : {state.product_count}")
    print(f"  timeline       : {state.timeline}")
    print(f"  features       : {state.features_needed}")
    print(f"  barrier        : {state.barrier}")
    print(f"  callback       : {state.callback_requested_text}")
    print("----------------------\n")


async def main():
    state = LeadState(call_sid=str(uuid.uuid4()))

    print("=" * 60)
    print("ElevateBox Voice AI — text test harness")
    print("Type as the customer. Type 'quit' to end the call.")
    print("=" * 60)

    # Kick off the call the way the agent would open it
    opener = "Hi, this is Aditi calling from ElevateBox — hope I'm not catching you at a bad time?"
    print(f"\nAI: {opener}")
    state.add_turn("assistant", opener)

    while True:
        customer_said = input("You: ").strip()
        if customer_said.lower() in ("quit", "exit"):
            break

        result = process_turn(state, customer_said)
        print(f"\nAI: {result['speech']}\n")

        actions = result["actions"]

        if actions["whatsapp_triggered"]:
            print(f">>> [MID-CALL WHATSAPP TRIGGERED] reason: {actions['whatsapp_reason']}")
            await send_mid_call_whatsapp(state, actions["whatsapp_reason"])

        if actions["callback_scheduled"]:
            booking = book_callback(actions["callback_spoken_time"])
            state.callback_booked = booking["success"]
            print(f">>> [CALLBACK SCHEDULED] raw: '{booking['raw_text']}' -> resolved: {booking['resolved_datetime']}")

        print_state(state)

    print("\n=== Call ended ===")
    print("Full transcript:\n")
    print(state.full_transcript_text())

    print(f"\nFinal classification: {state.classification.value} — {state.classification_reason}")

    await send_post_call_followup(state)


if __name__ == "__main__":
    asyncio.run(main())