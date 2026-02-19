"""
PostgreSQL-Based Message Queue
================================
Replaces Kafka for cloud deployment on Render.com.

The message_queue table acts as a simple durable queue:
  - publish_message()   — inserts a new message (producer side)
  - consume_messages()  — claims and returns unprocessed messages (consumer side)

Messages are marked processed=true rather than deleted, providing an audit
trail and making it safe to re-run consume_messages() concurrently.

Schema (added to database/schema.sql):
  CREATE TABLE message_queue (
      id          BIGSERIAL PRIMARY KEY,
      topic       VARCHAR(100) NOT NULL,
      payload     JSONB        NOT NULL,
      processed   BOOLEAN      NOT NULL DEFAULT false,
      created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
      processed_at TIMESTAMPTZ
  );
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg

logger = logging.getLogger("database.queue")

# ── Publish ──────────────────────────────────────────────────────────────────


async def publish_message(
    pool: asyncpg.Pool,
    topic: str,
    payload: dict[str, Any],
) -> int:
    """Insert a message into the queue.

    Args:
        pool:    asyncpg connection pool.
        topic:   Logical topic name (mirrors Kafka topic names for clarity).
                 e.g. "fte.tickets.incoming", "fte.metrics"
        payload: The message body as a dict (stored as JSONB).

    Returns:
        The auto-generated message ID.
    """
    row = await pool.fetchrow(
        """
        INSERT INTO message_queue (topic, payload)
        VALUES ($1, $2::jsonb)
        RETURNING id
        """,
        topic,
        json.dumps(payload),
    )
    msg_id = row["id"]
    logger.debug(f"Published message id={msg_id} to topic={topic!r}")
    return msg_id


# ── Consume ──────────────────────────────────────────────────────────────────


async def consume_messages(
    pool: asyncpg.Pool,
    topic: str,
    batch_size: int = 10,
) -> list[dict[str, Any]]:
    """Atomically claim and return unprocessed messages from the queue.

    Uses SELECT ... FOR UPDATE SKIP LOCKED so multiple worker processes
    can poll safely without double-processing the same message.

    Args:
        pool:       asyncpg connection pool.
        topic:      Topic to consume from.
        batch_size: Maximum number of messages to return per call.

    Returns:
        List of message dicts with keys: id, topic, payload, created_at.
        Returns [] when the queue is empty.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                SELECT id, topic, payload, created_at
                FROM message_queue
                WHERE topic = $1
                  AND processed = false
                ORDER BY id ASC
                LIMIT $2
                FOR UPDATE SKIP LOCKED
                """,
                topic,
                batch_size,
            )

            if not rows:
                return []

            ids = [r["id"] for r in rows]

            await conn.execute(
                """
                UPDATE message_queue
                SET processed    = true,
                    processed_at = NOW()
                WHERE id = ANY($1::bigint[])
                """,
                ids,
            )

            messages = []
            for row in rows:
                payload = row["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                messages.append({
                    "id": row["id"],
                    "topic": row["topic"],
                    "payload": payload,
                    "created_at": row["created_at"],
                })

            logger.debug(
                f"Consumed {len(messages)} message(s) from topic={topic!r}"
            )
            return messages


# ── Purge (maintenance) ──────────────────────────────────────────────────────


async def purge_processed_messages(
    pool: asyncpg.Pool,
    older_than_hours: int = 24,
) -> int:
    """Delete processed messages older than the given threshold.

    Call this periodically (e.g., daily) to keep the table small.

    Args:
        pool:              asyncpg connection pool.
        older_than_hours:  Delete messages processed more than N hours ago.

    Returns:
        Number of rows deleted.
    """
    result = await pool.execute(
        """
        DELETE FROM message_queue
        WHERE processed = true
          AND processed_at < NOW() - ($1 || ' hours')::INTERVAL
        """,
        str(older_than_hours),
    )
    deleted = int(result.split()[-1])
    logger.info(f"Purged {deleted} processed messages older than {older_than_hours}h")
    return deleted
