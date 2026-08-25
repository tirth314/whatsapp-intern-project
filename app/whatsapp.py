"""
WhatsApp sending via Meta's WhatsApp Business Cloud API.

STUB MODE: WhatsApp setup is deferred for now. Both functions currently just
BUILD the message and PRINT it instead of sending, so the rest of the system
(classification -> trigger decision -> message content) is fully built and
testable without needing WhatsApp credentials yet.

To go live later: set WHATSAPP_ENABLED=true in .env once you have real
credentials in WHATSAPP_PHONE_NUMBER_ID / WHATSAPP_ACCESS_TOKEN / WHATSAPP_TO_NUMBER.
Nothing else in the system needs to change — the call sites in llm_engine's
consumer code stay exactly the same either way.
"""
from __future__ import annotations
import os
import httpx

from app.lead_state import LeadState

WHATSAPP_ENABLED = os.environ.get("WHATSAPP_ENABLED", "false").lower() == "true"

WHATSAPP_API_VERSION = "v21.0"
PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN")
TO_NUMBER = os.environ.get("WHATSAPP_TO_NUMBER")

YOUR_MOBILE_NUMBER = os.environ.get("YOUR_MOBILE_NUMBER", "<your number not set yet>")
RESUME_URL = os.environ.get("RESUME_URL")
ARCHITECTURE_IMAGE_URL = os.environ.get("ARCHITECTURE_IMAGE_URL")

BASE_URL = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{PHONE_NUMBER_ID}/messages"


async def _send_text(body: str) -> None:
    if not WHATSAPP_ENABLED:
        print("\n[WHATSAPP STUB] Would send TEXT message:")
        print("-" * 50)
        print(body)
        print("-" * 50)
        return

    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": TO_NUMBER,
        "type": "text",
        "text": {"body": body},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(BASE_URL, headers=headers, json=payload, timeout=10.0)
        resp.raise_for_status()


async def _send_image(image_url: str, caption: str = "") -> None:
    if not WHATSAPP_ENABLED:
        print(f"[WHATSAPP STUB] Would send IMAGE: {image_url} (caption: {caption})")
        return

    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": TO_NUMBER,
        "type": "image",
        "image": {"link": image_url, "caption": caption},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(BASE_URL, headers=headers, json=payload, timeout=10.0)
        resp.raise_for_status()


async def _send_document(doc_url: str, filename: str, caption: str = "") -> None:
    if not WHATSAPP_ENABLED:
        print(f"[WHATSAPP STUB] Would send DOCUMENT: {doc_url} as {filename} (caption: {caption})")
        return

    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": TO_NUMBER,
        "type": "document",
        "document": {"link": doc_url, "filename": filename, "caption": caption},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(BASE_URL, headers=headers, json=payload, timeout=10.0)
        resp.raise_for_status()


async def send_mid_call_whatsapp(state: LeadState, reason: str) -> None:
    """Fired while the call is still live — high intent detected."""
    lines = [
        "Hey! Great chatting with you just now 🙂",
        "",
        "Quick summary of what we discussed:",
    ]
    if state.product_type:
        lines.append(f"- Business: {state.product_type}")
    if state.product_count:
        lines.append(f"- Products: {state.product_count}")
    if state.budget:
        lines.append(f"- Budget: {state.budget}")
    if state.timeline:
        lines.append(f"- Timeline: {state.timeline}")
    lines.append("")
    lines.append(f"You can reach me directly at {YOUR_MOBILE_NUMBER} anytime.")

    await _send_text("\n".join(lines))


async def send_post_call_followup(state: LeadState) -> None:
    """Fired after the call ends — full context + resume + build image."""
    summary_lines = ["Thanks for the call earlier! Here's what we covered:"]
    if state.product_type:
        summary_lines.append(f"- You mentioned you sell {state.product_type}")
    if state.product_count:
        summary_lines.append(f"- Around {state.product_count} products")
    if state.budget:
        summary_lines.append(f"- Budget: {state.budget}")
    if state.timeline:
        summary_lines.append(f"- Timeline: {state.timeline}")
    if state.features_needed:
        summary_lines.append(f"- Features: {', '.join(state.features_needed)}")
    if state.barrier:
        summary_lines.append(f"- You mentioned: {state.barrier}")
    if state.callback_requested_text:
        summary_lines.append(f"- You asked me to call back: {state.callback_requested_text}")

    summary_lines.append("")
    summary_lines.append(f"Feel free to reach me directly at {YOUR_MOBILE_NUMBER}.")

    await _send_text("\n".join(summary_lines))

    if ARCHITECTURE_IMAGE_URL:
        await _send_image(ARCHITECTURE_IMAGE_URL, caption="How I built this system")

    if RESUME_URL:
        await _send_document(RESUME_URL, filename="Resume.pdf", caption="My resume")