"""
Customer Success Digital FTE — Database Query Functions
========================================================
Async database operations using asyncpg for the production agent.

All functions accept a connection pool (asyncpg.Pool) and return typed results.
Designed for use with FastAPI dependency injection:

    from database.queries import get_or_create_customer
    pool = app.state.db_pool
    customer = await get_or_create_customer(pool, email="alice@example.com")

Connection pool creation:
    import asyncpg
    pool = await asyncpg.create_pool(dsn="postgresql://user:pass@host/db")

Tables referenced: customers, customer_identifiers, conversations, messages,
                   tickets, knowledge_base, agent_metrics
Schema: database/schema.sql
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import asyncpg


# ── Helpers ────────────────────────────────────────────────────────────────


async def _fetchrow(pool: asyncpg.Pool, query: str, *args) -> Optional[dict]:
    """Execute a query and return a single row as a dict (or None)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None


async def _fetch(pool: asyncpg.Pool, query: str, *args) -> list[dict]:
    """Execute a query and return all rows as a list of dicts."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *args)
        return [dict(r) for r in rows]


async def _execute(pool: asyncpg.Pool, query: str, *args) -> str:
    """Execute a query and return the status string."""
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


# ── 1. Customer Management ────────────────────────────────────────────────


async def get_or_create_customer(
    pool: asyncpg.Pool,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    name: Optional[str] = None,
    plan: str = "free",
) -> dict:
    """Find an existing customer by email or phone, or create a new one.

    Resolution order:
      1. Exact email match on customers.email
      2. Exact phone match on customers.phone
      3. Lookup via customer_identifiers (email or phone)
      4. Create new customer

    Returns: dict with customer row (id, email, phone, name, plan, ...)
    """
    # Try email lookup first (most common)
    if email:
        row = await _fetchrow(
            pool,
            "SELECT * FROM customers WHERE email = $1",
            email,
        )
        if row:
            # Update last_contact_at
            await _execute(
                pool,
                "UPDATE customers SET last_contact_at = NOW() WHERE id = $1",
                row["id"],
            )
            return row

    # Try phone lookup
    if phone:
        row = await _fetchrow(
            pool,
            "SELECT * FROM customers WHERE phone = $1",
            phone,
        )
        if row:
            await _execute(
                pool,
                "UPDATE customers SET last_contact_at = NOW() WHERE id = $1",
                row["id"],
            )
            return row

    # Try customer_identifiers table (cross-channel resolution)
    identifier = email or phone
    identifier_type = "email" if email else "phone"
    if identifier:
        row = await _fetchrow(
            pool,
            """
            SELECT c.* FROM customers c
            JOIN customer_identifiers ci ON ci.customer_id = c.id
            WHERE ci.identifier_type = $1 AND ci.identifier_value = $2
            """,
            identifier_type,
            identifier,
        )
        if row:
            await _execute(
                pool,
                "UPDATE customers SET last_contact_at = NOW() WHERE id = $1",
                row["id"],
            )
            return row

    # Create new customer
    row = await _fetchrow(
        pool,
        """
        INSERT INTO customers (email, phone, name, plan, last_contact_at)
        VALUES ($1, $2, $3, $4, NOW())
        RETURNING *
        """,
        email,
        phone,
        name,
        plan,
    )

    # Also create identity records
    if row:
        if email:
            await link_customer_identifier(
                pool, row["id"], "email", email, verified=True
            )
        if phone:
            await link_customer_identifier(
                pool, row["id"], "phone", phone, verified=True
            )

    return row


# ── 2. Identity Linking ──────────────────────────────────────────────────


async def link_customer_identifier(
    pool: asyncpg.Pool,
    customer_id: uuid.UUID,
    identifier_type: str,
    identifier_value: str,
    verified: bool = False,
) -> dict:
    """Link an identifier (email, phone, whatsapp) to a customer.

    Uses ON CONFLICT to avoid duplicates — if the identifier already exists,
    the verified flag is updated (only upgraded, never downgraded).

    Returns: dict with the identifier row.
    """
    return await _fetchrow(
        pool,
        """
        INSERT INTO customer_identifiers (customer_id, identifier_type, identifier_value, verified)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (identifier_type, identifier_value)
        DO UPDATE SET verified = GREATEST(customer_identifiers.verified, EXCLUDED.verified)
        RETURNING *
        """,
        customer_id,
        identifier_type,
        identifier_value,
        verified,
    )


async def get_customer_by_identifier(
    pool: asyncpg.Pool,
    identifier_type: str,
    identifier_value: str,
) -> Optional[dict]:
    """Resolve any identifier to the canonical customer record.

    Args:
        identifier_type: 'email', 'phone', or 'whatsapp'
        identifier_value: The actual value (e.g., 'alice@example.com', '+15551234567')

    Returns: Customer dict or None if not found.
    """
    return await _fetchrow(
        pool,
        """
        SELECT c.* FROM customers c
        JOIN customer_identifiers ci ON ci.customer_id = c.id
        WHERE ci.identifier_type = $1 AND ci.identifier_value = $2
        """,
        identifier_type,
        identifier_value,
    )


# ── 3. Conversations ─────────────────────────────────────────────────────


async def create_conversation(
    pool: asyncpg.Pool,
    customer_id: uuid.UUID,
    channel: str,
) -> dict:
    """Create a new conversation for a customer.

    Sets initial_channel and current_channel to the provided channel,
    and adds the channel to channels_used array.

    Returns: dict with the new conversation row.
    """
    return await _fetchrow(
        pool,
        """
        INSERT INTO conversations (customer_id, initial_channel, current_channel, channels_used)
        VALUES ($1, $2::text, $2::text, ARRAY[$2::text])
        RETURNING *
        """,
        customer_id,
        channel,
    )


async def get_active_conversation(
    pool: asyncpg.Pool,
    customer_id: uuid.UUID,
    channel: Optional[str] = None,
) -> Optional[dict]:
    """Find the most recent active or escalated conversation for a customer.

    Escalated conversations are reused for follow-up messages (from incubation
    learning — see discovery-log.md Entry 3). Active conversations are preferred
    over escalated.

    Args:
        customer_id: The customer's UUID
        channel: If provided, also updates the current_channel and channels_used

    Returns: Conversation dict or None if no active/escalated conversation.
    """
    row = await _fetchrow(
        pool,
        """
        SELECT * FROM conversations
        WHERE customer_id = $1 AND status IN ('active', 'escalated')
        ORDER BY
            CASE status WHEN 'active' THEN 0 ELSE 1 END,
            last_message_at DESC
        LIMIT 1
        """,
        customer_id,
    )

    # Update channel tracking if conversation found and channel provided
    if row and channel:
        await _execute(
            pool,
            """
            UPDATE conversations
            SET current_channel = $2::text,
                channels_used = CASE
                    WHEN NOT ($2::text = ANY(channels_used)) THEN array_append(channels_used, $2::text)
                    ELSE channels_used
                END,
                last_message_at = NOW()
            WHERE id = $1
            """,
            row["id"],
            channel,
        )

    return row


async def update_conversation_sentiment(
    pool: asyncpg.Pool,
    conversation_id: uuid.UUID,
    sentiment_score: float,
    sentiment_trend: str = "stable",
) -> None:
    """Update the sentiment score and trend for a conversation.

    Sentiment trend is computed by the agent pipeline based on message history:
    - 'improving': last 3 messages trend positive
    - 'declining': last 3 messages trend negative (triggers auto-escalation check)
    - 'stable': no significant change

    Args:
        conversation_id: Conversation UUID
        sentiment_score: Latest score from -1.00 to 1.00
        sentiment_trend: One of 'improving', 'stable', 'declining', 'unknown'
    """
    await _execute(
        pool,
        """
        UPDATE conversations
        SET sentiment_score = $2,
            sentiment_trend = $3,
            last_message_at = NOW()
        WHERE id = $1
        """,
        conversation_id,
        sentiment_score,
        sentiment_trend,
    )


async def resolve_conversation(
    pool: asyncpg.Pool,
    conversation_id: uuid.UUID,
    resolution_notes: Optional[str] = None,
) -> None:
    """Mark a conversation as resolved."""
    await _execute(
        pool,
        """
        UPDATE conversations
        SET status = 'resolved', ended_at = NOW(), resolution_notes = $2
        WHERE id = $1
        """,
        conversation_id,
        resolution_notes,
    )


async def update_conversation_topics(
    pool: asyncpg.Pool,
    conversation_id: uuid.UUID,
    topics: list[str],
) -> None:
    """Add topics to a conversation's topic list (deduplicates)."""
    await _execute(
        pool,
        """
        UPDATE conversations
        SET topics = (
            SELECT ARRAY(SELECT DISTINCT unnest(topics || $2::text[]))
        )
        WHERE id = $1
        """,
        conversation_id,
        topics,
    )


# ── 4. Messages ──────────────────────────────────────────────────────────


async def add_message(
    pool: asyncpg.Pool,
    conversation_id: uuid.UUID,
    channel: str,
    direction: str,
    role: str,
    content: str,
    sentiment_score: Optional[float] = None,
    intent: Optional[str] = None,
    tokens_used: Optional[int] = None,
    latency_ms: Optional[int] = None,
    tool_calls: Optional[dict] = None,
    channel_message_id: Optional[str] = None,
) -> dict:
    """Add a message to a conversation.

    Also updates the conversation's last_message_at and the customer's
    last_contact_at and total_conversations counter.

    Args:
        conversation_id: Parent conversation UUID
        channel: 'email', 'whatsapp', or 'web_form'
        direction: 'inbound' (from customer) or 'outbound' (from agent)
        role: 'customer', 'agent', or 'system'
        content: Message text
        sentiment_score: Sentiment analysis result (-1.0 to 1.0)
        intent: Detected intent (e.g., 'billing_question', 'bug_report')
        tokens_used: LLM tokens consumed (agent messages only)
        latency_ms: Response generation time in milliseconds
        tool_calls: JSON of tool calls made (agent messages only)
        channel_message_id: External message ID for deduplication

    Returns: dict with the new message row.
    """
    import json

    # Check for duplicate by channel_message_id
    if channel_message_id:
        existing = await _fetchrow(
            pool,
            "SELECT id FROM messages WHERE channel_message_id = $1",
            channel_message_id,
        )
        if existing:
            return await _fetchrow(
                pool,
                "SELECT * FROM messages WHERE id = $1",
                existing["id"],
            )

    tool_calls_json = json.dumps(tool_calls) if tool_calls else None

    row = await _fetchrow(
        pool,
        """
        INSERT INTO messages (
            conversation_id, channel, direction, role, content,
            sentiment_score, intent, tokens_used, latency_ms,
            tool_calls, channel_message_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11)
        RETURNING *
        """,
        conversation_id,
        channel,
        direction,
        role,
        content,
        sentiment_score,
        intent,
        tokens_used,
        latency_ms,
        tool_calls_json,
        channel_message_id,
    )

    # Update conversation timestamp
    await _execute(
        pool,
        "UPDATE conversations SET last_message_at = NOW() WHERE id = $1",
        conversation_id,
    )

    # Update customer's last_contact_at
    await _execute(
        pool,
        """
        UPDATE customers SET last_contact_at = NOW()
        WHERE id = (SELECT customer_id FROM conversations WHERE id = $1)
        """,
        conversation_id,
    )

    return row


async def get_conversation_history(
    pool: asyncpg.Pool,
    conversation_id: uuid.UUID,
    limit: int = 50,
    before: Optional[datetime] = None,
) -> list[dict]:
    """Retrieve message history for a conversation, ordered by time.

    Supports cursor-based pagination using the 'before' timestamp.

    Args:
        conversation_id: Conversation UUID
        limit: Max messages to return (default 50, max 200)
        before: Only return messages created before this timestamp

    Returns: List of message dicts, oldest first.
    """
    limit = max(1, min(200, limit))

    if before:
        return await _fetch(
            pool,
            """
            SELECT * FROM messages
            WHERE conversation_id = $1 AND created_at < $2
            ORDER BY created_at ASC
            LIMIT $3
            """,
            conversation_id,
            before,
            limit,
        )

    return await _fetch(
        pool,
        """
        SELECT * FROM messages
        WHERE conversation_id = $1
        ORDER BY created_at ASC
        LIMIT $2
        """,
        conversation_id,
        limit,
    )


# ── 5. Tickets ────────────────────────────────────────────────────────────


async def create_ticket(
    pool: asyncpg.Pool,
    conversation_id: uuid.UUID,
    customer_id: uuid.UUID,
    source_channel: str,
    subject: Optional[str] = None,
    category: Optional[str] = None,
    priority: str = "medium",
) -> dict:
    """Create a new support ticket linked to a conversation.

    Generates a human-readable ticket_ref in format TF-YYYYMMDD-XXXX.

    Returns: dict with the new ticket row.
    """
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    short_id = uuid.uuid4().hex[:4].upper()
    ticket_ref = f"TF-{date_str}-{short_id}"

    return await _fetchrow(
        pool,
        """
        INSERT INTO tickets (
            ticket_ref, conversation_id, customer_id,
            source_channel, subject, category, priority
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
        """,
        ticket_ref,
        conversation_id,
        customer_id,
        source_channel,
        subject,
        category,
        priority,
    )


async def escalate_ticket(
    pool: asyncpg.Pool,
    ticket_id: uuid.UUID,
    assigned_to: str,
    assigned_to_email: str,
    reason: str,
) -> dict:
    """Escalate a ticket to a human agent.

    Updates both the ticket status and the linked conversation's escalation fields.

    Returns: dict with the updated ticket row.
    """
    # Update ticket
    row = await _fetchrow(
        pool,
        """
        UPDATE tickets
        SET status = 'escalated',
            assigned_to = $2,
            assigned_to_email = $3,
            resolution_notes = $4
        WHERE id = $1
        RETURNING *
        """,
        ticket_id,
        assigned_to,
        assigned_to_email,
        reason,
    )

    # Also update the linked conversation
    if row:
        escalation_id = f"ESC-{uuid.uuid4().hex[:8].upper()}"
        await _execute(
            pool,
            """
            UPDATE conversations
            SET status = 'escalated',
                escalation_reason = $2,
                escalated_to = $3,
                escalated_to_email = $4,
                escalation_id = $5
            WHERE id = $1
            """,
            row["conversation_id"],
            reason,
            assigned_to,
            assigned_to_email,
            escalation_id,
        )

    return row


async def get_ticket_by_ref(
    pool: asyncpg.Pool,
    ticket_ref: str,
) -> Optional[dict]:
    """Look up a ticket by its human-readable reference (TF-YYYYMMDD-XXXX)."""
    return await _fetchrow(
        pool,
        "SELECT * FROM tickets WHERE ticket_ref = $1",
        ticket_ref,
    )


# ── 6. Knowledge Base Search ─────────────────────────────────────────────


async def search_knowledge_base(
    pool: asyncpg.Pool,
    query_embedding: list[float],
    top_k: int = 5,
    similarity_threshold: float = 0.3,
) -> list[dict]:
    """Semantic search over product documentation using cosine similarity.

    Uses pgvector's <=> operator (cosine distance). Lower distance = more similar.
    Cosine similarity = 1 - cosine distance.

    Args:
        query_embedding: 1536-dimension embedding vector from OpenAI text-embedding-3-small
        top_k: Maximum number of results (default 5, max 20)
        similarity_threshold: Minimum cosine similarity to include (0.0 to 1.0)

    Returns: List of dicts with title, content, category, similarity_score.
    """
    top_k = max(1, min(20, top_k))

    # pgvector <=> returns cosine distance (0 = identical, 2 = opposite)
    # Convert threshold to distance: distance = 1 - similarity
    max_distance = 1.0 - similarity_threshold

    # Cast the embedding list to a string pgvector can parse
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    return await _fetch(
        pool,
        """
        SELECT
            id,
            title,
            content,
            category,
            source,
            1 - (embedding <=> $1::vector) AS similarity_score
        FROM knowledge_base
        WHERE embedding IS NOT NULL
          AND (embedding <=> $1::vector) <= $3
        ORDER BY embedding <=> $1::vector
        LIMIT $2
        """,
        embedding_str,
        top_k,
        max_distance,
    )


# ── 7. Customer Full History ─────────────────────────────────────────────


async def get_customer_full_history(
    pool: asyncpg.Pool,
    customer_id: uuid.UUID,
) -> dict:
    """Retrieve complete interaction history for a customer.

    Aggregates conversations, messages, tickets, and sentiment data
    for the agent's context window.

    Returns: dict with customer profile, conversations, recent messages, and stats.
    """
    # Customer profile
    customer = await _fetchrow(
        pool,
        "SELECT * FROM customers WHERE id = $1",
        customer_id,
    )
    if not customer:
        return {"found": False, "customer_id": str(customer_id)}

    # All conversations (most recent first)
    conversations = await _fetch(
        pool,
        """
        SELECT * FROM conversations
        WHERE customer_id = $1
        ORDER BY last_message_at DESC
        """,
        customer_id,
    )

    # All tickets
    tickets = await _fetch(
        pool,
        """
        SELECT * FROM tickets
        WHERE customer_id = $1
        ORDER BY created_at DESC
        """,
        customer_id,
    )

    # Recent messages across all conversations (last 20)
    recent_messages = await _fetch(
        pool,
        """
        SELECT m.* FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        WHERE c.customer_id = $1
        ORDER BY m.created_at DESC
        LIMIT 20
        """,
        customer_id,
    )

    # Aggregate stats
    all_channels = set()
    all_topics = set()
    for conv in conversations:
        for ch in (conv.get("channels_used") or []):
            all_channels.add(ch)
        for t in (conv.get("topics") or []):
            all_topics.add(t)

    # Sentiment trend from recent messages
    sentiment_scores = [
        m["sentiment_score"]
        for m in recent_messages
        if m.get("sentiment_score") is not None
    ]
    avg_sentiment = (
        sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.0
    )

    return {
        "found": True,
        "customer": customer,
        "conversation_count": len(conversations),
        "conversations": conversations,
        "tickets": tickets,
        "recent_messages": list(reversed(recent_messages)),  # oldest first
        "all_channels": sorted(all_channels),
        "all_topics": sorted(all_topics),
        "average_sentiment": round(float(avg_sentiment), 2),
        "last_contact": customer.get("last_contact_at"),
    }


# ── 8. Agent Metrics ─────────────────────────────────────────────────────


async def record_metric(
    pool: asyncpg.Pool,
    metric_name: str,
    metric_value: float,
    channel: Optional[str] = None,
    dimensions: Optional[dict] = None,
) -> dict:
    """Record an observability metric for monitoring and alerting.

    Common metrics:
      - 'response_latency_ms': Time to generate agent response
      - 'escalation_rate': 1.0 if escalated, 0.0 if not
      - 'sentiment_score': Customer message sentiment
      - 'tokens_used': LLM tokens per interaction
      - 'knowledge_base_hit': 1.0 if docs found, 0.0 if not
      - 'confidence_score': Agent confidence in its response

    Returns: dict with the new metric row.
    """
    import json

    dimensions_json = json.dumps(dimensions) if dimensions else "{}"

    return await _fetchrow(
        pool,
        """
        INSERT INTO agent_metrics (metric_name, metric_value, channel, dimensions)
        VALUES ($1, $2, $3, $4::jsonb)
        RETURNING *
        """,
        metric_name,
        metric_value,
        channel,
        dimensions_json,
    )


async def get_metrics_summary(
    pool: asyncpg.Pool,
    metric_name: str,
    hours: int = 24,
    channel: Optional[str] = None,
) -> dict:
    """Get aggregated metrics for monitoring dashboards.

    Returns: dict with count, avg, min, max, p50, p95 over the time window.
    """
    channel_filter = "AND channel = $3" if channel else ""
    args = [metric_name, hours]
    if channel:
        args.append(channel)

    row = await _fetchrow(
        pool,
        f"""
        SELECT
            COUNT(*)::int AS count,
            ROUND(AVG(metric_value), 4) AS avg,
            ROUND(MIN(metric_value), 4) AS min,
            ROUND(MAX(metric_value), 4) AS max,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY metric_value)::numeric, 4) AS p50,
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY metric_value)::numeric, 4) AS p95
        FROM agent_metrics
        WHERE metric_name = $1
          AND recorded_at >= NOW() - INTERVAL '1 hour' * $2
          {channel_filter}
        """,
        *args,
    )

    return {
        "metric_name": metric_name,
        "window_hours": hours,
        "channel": channel,
        **(row or {}),
    }


# ── 9. Channel Config ────────────────────────────────────────────────────


async def get_channel_config(
    pool: asyncpg.Pool,
    channel: str,
) -> Optional[dict]:
    """Get configuration for a specific channel."""
    return await _fetchrow(
        pool,
        "SELECT * FROM channel_configs WHERE channel = $1 AND enabled = true",
        channel,
    )


async def get_all_channel_configs(pool: asyncpg.Pool) -> list[dict]:
    """Get all enabled channel configurations."""
    return await _fetch(
        pool,
        "SELECT * FROM channel_configs WHERE enabled = true ORDER BY channel",
    )
