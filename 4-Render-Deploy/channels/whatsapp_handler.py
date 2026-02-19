"""
WhatsApp Channel Handler — Twilio Integration
===============================================
Receives and sends WhatsApp messages via the Twilio API.

Incoming flow:
  Twilio webhook POST → validate_webhook() → process_webhook()
  → normalized message dict → published to Kafka

Outgoing flow:
  Agent response → send_message() → Twilio API → delivery confirmation

Setup:
  1. Create a Twilio account with WhatsApp Business API enabled
  2. Configure webhook URL in Twilio Console:
     POST https://your-domain.com/webhooks/whatsapp
  3. Set environment variables:
     - TWILIO_ACCOUNT_SID: Twilio account SID
     - TWILIO_AUTH_TOKEN: Twilio auth token
     - TWILIO_WHATSAPP_FROM: WhatsApp sender number (whatsapp:+14155238886)
     - TWILIO_WEBHOOK_URL: Public webhook URL for signature validation

Dependencies:
  twilio
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx

logger = logging.getLogger("channels.whatsapp")

# ── Configuration ────────────────────────────────────────────────────────

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
TWILIO_WEBHOOK_URL = os.environ.get("TWILIO_WEBHOOK_URL", "")

# Twilio API base URL
TWILIO_API_BASE = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}"


# ── Webhook Validation ──────────────────────────────────────────────────


def validate_webhook(
    signature: str,
    url: str,
    params: dict,
) -> bool:
    """Validate Twilio webhook signature for security.

    Twilio signs every webhook request. This function verifies the
    X-Twilio-Signature header to prevent spoofed messages.

    Args:
        signature: Value of X-Twilio-Signature header
        url: The full webhook URL (must match Twilio Console config exactly)
        params: POST form parameters from the webhook body

    Returns:
        True if signature is valid, False otherwise.
    """
    import hashlib
    import hmac

    if not TWILIO_AUTH_TOKEN:
        logger.warning("TWILIO_AUTH_TOKEN not set — skipping signature validation")
        return True

    # Build the data string: URL + sorted params concatenated
    data = url
    for key in sorted(params.keys()):
        data += key + params[key]

    # Compute HMAC-SHA1
    expected = hmac.new(
        TWILIO_AUTH_TOKEN.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha1,
    ).digest()

    import base64

    expected_b64 = base64.b64encode(expected).decode("utf-8")

    return hmac.compare_digest(expected_b64, signature)


# ── Incoming Message Processing ─────────────────────────────────────────


async def process_webhook(form_data: dict) -> Optional[dict]:
    """Process an incoming WhatsApp message from the Twilio webhook.

    Twilio sends POST requests with form-encoded data when a WhatsApp
    message is received. This function normalizes it to our standard
    message format.

    Args:
        form_data: Parsed form data from the Twilio webhook POST body.
            Key fields: MessageSid, From, To, Body, ProfileName,
            WaId, NumMedia, NumSegments

    Returns:
        Normalized message dict, or None if the message should be skipped.
    """
    message_sid = form_data.get("MessageSid", "")
    from_number = form_data.get("From", "")
    body = form_data.get("Body", "")
    profile_name = form_data.get("ProfileName", "")
    wa_id = form_data.get("WaId", "")
    num_media = form_data.get("NumMedia", "0")
    status = form_data.get("SmsStatus", "received")

    if not message_sid or not from_number:
        logger.warning("WhatsApp webhook missing MessageSid or From")
        return None

    # Normalize phone number (remove whatsapp: prefix)
    customer_phone = _normalize_phone(from_number)

    # Skip empty messages (unless they have media)
    if not body and num_media == "0":
        logger.info(f"Skipping empty WhatsApp message from {customer_phone}")
        return None

    # Handle media messages
    media_info = []
    try:
        media_count = int(num_media)
    except (ValueError, TypeError):
        media_count = 0

    for i in range(media_count):
        media_url = form_data.get(f"MediaUrl{i}", "")
        media_type = form_data.get(f"MediaContentType{i}", "")
        if media_url:
            media_info.append({"url": media_url, "content_type": media_type})

    # If message is only media with no text, note it
    if not body and media_info:
        body = f"[Customer sent {media_count} media file(s)]"

    logger.info(
        f"WhatsApp message received: sid={message_sid}, "
        f"from={customer_phone}, body_length={len(body)}"
    )

    return {
        "channel": "whatsapp",
        "channel_message_id": message_sid,
        "customer_phone": customer_phone,
        "customer_name": profile_name or "Customer",
        "subject": "",  # WhatsApp doesn't have subjects
        "content": body.strip(),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "wa_id": wa_id,
            "num_media": num_media,
            "media": media_info,
            "status": status,
            "from_raw": from_number,
            "num_segments": form_data.get("NumSegments", "1"),
        },
    }


# ── Outgoing Messages ───────────────────────────────────────────────────


async def send_message(
    to_phone: str,
    body: str,
) -> dict:
    """Send a WhatsApp message via the Twilio API.

    Args:
        to_phone: Recipient phone number (E.164 format, e.g., +15551234567)
        body: Message text (already formatted by formatters.py)

    Returns:
        dict with channel_message_id (Twilio SID) and delivery_status.
    """
    logger.info(f"send_message called: to_phone={to_phone!r}, body_length={len(body)}")

    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.error(
            f"Twilio credentials missing — "
            f"SID={'set' if TWILIO_ACCOUNT_SID else 'MISSING'}, "
            f"TOKEN={'set' if TWILIO_AUTH_TOKEN else 'MISSING'}"
        )
        return {
            "channel_message_id": None,
            "delivery_status": "failed",
            "error": "Twilio credentials not configured",
        }

    # Ensure phone number is in whatsapp: format
    to_whatsapp = _to_whatsapp_format(to_phone)
    logger.info(f"Twilio sending to: {to_whatsapp}, from: {TWILIO_WHATSAPP_FROM}")

    # Split long messages at sentence boundaries
    message_parts = split_message(body)
    logger.info(f"Message split into {len(message_parts)} part(s)")

    results = []
    for part in message_parts:
        result = await _send_single_message(to_whatsapp, part)
        results.append(result)

    # Return the last message's result (or first failure)
    for r in results:
        if r.get("delivery_status") == "failed":
            return r

    return results[-1] if results else {
        "channel_message_id": None,
        "delivery_status": "failed",
        "error": "No message parts to send",
    }


async def _send_single_message(to_whatsapp: str, body: str) -> dict:
    """Send a single WhatsApp message via Twilio REST API."""
    url = f"{TWILIO_API_BASE}/Messages.json"

    payload = {
        "From": TWILIO_WHATSAPP_FROM,
        "To": to_whatsapp,
        "Body": body,
    }

    logger.info(
        f"Twilio API request: POST {url}, "
        f"From={TWILIO_WHATSAPP_FROM}, To={to_whatsapp}, "
        f"body_length={len(body)}"
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                data=payload,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                timeout=30.0,
            )

        logger.info(f"Twilio API response: status={response.status_code}")

        if response.status_code in (200, 201):
            data = response.json()
            message_sid = data.get("sid", "")
            logger.info(f"WhatsApp message sent: sid={message_sid}, to={to_whatsapp}")
            return {
                "channel_message_id": message_sid,
                "delivery_status": "sent",
            }
        else:
            error_msg = response.text[:500]
            logger.error(
                f"Twilio API error ({response.status_code}): {error_msg}"
            )
            return {
                "channel_message_id": None,
                "delivery_status": "failed",
                "error": f"Twilio API {response.status_code}: {error_msg}",
            }

    except Exception as e:
        logger.error(
            f"Failed to send WhatsApp message to {to_whatsapp}: {e}",
            exc_info=True,
        )
        return {
            "channel_message_id": None,
            "delivery_status": "failed",
            "error": str(e),
        }


# ── Status Callbacks ────────────────────────────────────────────────────


async def process_status_callback(form_data: dict) -> dict:
    """Process a Twilio message status callback.

    Twilio sends status updates (queued → sent → delivered → read)
    via webhook. Use this to update delivery_status in the messages table.

    Args:
        form_data: Status callback form data with MessageSid, MessageStatus

    Returns:
        dict with message_sid and status.
    """
    message_sid = form_data.get("MessageSid", "")
    status = form_data.get("MessageStatus", "unknown")
    error_code = form_data.get("ErrorCode")

    logger.info(f"WhatsApp status update: sid={message_sid}, status={status}")

    if error_code:
        logger.warning(
            f"WhatsApp delivery error: sid={message_sid}, "
            f"error_code={error_code}, status={status}"
        )

    return {
        "channel_message_id": message_sid,
        "delivery_status": _map_twilio_status(status),
        "error_code": error_code,
    }


# ── Message Splitting ───────────────────────────────────────────────────


def split_message(
    text: str,
    max_length: int = 1600,
) -> list[str]:
    """Split a long response into multiple WhatsApp-friendly messages.

    WhatsApp has a 4096-char limit per message, but messages over 1600 chars
    render poorly on mobile. We split at sentence boundaries.

    Args:
        text: Full response text
        max_length: Maximum characters per message chunk

    Returns:
        List of message chunks, each under max_length.
    """
    if len(text) <= max_length:
        return [text]

    # Split on sentence boundaries (same regex as formatters.py)
    sentences = re.split(r"(?<=[.!?])(?<!\d\.)(?<!\d\d\.)\s+", text)

    # Also handle newline-separated content
    chunks_raw = []
    for s in sentences:
        for part in s.split("\n"):
            part = part.strip()
            if part:
                chunks_raw.append(part)

    # Build message parts
    parts = []
    current_part = []
    current_length = 0

    for chunk in chunks_raw:
        separator_len = 1 if current_part else 0
        new_length = current_length + len(chunk) + separator_len

        if new_length <= max_length:
            current_part.append(chunk)
            current_length = new_length
        else:
            # Save current part and start a new one
            if current_part:
                parts.append("\n".join(current_part))
            current_part = [chunk]
            current_length = len(chunk)

    # Don't forget the last part
    if current_part:
        parts.append("\n".join(current_part))

    return parts if parts else [text[:max_length]]


# ── Helper Functions ────────────────────────────────────────────────────


def _normalize_phone(phone: str) -> str:
    """Normalize phone number to E.164 format.

    Handles:
      - "whatsapp:+15551234567" → "+15551234567"
      - "+15551234567" → "+15551234567"
      - "15551234567" → "+15551234567"
    """
    # Strip whatsapp: prefix
    phone = re.sub(r"^whatsapp:", "", phone).strip()

    # Ensure + prefix
    if phone and not phone.startswith("+"):
        phone = f"+{phone}"

    return phone


def _to_whatsapp_format(phone: str) -> str:
    """Convert phone number to Twilio WhatsApp format.

    Handles:
      - "+15551234567" → "whatsapp:+15551234567"
      - "whatsapp:+15551234567" → "whatsapp:+15551234567" (no-op)
    """
    phone = _normalize_phone(phone)
    if not phone.startswith("whatsapp:"):
        phone = f"whatsapp:{phone}"
    return phone


def _map_twilio_status(twilio_status: str) -> str:
    """Map Twilio message status to our delivery_status enum.

    Twilio statuses: queued, sent, delivered, read, failed, undelivered
    Our enum: pending, sent, delivered, read, failed
    """
    status_map = {
        "queued": "pending",
        "sending": "pending",
        "sent": "sent",
        "delivered": "delivered",
        "read": "read",
        "failed": "failed",
        "undelivered": "failed",
    }
    return status_map.get(twilio_status, "pending")
