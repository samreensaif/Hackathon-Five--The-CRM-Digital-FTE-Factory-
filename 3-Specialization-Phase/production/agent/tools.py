"""
Agent Tools — OpenAI Agents SDK @function_tool Definitions
===========================================================
Six production tools for the Customer Success Digital FTE agent.

Tools:
  1. search_knowledge_base — Semantic search over product docs (pgvector)
  2. create_ticket          — Create support ticket for tracking
  3. get_customer_history   — Cross-channel interaction history
  4. escalate_to_human      — Route to human agent with structured handoff
  5. send_response          — Format & deliver response via channel
  6. analyze_sentiment      — Keyword-based sentiment scoring

Dependencies:
  - database.queries (asyncpg)
  - agent.formatters (channel formatting)
  - agent.prompts (escalation routing, SLA)
  - openai (embeddings for knowledge base search)

Source: 2-Transition-to-Production/documentation/extracted-prompts.md §2
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Optional

from agents import function_tool
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from .formatters import format_for_channel
from .prompts import ESCALATION_ROUTING, SLA_BY_PLAN

logger = logging.getLogger("agent.tools")

# Lazy-initialized database pool — set by the FastAPI app on startup.
# Import: from agent.tools import set_db_pool
_db_pool = None


def set_db_pool(pool):
    """Set the shared database connection pool. Called once at app startup."""
    global _db_pool
    _db_pool = pool


def _get_pool():
    """Get the database pool, raising if not initialized."""
    if _db_pool is None:
        raise RuntimeError(
            "Database pool not initialized. Call set_db_pool() at app startup."
        )
    return _db_pool


# ── Tool 1: search_knowledge_base ───────────────────────────────────────


class KnowledgeSearchInput(BaseModel):
    """Input schema for knowledge base search."""

    query: str = Field(description="Search query for product documentation")
    max_results: int = Field(
        default=5, ge=1, le=10, description="Maximum number of results"
    )
    category: Optional[str] = Field(
        default=None,
        description="Filter by category: Getting Started, Core Features, Integrations, Troubleshooting, Frequently Asked Questions",
    )


@function_tool
async def search_knowledge_base(input: KnowledgeSearchInput) -> str:
    """Search TaskFlow product documentation for relevant information.

    Use this when the customer asks questions about:
    - Product features and capabilities
    - How to use specific features
    - Technical troubleshooting
    - Integration setup
    - Account management

    Returns formatted documentation excerpts with relevance scores.
    Do NOT use this when the ticket should be escalated — check escalation first.
    """
    from database.queries import search_knowledge_base as db_search

    try:
        # Generate embedding for the query
        client = AsyncOpenAI()
        embedding_response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=input.query,
        )
        query_embedding = embedding_response.data[0].embedding

        # Search database
        pool = _get_pool()
        results = await db_search(
            pool,
            query_embedding=query_embedding,
            top_k=input.max_results,
            similarity_threshold=0.3,
        )

        # Filter by category if specified
        if input.category and results:
            results = [
                r for r in results if input.category.lower() in (r.get("category") or "").lower()
            ] or results  # Fall back to unfiltered if no category matches

        if not results:
            return (
                "No relevant documentation found for that query. "
                "Consider rephrasing or asking the customer for more details. "
                "You can also direct them to app.taskflow.io/help."
            )

        # Format results
        output = []
        for i, result in enumerate(results, 1):
            title = result["title"]
            content = result["content"].strip()
            score = result.get("similarity_score", 0)

            # Truncate content to ~500 chars for context window efficiency
            if len(content) > 500:
                content = content[:500].rsplit(" ", 1)[0] + "..."

            output.append(
                f"### Result {i}: {title} (relevance: {score:.2f})\n{content}"
            )

        return "\n\n---\n\n".join(output)

    except RuntimeError:
        # Database not initialized — fallback message
        return (
            "Knowledge base is currently unavailable. Please ask the customer "
            "to check app.taskflow.io/help or try again later."
        )
    except Exception as e:
        logger.error(f"Knowledge base search failed: {e}")
        return (
            "I encountered an issue searching our documentation. "
            "You can direct the customer to app.taskflow.io/help for now."
        )


# ── Tool 2: create_ticket ───────────────────────────────────────────────


class TicketInput(BaseModel):
    """Input schema for ticket creation."""

    customer_id: str = Field(description="Customer UUID from database")
    issue: str = Field(description="Brief description of the customer's issue")
    priority: str = Field(
        default="medium",
        description="Priority: low, medium, high, urgent",
    )
    category: str = Field(
        default="general_inquiry",
        description="Category: billing_inquiry, technical, how_to, bug_report, integration_issue, feature_request, password_reset, data_concern, general_inquiry",
    )
    channel: str = Field(description="Source channel: email, whatsapp, web_form")


@function_tool
async def create_ticket(input: TicketInput) -> str:
    """Create a support ticket for tracking.

    ALWAYS create a ticket at the start of EVERY conversation.
    This is required for tracking and metrics.

    Returns the ticket ID (format: TF-YYYYMMDD-XXXX) for reference
    in all subsequent responses.
    """
    from database.queries import (
        create_conversation,
        create_ticket as db_create_ticket,
        get_active_conversation,
    )

    try:
        pool = _get_pool()
        customer_uuid = uuid.UUID(input.customer_id)

        # Get or create a conversation for this customer
        conversation = await get_active_conversation(pool, customer_uuid, input.channel)
        if not conversation:
            conversation = await create_conversation(pool, customer_uuid, input.channel)

        # Create the ticket
        ticket = await db_create_ticket(
            pool,
            conversation_id=conversation["id"],
            customer_id=customer_uuid,
            source_channel=input.channel,
            subject=input.issue,
            category=input.category,
            priority=input.priority,
        )

        return (
            f"Ticket created successfully.\n"
            f"**Ticket ID:** {ticket['ticket_ref']}\n"
            f"**Priority:** {input.priority}\n"
            f"**Category:** {input.category}\n"
            f"**Status:** open\n\n"
            f"Use this ticket ID ({ticket['ticket_ref']}) in all responses to the customer."
        )

    except Exception as e:
        logger.error(f"Ticket creation failed: {e}")
        # Generate a fallback ticket ref for tracking
        from datetime import datetime, timezone

        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        fallback_ref = f"TF-{date_str}-{uuid.uuid4().hex[:4].upper()}"
        return (
            f"Ticket tracking note: Database unavailable, using reference {fallback_ref}.\n"
            f"Please include this reference in your response."
        )


# ── Tool 3: get_customer_history ────────────────────────────────────────


class CustomerHistoryInput(BaseModel):
    """Input schema for customer history lookup."""

    customer_id: str = Field(
        description="Customer identifier — UUID, email address, or phone number"
    )


@function_tool
async def get_customer_history(input: CustomerHistoryInput) -> str:
    """Get customer's complete interaction history across ALL channels.

    Use this to understand context from previous conversations,
    even if they happened on a different channel (email vs WhatsApp).

    Shows:
    - Past conversations and their outcomes
    - Topics previously discussed
    - Sentiment trends
    - Channel usage patterns

    ALWAYS call this at the start of every new ticket to check for
    prior interactions and avoid repeating solutions.
    """
    from database.queries import (
        get_customer_by_identifier,
        get_customer_full_history,
    )

    try:
        pool = _get_pool()

        # Try to parse as UUID first, then resolve as identifier
        customer_uuid = None
        try:
            customer_uuid = uuid.UUID(input.customer_id)
        except ValueError:
            # Not a UUID — resolve as email or phone
            identifier_type = "email" if "@" in input.customer_id else "phone"
            customer = await get_customer_by_identifier(
                pool, identifier_type, input.customer_id
            )
            if customer:
                customer_uuid = customer["id"]

        if not customer_uuid:
            return (
                f"No previous interactions found for '{input.customer_id}'. "
                f"This appears to be a new customer."
            )

        history = await get_customer_full_history(pool, customer_uuid)

        if not history.get("found"):
            return (
                f"No previous interactions found for this customer. "
                f"This is their first contact."
            )

        # Format the history summary
        customer = history["customer"]
        lines = [
            f"## Customer History: {customer.get('name', 'Unknown')}",
            f"- **Email:** {customer.get('email', 'N/A')}",
            f"- **Plan:** {customer.get('plan', 'free')}",
            f"- **Total conversations:** {history['conversation_count']}",
            f"- **Channels used:** {', '.join(history['all_channels']) or 'none'}",
            f"- **Topics discussed:** {', '.join(history['all_topics']) or 'none'}",
            f"- **Average sentiment:** {history['average_sentiment']}",
            f"- **Last contact:** {customer.get('last_contact_at', 'N/A')}",
        ]

        # Recent conversations
        conversations = history.get("conversations", [])
        if conversations:
            lines.append("\n### Recent Conversations:")
            for conv in conversations[:5]:
                status = conv.get("status", "unknown")
                channel = conv.get("initial_channel", "?")
                sentiment = conv.get("sentiment_trend", "unknown")
                topics = ", ".join(conv.get("topics") or []) or "general"
                escalation = ""
                if conv.get("escalation_reason"):
                    escalation = f" [ESCALATED: {conv['escalation_reason'][:60]}]"
                lines.append(
                    f"- [{status}] via {channel} | topics: {topics} | "
                    f"sentiment: {sentiment}{escalation}"
                )

        # Recent messages (for cross-channel context)
        recent_msgs = history.get("recent_messages", [])
        if recent_msgs:
            lines.append("\n### Recent Messages (last 5):")
            for msg in recent_msgs[-5:]:
                role = msg.get("role", "?")
                channel = msg.get("channel", "?")
                content = msg.get("content", "")[:100]
                if len(msg.get("content", "")) > 100:
                    content += "..."
                lines.append(f"- [{role}/{channel}] {content}")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Customer history lookup failed: {e}")
        return (
            f"Could not retrieve history for '{input.customer_id}'. "
            f"Proceeding as if this is a new customer."
        )


# ── Tool 4: escalate_to_human ───────────────────────────────────────────


class EscalationInput(BaseModel):
    """Input schema for ticket escalation."""

    ticket_id: str = Field(description="Ticket reference ID (TF-YYYYMMDD-XXXX)")
    reason: str = Field(description="Detailed reason for escalation")
    urgency: str = Field(
        default="normal",
        description="Urgency: low, normal, high, critical",
    )
    category: str = Field(
        default="general",
        description="Category for routing: billing, legal, security, account, technical, churn, general",
    )
    context_summary: str = Field(
        default="",
        description="Brief summary of the conversation so far",
    )


@function_tool
async def escalate_to_human(input: EscalationInput) -> str:
    """Escalate a conversation to a human support agent.

    Use this when:
    - Customer asks about pricing, refunds, or billing disputes (→ billing)
    - Customer mentions legal action, lawyers, GDPR, CCPA (→ legal)
    - Customer reports security issues or unauthorized access (→ security)
    - Customer requests account/workspace deletion (→ account)
    - Customer sentiment is very negative (score < -0.3)
    - You cannot find relevant information after 2 searches
    - Customer explicitly requests a human ("talk to a real person")
    - 2+ LIKELY ESCALATE signals fire simultaneously

    ALWAYS tell the customer who will handle their case and the expected
    response time based on their plan tier.
    """
    from database.queries import escalate_ticket, get_ticket_by_ref

    # Determine routing
    routing = ESCALATION_ROUTING.get(
        input.category, ESCALATION_ROUTING["general"]
    )

    # Map urgency to response time
    urgency_map = {
        "critical": "< 15 minutes",
        "high": "< 1 hour",
        "normal": "< 4 hours",
        "low": "< 24 hours",
    }
    response_time = urgency_map.get(input.urgency, "< 4 hours")

    try:
        pool = _get_pool()

        # Look up the ticket
        ticket = await get_ticket_by_ref(pool, input.ticket_id)
        if ticket:
            await escalate_ticket(
                pool,
                ticket_id=ticket["id"],
                assigned_to=routing["name"],
                assigned_to_email=routing["email"],
                reason=input.reason,
            )

    except Exception as e:
        logger.error(f"Escalation DB update failed: {e}")
        # Continue anyway — the routing info is still valid

    # Build escalation handoff (from escalation-rules.md format)
    escalation_id = f"ESC-{uuid.uuid4().hex[:8].upper()}"

    return (
        f"## Escalation Confirmed\n\n"
        f"**Escalation ID:** {escalation_id}\n"
        f"**Ticket:** {input.ticket_id}\n"
        f"**Assigned to:** {routing['name']} ({routing['email']})\n"
        f"**Category:** {input.category}\n"
        f"**Urgency:** {input.urgency}\n"
        f"**Expected response:** {response_time}\n"
        f"**Reason:** {input.reason}\n\n"
        f"Tell the customer:\n"
        f"- Their case has been assigned to {routing['name']}\n"
        f"- They can expect a response within {response_time}\n"
        f"- Reference their ticket ID: {input.ticket_id}\n"
        f"- Show empathy appropriate to the situation"
    )


# ── Tool 5: send_response ───────────────────────────────────────────────


class ResponseInput(BaseModel):
    """Input schema for sending a formatted response."""

    ticket_id: str = Field(description="Ticket reference ID")
    message: str = Field(description="Response message body to send")
    channel: str = Field(description="Target channel: email, whatsapp, web_form")
    customer_name: str = Field(
        default="Customer", description="Customer name for greeting"
    )
    is_escalation: bool = Field(
        default=False, description="Whether this is an escalation acknowledgment"
    )
    sentiment_score: float = Field(
        default=0.0, description="Customer sentiment score for empathy calibration"
    )


@function_tool
async def send_response(input: ResponseInput) -> str:
    """Format and deliver a response to the customer on their channel.

    The response will be automatically formatted:
    - Email: Formal with Dear greeting, signature, ticket reference
    - WhatsApp: Concise (<300 chars), conversational, approved emojis only
    - Web Form: Semi-formal, ticket ID, actionable next steps

    ALWAYS use this tool to send responses. The formatting ensures
    brand-voice compliance across all channels.
    """
    from database.queries import add_message, get_active_conversation, get_ticket_by_ref

    # Format the message for the channel
    formatted = format_for_channel(
        response=input.message,
        channel=input.channel,
        customer_name=input.customer_name,
        ticket_id=input.ticket_id,
        is_escalation=input.is_escalation,
        sentiment_score=input.sentiment_score,
    )

    # Store in database
    try:
        pool = _get_pool()

        # Find the conversation via ticket
        ticket = await get_ticket_by_ref(pool, input.ticket_id)
        if ticket:
            await add_message(
                pool,
                conversation_id=ticket["conversation_id"],
                channel=input.channel,
                direction="outbound",
                role="agent",
                content=formatted,
            )

    except Exception as e:
        logger.error(f"Failed to store response in DB: {e}")
        # Continue — delivery is more important than storage

    return (
        f"**Response sent via {input.channel}**\n\n"
        f"---\n{formatted}\n---\n\n"
        f"Character count: {len(formatted)}"
    )


# ── Tool 6: analyze_sentiment ───────────────────────────────────────────


@function_tool
async def analyze_sentiment(text: str) -> str:
    """Analyze the sentiment of a customer message.

    Returns sentiment score (-1.0 to +1.0), label, and confidence.
    Use this to:
    - Calibrate your response tone
    - Detect if the customer is frustrated before responding
    - Inform escalation decisions (score < -0.3 triggers escalation review)
    - Track sentiment changes across a conversation
    """
    score = _analyze_sentiment_score(text)

    # Determine label
    if score >= 0.3:
        label = "positive"
    elif score <= -0.3:
        label = "negative"
    else:
        label = "neutral"

    # Determine confidence from magnitude
    magnitude = abs(score)
    if magnitude >= 0.7:
        confidence = "high"
    elif magnitude >= 0.3:
        confidence = "medium"
    else:
        confidence = "low"

    # Build actionable interpretation
    if score < -0.3:
        interpretation = (
            "Customer appears frustrated or upset. Use empathetic language "
            "and consider escalation if other signals are present."
        )
    elif score < -0.1:
        interpretation = (
            "Customer has mild negative sentiment. Acknowledge their concern "
            "before providing a solution."
        )
    elif score > 0.3:
        interpretation = (
            "Customer has positive sentiment. Maintain a warm, helpful tone."
        )
    else:
        interpretation = "Customer sentiment is neutral. Use standard professional tone."

    return (
        f"**Sentiment Analysis:**\n"
        f"- Score: {score:.2f} (scale: -1.0 very negative to +1.0 very positive)\n"
        f"- Label: {label}\n"
        f"- Confidence: {confidence}\n"
        f"- Interpretation: {interpretation}"
    )


# ── Sentiment Analyzer (ported from incubation prototype.py) ─────────────
# Keyword-based sentiment scoring. In production, this provides a fast
# pre-filter before the LLM's own judgment.

_POSITIVE_WORDS = {
    "love": 2, "amazing": 2, "excellent": 2, "fantastic": 2, "perfect": 2,
    "outstanding": 2, "incredible": 2, "wonderful": 2, "brilliant": 2,
    "great": 1, "good": 1, "nice": 1, "helpful": 1, "thanks": 1, "thank": 1,
    "appreciate": 1, "happy": 1, "pleased": 1, "enjoy": 1, "glad": 1,
    "awesome": 1, "impressive": 1, "smooth": 1, "easy": 1, "convenient": 1,
    "improved": 1, "fast": 1, "reliable": 1, "intuitive": 1, "clean": 1,
    "productive": 1, "efficient": 1, "solid": 1, "useful": 1,
}

_NEGATIVE_WORDS = {
    "terrible": 3, "worst": 3, "garbage": 3, "useless": 3, "unacceptable": 3,
    "awful": 3, "horrible": 3, "disgusting": 3, "pathetic": 3, "hate": 3,
    "scam": 3,
    "broken": 2, "frustrated": 2, "frustrating": 2, "angry": 2, "annoying": 2,
    "furious": 2, "ridiculous": 2, "disappointed": 2, "unresponsive": 2,
    "unusable": 2, "failing": 2, "disaster": 2, "outraged": 2, "ruined": 2,
    "wasted": 2,
    "issue": 1, "problem": 1, "bug": 1, "error": 1, "stuck": 1,
    "slow": 1, "confusing": 1, "difficult": 1, "crash": 1, "crashing": 1,
    "missing": 1, "lost": 1, "fail": 1, "failed": 1, "wrong": 1,
    "concern": 1, "worried": 1, "trouble": 1, "unfortunately": 1,
    "worse": 1, "lag": 1, "delay": 1, "glitch": 1,
}

_NEGATION_WORDS = {
    "not", "n't", "no", "never", "neither", "nobody", "nothing",
    "nowhere", "hardly", "barely", "without",
}

_INTENSIFIERS = {
    "very": 1.5, "really": 1.5, "extremely": 2.0, "absolutely": 2.0,
    "completely": 1.5, "totally": 1.5, "so": 1.3, "incredibly": 2.0,
    "beyond": 1.5, "super": 1.5,
}


def _analyze_sentiment_score(text: str) -> float:
    """Keyword-based sentiment scoring from -1.0 to 1.0.

    Ported from prototype.py SentimentAnalyzer.analyze() — identical logic
    to ensure consistent behavior with incubation test results.
    """
    if not text or len(text.strip()) < 2:
        return 0.0

    words = re.findall(r"[a-z']+", text.lower())
    if not words:
        return 0.0

    pos_score = 0.0
    neg_score = 0.0
    prev_word = ""
    prev_prev_word = ""

    for word in words:
        multiplier = 1.0
        if prev_word in _INTENSIFIERS:
            multiplier = _INTENSIFIERS[prev_word]

        negated = False
        if prev_word in _NEGATION_WORDS or (
            prev_word.endswith("n't") or prev_prev_word in _NEGATION_WORDS
        ):
            negated = True

        if word in _POSITIVE_WORDS:
            weight = _POSITIVE_WORDS[word] * multiplier
            if negated:
                neg_score += weight * 0.5
            else:
                pos_score += weight

        if word in _NEGATIVE_WORDS:
            weight = _NEGATIVE_WORDS[word] * multiplier
            if negated:
                pos_score += weight * 0.3
            else:
                neg_score += weight

        prev_prev_word = prev_word
        prev_word = word

    # ALL CAPS detection (anger signal)
    alpha_chars = re.sub(r"[^a-zA-Z]", "", text)
    if len(alpha_chars) > 15 and alpha_chars == alpha_chars.upper():
        neg_score += 5.0

    # Exclamation marks amplify existing sentiment
    excl_count = text.count("!")
    if excl_count >= 3:
        if neg_score > pos_score:
            neg_score *= 1.3
        elif pos_score > neg_score:
            pos_score *= 1.2

    # Normalize to -1..1 range
    total = pos_score + neg_score
    if total == 0:
        return 0.0

    raw = (pos_score - neg_score) / total
    return round(max(-1.0, min(1.0, raw)), 2)
