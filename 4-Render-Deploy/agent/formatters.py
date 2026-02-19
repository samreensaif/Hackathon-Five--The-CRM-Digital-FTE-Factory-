"""
Response Formatters — Channel-Specific Output
==============================================
Formats agent responses for Gmail, WhatsApp, and Web Form channels
following brand-voice.md guidelines and the empathy selection matrix
from extracted-prompts.md.

Used by: tools.send_response
Source:  2-Transition-to-Production/documentation/extracted-prompts.md §3
"""

from __future__ import annotations

import re
from enum import Enum


class Channel(str, Enum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    WEB_FORM = "web_form"


# ── Empathy Phrases ──────────────────────────────────────────────────────
# Matrix from extracted-prompts.md §3 — tested against 62 tickets.

EMPATHY_MATRIX = {
    # (is_escalation, sentiment_bucket) → {channel: phrase}
    (True, "negative"): {
        Channel.EMAIL: (
            "I completely understand your frustration, and I'm sorry "
            "for the trouble you've been experiencing. "
        ),
        Channel.WHATSAPP: (
            "I completely understand your frustration and I'm sorry "
            "for the trouble. "
        ),
        Channel.WEB_FORM: (
            "I understand your concern and I want to make sure this "
            "gets the attention it deserves. "
        ),
    },
    (True, "neutral"): {
        Channel.EMAIL: (
            "Thanks for reaching out. I want to make sure you get "
            "the best help on this. "
        ),
        Channel.WHATSAPP: "",
        Channel.WEB_FORM: (
            "I've reviewed your request and want to make sure you "
            "get the most accurate help. "
        ),
    },
    (False, "negative"): {
        Channel.EMAIL: (
            "I understand how frustrating this must be, and I appreciate "
            "your patience. "
        ),
        Channel.WHATSAPP: "",
        Channel.WEB_FORM: "",
    },
    (False, "positive"): {
        Channel.EMAIL: "Thanks for reaching out! ",
        Channel.WHATSAPP: "",
        Channel.WEB_FORM: "",
    },
    (False, "neutral"): {
        Channel.EMAIL: "Thanks for contacting TaskFlow Support! ",
        Channel.WHATSAPP: "",
        Channel.WEB_FORM: "",
    },
}


def _get_sentiment_bucket(score: float) -> str:
    """Map sentiment score to bucket for empathy selection."""
    if score < -0.2:
        return "negative"
    elif score > 0.3:
        return "positive"
    return "neutral"


def _get_empathy_phrase(
    channel: Channel,
    is_escalation: bool,
    sentiment_score: float,
) -> str:
    """Select the appropriate empathy phrase from the matrix."""
    bucket = _get_sentiment_bucket(sentiment_score)
    key = (is_escalation, bucket)

    phrases = EMPATHY_MATRIX.get(key, EMPATHY_MATRIX[(False, "neutral")])
    return phrases.get(channel, "")


# ── WhatsApp Truncation ──────────────────────────────────────────────────
# From prototype.py — sentence-boundary-aware truncation.


def _whatsapp_truncate(text: str, max_chars: int = 280) -> str:
    """Truncate at sentence boundaries, never mid-word or mid-list-item.

    Uses negative lookbehind to avoid splitting after numbered list items
    (e.g., "1." "2." "3."). Appends "Want me to explain more?" if truncated.
    """
    if len(text) <= max_chars:
        return text

    # Split into sentences (avoid splitting after numbered items like "1.")
    sentences = re.split(r"(?<=[.!?])(?<!\d\.)(?<!\d\d\.)\s+", text)

    # Also split on newlines for list items
    chunks = []
    for s in sentences:
        for part in s.split("\n"):
            part = part.strip()
            if part:
                chunks.append(part)

    result = []
    current_len = 0

    for chunk in chunks:
        new_len = current_len + len(chunk) + (1 if result else 0)
        if new_len <= max_chars:
            result.append(chunk)
            current_len = new_len
        else:
            break

    if result:
        truncated = "\n".join(result)
        if truncated != text:
            truncated += "\n\nWant me to explain more?"
        return truncated

    # Fallback: truncate at last word boundary
    words = text.split()
    result_words = []
    current_len = 0
    for word in words:
        new_len = current_len + len(word) + (1 if result_words else 0)
        if new_len <= max_chars - 25:  # reserve space for suffix
            result_words.append(word)
            current_len = new_len
        else:
            break

    if result_words:
        return " ".join(result_words) + "...\n\nWant me to explain more?"

    return text[:max_chars]


# ── Channel Formatters ───────────────────────────────────────────────────


def _format_email(
    body: str,
    customer_name: str,
    ticket_id: str | None,
    is_escalation: bool,
    sentiment_score: float,
) -> str:
    """Format for Gmail — formal, structured, self-contained.

    Template from extracted-prompts.md §3 (Gmail Formatting):
      Dear {name},
      {empathy_opener}{body}
      Reference: {ticket_id}
      Best regards, TaskFlow Support Team
    """
    greeting = f"Dear {customer_name},"

    empathy = _get_empathy_phrase(Channel.EMAIL, is_escalation, sentiment_score)

    # Deduplicate: if the empathy phrase already appears in the body, skip it
    if empathy.strip() and empathy.strip().rstrip(". ") in body:
        empathy = ""

    ref = f"\n\nReference: {ticket_id}" if ticket_id else ""
    closing = (
        "\n\nBest regards,\n"
        "TaskFlow Support Team\n"
        "support@techcorp.io"
    )

    return f"{greeting}\n\n{empathy}{body}{ref}{closing}"


def _format_whatsapp(
    body: str,
    customer_name: str,
    is_escalation: bool,
    sentiment_score: float,
) -> str:
    """Format for WhatsApp — concise, conversational, emoji-friendly.

    Rules from brand-voice.md and extracted-prompts.md:
    - Keep under 300 chars
    - Casual-but-professional (contractions OK)
    - Emojis: max 1-2 per message (approved: checkmark, wave, wrench, bulb, point_right)
    - Truncate at sentence boundaries
    """
    if is_escalation:
        if sentiment_score < -0.3:
            return (
                f"Hi {customer_name}, I completely understand your frustration "
                f"and I'm sorry for the trouble. I'm connecting you with our "
                f"support team right now. They'll follow up shortly."
            )
        return (
            f"Hi {customer_name}! I'm connecting you with our support team "
            f"right now. They'll follow up shortly. Is there anything "
            f"quick I can help with in the meantime?"
        )

    formatted = _whatsapp_truncate(body, max_chars=280)
    return f"Hi {customer_name}!\n\n{formatted}"


def _format_web_form(
    body: str,
    customer_name: str,
    ticket_id: str | None,
    is_escalation: bool,
    sentiment_score: float,
) -> str:
    """Format for Web Form — semi-formal, includes ticket ID.

    Template from extracted-prompts.md §3 (Web Form Formatting):
      Hi {name},
      Thank you for contacting TaskFlow Support. We've received your request.
      Ticket ID: {ticket_id}
      {empathy}{body}
      -- TaskFlow Support Team
    """
    header = (
        f"Hi {customer_name},\n\n"
        f"Thank you for contacting TaskFlow Support. We've received your request."
    )

    tid = f"\n\n**Ticket ID:** {ticket_id}" if ticket_id else ""

    empathy = _get_empathy_phrase(Channel.WEB_FORM, is_escalation, sentiment_score)

    # Deduplicate empathy
    if empathy.strip() and empathy.strip().rstrip(". ") in body:
        empathy = ""

    footer = (
        "\n\nIf you need further assistance, you can reply to this message "
        "or reach us at support@techcorp.io."
        "\n\n-- TaskFlow Support Team"
    )

    return f"{header}{tid}\n\n{empathy}{body}{footer}"


# ── Public API ───────────────────────────────────────────────────────────


def format_for_channel(
    response: str,
    channel: str | Channel,
    customer_name: str = "Customer",
    ticket_id: str | None = None,
    is_escalation: bool = False,
    sentiment_score: float = 0.0,
) -> str:
    """Format a response for the specified channel.

    Applies channel-specific templates, empathy phrases, and truncation
    rules from brand-voice.md and extracted-prompts.md.

    Args:
        response: Raw response body text
        channel: Target channel ('email', 'whatsapp', 'web_form')
        customer_name: Customer's display name for greeting
        ticket_id: Ticket reference (TF-YYYYMMDD-XXXX)
        is_escalation: Whether this is an escalation acknowledgment
        sentiment_score: Customer sentiment (-1.0 to 1.0) for empathy selection

    Returns:
        Formatted response string ready for delivery.
    """
    # Normalize channel
    if isinstance(channel, str):
        # Handle legacy channel names from incubation
        channel_map = {
            "gmail": Channel.EMAIL,
            "email": Channel.EMAIL,
            "whatsapp": Channel.WHATSAPP,
            "web-form": Channel.WEB_FORM,
            "web_form": Channel.WEB_FORM,
        }
        channel = channel_map.get(channel.lower(), Channel.WEB_FORM)

    # Normalize customer name
    if not customer_name or customer_name in ("Unknown", "None", ""):
        customer_name = "there"

    if channel == Channel.EMAIL:
        return _format_email(response, customer_name, ticket_id, is_escalation, sentiment_score)
    elif channel == Channel.WHATSAPP:
        return _format_whatsapp(response, customer_name, is_escalation, sentiment_score)
    elif channel == Channel.WEB_FORM:
        return _format_web_form(response, customer_name, ticket_id, is_escalation, sentiment_score)
    else:
        return response
