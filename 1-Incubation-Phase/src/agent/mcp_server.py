"""
Customer Success FTE — MCP Server
===================================
Exposes the agent's capabilities as MCP tools for use by LLM clients.

Tools:
  1. search_knowledge_base  — TF-IDF search over product docs
  2. create_ticket          — Create and process a new support ticket
  3. get_customer_history   — Retrieve cross-channel conversation history
  4. escalate_to_human      — Manually escalate a ticket
  5. send_response          — Format and send a response via channel
  6. analyze_sentiment      — Analyze text sentiment

Usage:
    python mcp_server.py                    # stdio transport (default)
    python mcp_server.py --transport sse    # SSE transport on port 8000
"""

import sys
import os
from pathlib import Path

# Ensure the agent package is importable
AGENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(AGENT_DIR))

from mcp.server.fastmcp import FastMCP

from prototype import (
    CONTEXT_DIR, KnowledgeBase, SentimentAnalyzer,
    ResponseFormatter, Ticket, CustomerSuccessAgent,
)
from conversation_manager import ConversationManager

# ── Initialize ─────────────────────────────────────────────────────────────

mcp = FastMCP(
    "TaskFlow Customer Success FTE",
    instructions=(
        "You are a customer success agent for TaskFlow, a project management SaaS. "
        "Use these tools to search docs, manage tickets, track conversations, "
        "analyze sentiment, and escalate issues."
    ),
)

# Shared state
_kb = KnowledgeBase(CONTEXT_DIR / "product-docs.md")
_sentiment = SentimentAnalyzer()
_formatter = ResponseFormatter()
_cm = ConversationManager()
_agent = CustomerSuccessAgent(conversation_manager=_cm)

# Escalation routing from escalation-rules.md
ESCALATION_ROUTING = {
    "billing":    {"name": "Lisa Tanaka",    "email": "billing@techcorp.io",           "tier": 1},
    "legal":      {"name": "Rachel Foster",  "email": "legal@techcorp.io",             "tier": 1},
    "security":   {"name": "James Okafor",   "email": "security@techcorp.io",          "tier": 1},
    "account":    {"name": "Sarah Chen",     "email": "cs-lead@techcorp.io",           "tier": 1},
    "technical":  {"name": "Priya Patel",    "email": "engineering-support@techcorp.io","tier": 1},
    "churn":      {"name": "Marcus Rivera",  "email": "cs-lead@techcorp.io",           "tier": 1},
    "general":    {"name": "Marcus Rivera",  "email": "cs-lead@techcorp.io",           "tier": 1},
}

SLA_BY_PLAN = {
    "enterprise": "1 hour",
    "pro": "4 hours",
    "free": "24 hours",
}


# ── Tool 1: search_knowledge_base ─────────────────────────────────────────

@mcp.tool()
def search_knowledge_base(query: str, max_results: int = 5) -> str:
    """Search TaskFlow product documentation using TF-IDF relevance scoring.

    Args:
        query: Search query (natural language or keywords)
        max_results: Maximum number of doc sections to return (1-10, default 5)
    """
    max_results = max(1, min(10, max_results))
    results = _kb.search(query, top_k=max_results)

    if not results:
        return "No relevant documentation found for that query."

    output = []
    for i, section in enumerate(results, 1):
        title = section["title"]
        body = section["body"].strip()
        # Truncate body to ~500 chars for readability
        if len(body) > 500:
            body = body[:500].rsplit(" ", 1)[0] + "..."
        output.append(f"### Result {i}: {title}\n{body}")

    return "\n\n---\n\n".join(output)


# ── Tool 2: create_ticket ─────────────────────────────────────────────────

@mcp.tool()
def create_ticket(
    customer_email: str,
    customer_name: str,
    subject: str,
    message: str,
    channel: str = "web-form",
    priority: str = "medium",
    category: str = "",
    customer_plan: str = "free",
) -> dict:
    """Create a new support ticket and process it through the agent pipeline.

    Args:
        customer_email: Customer's email address
        customer_name: Customer's display name
        subject: Ticket subject line
        message: Full message body from the customer
        channel: Contact channel (gmail, whatsapp, web-form)
        priority: Priority level (critical, high, medium, low)
        category: Issue category (billing, technical, how-to, bug-report, etc.)
        customer_plan: Customer's plan tier (free, pro, enterprise)
    """
    import uuid
    from datetime import datetime, timezone

    ticket_id = f"TF-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

    ticket = Ticket(
        id=ticket_id,
        channel=channel,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_plan=customer_plan,
        subject=subject,
        message=message,
        category=category,
        priority=priority,
    )

    # Process through agent with conversation context
    response = _agent.handle_ticket_with_context(ticket)

    return {
        "ticket_id": ticket_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "escalated" if response.should_escalate else "active",
        "detected_intent": response.detected_intent,
        "detected_sentiment": response.detected_sentiment,
        "confidence_score": response.confidence_score,
        "should_escalate": response.should_escalate,
        "escalation_reason": response.escalation_reason or None,
        "response_text": response.response_text,
        "matched_docs": response.matched_docs,
    }


# ── Tool 3: get_customer_history ──────────────────────────────────────────

@mcp.tool()
def get_customer_history(customer_id: str) -> dict:
    """Retrieve all past interactions for a customer across all channels.

    Args:
        customer_id: Customer identifier (email address or phone number)
    """
    history = _cm.get_customer_history(customer_id)

    if history["conversation_count"] == 0:
        return {
            "customer_id": customer_id,
            "found": False,
            "message": "No previous interactions found for this customer.",
        }

    # Compute summary sentiment
    sentiments = history.get("sentiment_trend", [])
    avg_sentiment = (
        sum(s["score"] for s in sentiments) / len(sentiments)
        if sentiments else 0.0
    )

    return {
        "customer_id": history["customer_id"],
        "found": True,
        "conversation_count": history["conversation_count"],
        "all_topics": history["all_topics"],
        "all_channels": history["all_channels"],
        "average_sentiment": round(avg_sentiment, 2),
        "sentiment_trend": sentiments[-10:],  # last 10 data points
        "last_contact": history["last_contact"],
        "conversations": history["conversations"],
    }


# ── Tool 4: escalate_to_human ─────────────────────────────────────────────

@mcp.tool()
def escalate_to_human(
    ticket_id: str,
    reason: str,
    urgency: str = "within_4_hours",
    category: str = "general",
) -> dict:
    """Escalate a ticket to a human agent with structured handoff.

    Args:
        ticket_id: The ticket ID to escalate
        reason: Reason for escalation (free text)
        urgency: Urgency level (immediate, within_1_hour, within_4_hours, within_24_hours)
        category: Escalation category for routing (billing, legal, security, account, technical, churn, general)
    """
    import uuid

    # Find the conversation containing this ticket
    target_conv = None
    for conv in _cm._conversations.values():
        for msg in conv.messages:
            tid = msg.ticket_id if hasattr(msg, "ticket_id") else msg.get("ticket_id", "")
            if tid == ticket_id:
                target_conv = conv
                break
        if target_conv:
            break

    escalation_id = f"ESC-{uuid.uuid4().hex[:8].upper()}"

    # Route to the right person
    routing = ESCALATION_ROUTING.get(category, ESCALATION_ROUTING["general"])
    plan = target_conv.customer_plan if target_conv else "free"
    sla = SLA_BY_PLAN.get(plan, "24 hours")

    # Update conversation state
    if target_conv:
        _cm.escalate_conversation(target_conv.conversation_id, reason, escalation_id)

    urgency_map = {
        "immediate": "< 15 minutes",
        "within_1_hour": "< 1 hour",
        "within_4_hours": "< 4 hours",
        "within_24_hours": "< 24 hours",
    }

    return {
        "escalation_id": escalation_id,
        "ticket_id": ticket_id,
        "assigned_to": routing["name"],
        "assigned_email": routing["email"],
        "tier": routing["tier"],
        "urgency": urgency,
        "estimated_response_time": urgency_map.get(urgency, sla),
        "category": category,
        "reason": reason,
        "status": "escalated",
    }


# ── Tool 5: send_response ─────────────────────────────────────────────────

@mcp.tool()
def send_response(
    ticket_id: str,
    message: str,
    channel: str,
    customer_name: str = "",
    is_escalation: bool = False,
) -> dict:
    """Format and deliver a response to a customer on their channel.

    Args:
        ticket_id: Ticket reference ID
        message: The raw response message body
        channel: Delivery channel (gmail, whatsapp, web-form)
        customer_name: Customer name for greeting
        is_escalation: Whether this is an escalation acknowledgment
    """
    # Analyze sentiment of the response we're sending (for tone consistency)
    response_sentiment = _sentiment.analyze(message)

    formatted = _formatter.format(
        channel=channel,
        customer_name=customer_name or "there",
        body=message,
        ticket_id=ticket_id,
        is_escalation=is_escalation,
        sentiment=0.0,  # agent responses use neutral base tone
    )

    # Record in conversation if we can find it
    for conv in _cm._conversations.values():
        for msg in conv.messages:
            tid = msg.ticket_id if hasattr(msg, "ticket_id") else msg.get("ticket_id", "")
            if tid == ticket_id:
                _cm.add_message(
                    conversation_id=conv.conversation_id,
                    role="agent",
                    content=formatted,
                    channel=channel,
                    ticket_id=ticket_id,
                )
                break

    return {
        "delivery_status": "sent",
        "channel": channel,
        "ticket_id": ticket_id,
        "formatted_message": formatted,
        "character_count": len(formatted),
    }


# ── Tool 6: analyze_sentiment ─────────────────────────────────────────────

@mcp.tool()
def analyze_sentiment(text: str) -> dict:
    """Analyze the sentiment of a text message.

    Args:
        text: The text to analyze for sentiment
    """
    score = _sentiment.analyze(text)

    if score >= 0.3:
        label = "positive"
    elif score <= -0.3:
        label = "negative"
    else:
        label = "neutral"

    # Confidence based on magnitude
    magnitude = abs(score)
    if magnitude >= 0.7:
        confidence = "high"
    elif magnitude >= 0.3:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "score": score,
        "label": label,
        "confidence": confidence,
        "scale": "-1.0 (very negative) to +1.0 (very positive)",
    }


# ── MCP Resources (read-only context) ─────────────────────────────────────

@mcp.resource("docs://product-docs")
def get_product_docs() -> str:
    """Full TaskFlow product documentation."""
    return (CONTEXT_DIR / "product-docs.md").read_text(encoding="utf-8")


@mcp.resource("docs://escalation-rules")
def get_escalation_rules() -> str:
    """Escalation rules and routing table."""
    return (CONTEXT_DIR / "escalation-rules.md").read_text(encoding="utf-8")


@mcp.resource("docs://brand-voice")
def get_brand_voice() -> str:
    """Brand voice and channel formatting guidelines."""
    return (CONTEXT_DIR / "brand-voice.md").read_text(encoding="utf-8")


@mcp.resource("stats://conversations")
def get_conversation_stats() -> str:
    """Current conversation manager statistics."""
    stats = _cm.stats
    return (
        f"Total conversations: {stats['total_conversations']}\n"
        f"Active: {stats['active']}\n"
        f"Escalated: {stats['escalated']}\n"
        f"Resolved: {stats['resolved']}\n"
        f"Unique customers: {stats['unique_customers']}"
    )


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    transport = "stdio"
    if "--transport" in sys.argv:
        idx = sys.argv.index("--transport")
        if idx + 1 < len(sys.argv):
            transport = sys.argv[idx + 1]

    if transport == "sse":
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
