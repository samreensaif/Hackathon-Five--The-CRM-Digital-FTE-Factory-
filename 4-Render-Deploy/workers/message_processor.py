"""
Unified Message Processor — Worker Service (Render.com Edition)
================================================================
Polls the PostgreSQL message queue for incoming messages from all channels,
processes them through the AI agent pipeline, and dispatches responses.

Differences from production/:
  - Kafka consumer replaced with a 2-second polling loop using consume_messages()
  - No aiokafka imports or Kafka producer/consumer initialization
  - Metrics are stored directly to DB instead of published to Kafka

Pipeline (per message):
  1. resolve_customer()          — get or create customer in DB
  2. get_or_create_conversation() — reuse active or create new
  3. Store inbound message in DB
  4. run_agent()                 — call the AI agent
  5. send_response()             — deliver via Gmail / Twilio / store for web
  6. Update conversation sentiment in DB
  7. Record metrics in DB

Run:
  python -m workers.message_processor

Dependencies:
  - PostgreSQL (asyncpg)
  - Agent pipeline (agent.customer_success_agent)
  - Channel handlers (channels.*)
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from typing import Optional

import asyncpg

from agent.customer_success_agent import run_agent
from agent.tools import set_db_pool
from database.queries import (
    add_message,
    create_conversation,
    get_active_conversation,
    get_conversation_history,
    get_or_create_customer,
    record_metric,
    update_conversation_sentiment,
)
from database.queue import consume_messages

logger = logging.getLogger("worker.processor")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

# ── Configuration ────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://localhost/fte_production",  # local dev fallback
)

POLL_INTERVAL_SECONDS = float(os.environ.get("POLL_INTERVAL_SECONDS", "2"))
TOPIC_TICKETS_INCOMING = "fte.tickets.incoming"


# ── Unified Message Processor ───────────────────────────────────────────


class UnifiedMessageProcessor:
    """Processes messages from all channels through the agent pipeline.

    Uses a polling loop instead of Kafka for cloud-friendly deployment.

    Lifecycle:
      processor = UnifiedMessageProcessor()
      await processor.start()    # Connect DB
      await processor.run()      # Blocking poll loop
      await processor.stop()     # Graceful shutdown
    """

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._running = False

    async def start(self) -> None:
        """Connect to PostgreSQL."""
        self._pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        set_db_pool(self._pool)
        logger.info("PostgreSQL pool connected")
        self._running = True

    async def stop(self) -> None:
        """Graceful shutdown."""
        self._running = False

        if self._pool:
            await self._pool.close()
            logger.info("PostgreSQL pool closed")

    async def run(self) -> None:
        """Polling loop — checks the queue every POLL_INTERVAL_SECONDS.

        Runs until stop() is called. Each poll batch processes up to 10
        messages before sleeping, so bursts drain quickly.
        """
        logger.info(
            f"Message processor running — polling every {POLL_INTERVAL_SECONDS}s "
            f"on topic={TOPIC_TICKETS_INCOMING!r}"
        )

        while self._running:
            try:
                messages = await consume_messages(
                    self._pool,
                    topic=TOPIC_TICKETS_INCOMING,
                    batch_size=10,
                )

                if messages:
                    logger.info(f"Poll: dequeued {len(messages)} message(s)")
                    for queued in messages:
                        if not self._running:
                            break
                        event = queued["payload"]
                        await self._handle_message(TOPIC_TICKETS_INCOMING, event)
                else:
                    # Queue empty — sleep before next poll
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Poll loop error: {e}", exc_info=True)
                await asyncio.sleep(POLL_INTERVAL_SECONDS)

    # ── Message Handler ──────────────────────────────────────────────

    async def _handle_message(self, topic: str, event: dict) -> None:
        """Process a single incoming message through the full pipeline."""
        start_time = time.time()
        channel = event.get("channel", "web_form")
        customer_email = event.get("customer_email", "")
        customer_phone = event.get("customer_phone", "")
        customer_name = event.get("customer_name", "Customer")
        customer_plan = event.get("customer_plan", "free")
        subject = event.get("subject", "Support Request")
        content = event.get("content", "")
        channel_message_id = event.get("channel_message_id")

        if not content:
            logger.warning(f"Skipping empty message from {topic}")
            return

        logger.info(
            f"Processing: channel={channel}, "
            f"customer={customer_email or customer_phone}, "
            f"subject={subject[:50]}"
        )

        pool = self._pool
        customer = None
        conversation = None

        try:
            # Step 1: Resolve customer
            customer = await self._resolve_customer(
                pool, customer_email, customer_phone, customer_name, customer_plan
            )
            customer_id = customer["id"]

            # Step 2: Get or create conversation
            conversation = await self._get_or_create_conversation(
                pool, customer_id, channel
            )
            conversation_id = conversation["id"]

            # Step 3: Store inbound message
            await add_message(
                pool,
                conversation_id=conversation_id,
                channel=channel,
                direction="inbound",
                role="customer",
                content=content,
                channel_message_id=channel_message_id,
            )

            # Build conversation history for context
            history = await get_conversation_history(pool, conversation_id, limit=10)
            conversation_history = [
                {"role": m.get("role", "user"), "content": m.get("content", "")}
                for m in history
            ]

            # Step 4: Run the agent
            result = await run_agent(
                customer_message=content,
                customer_email=customer_email or customer_phone,
                channel=channel,
                customer_name=customer_name,
                customer_plan=customer_plan,
                customer_id=str(customer_id),
                ticket_subject=subject,
                conversation_history=conversation_history,
            )

            response_text = result.get("response_text", "")

            # Step 5: Send response via the appropriate channel
            delivery = await self._send_response(
                channel=channel,
                response_text=response_text,
                customer_email=customer_email,
                customer_phone=customer_phone,
                subject=subject,
                event_metadata=event.get("metadata", {}),
            )

            # Store outbound message
            await add_message(
                pool,
                conversation_id=conversation_id,
                channel=channel,
                direction="outbound",
                role="agent",
                content=response_text,
                sentiment_score=result.get("sentiment_score"),
                tokens_used=result.get("tokens_used"),
                latency_ms=result.get("latency_ms"),
                tool_calls={"tools_used": result.get("tools_used", [])},
                channel_message_id=delivery.get("channel_message_id"),
            )

            # Step 6: Update conversation sentiment
            sentiment = result.get("sentiment_score", 0.0)
            trend = self._compute_sentiment_trend(conversation_history, sentiment)
            await update_conversation_sentiment(
                pool, conversation_id, sentiment, trend
            )

            # Step 7: Record metrics directly to DB
            await self._record_metrics(
                pool=pool,
                channel=channel,
                latency_ms=result.get("latency_ms", 0),
                escalated=result.get("escalated", False),
                sentiment_score=sentiment,
                tools_used=result.get("tools_used", []),
            )

            elapsed = int((time.time() - start_time) * 1000)
            logger.info(
                f"Message processed: ticket={result.get('ticket_id')}, "
                f"escalated={result.get('escalated')}, "
                f"delivery={delivery.get('delivery_status')}, "
                f"total_ms={elapsed}"
            )

        except Exception as e:
            elapsed = int((time.time() - start_time) * 1000)
            logger.error(f"Processing failed after {elapsed}ms: {e}", exc_info=True)
            await self._handle_processing_error(
                event=event,
                error=e,
                channel=channel,
                customer_email=customer_email,
                customer_phone=customer_phone,
                conversation=conversation,
            )

    # ── Pipeline Steps ───────────────────────────────────────────────

    async def _resolve_customer(
        self,
        pool: asyncpg.Pool,
        email: str,
        phone: str,
        name: str,
        plan: str,
    ) -> dict:
        """Step 1: Resolve or create customer record."""
        return await get_or_create_customer(
            pool,
            email=email or None,
            phone=phone or None,
            name=name,
            plan=plan,
        )

    async def _get_or_create_conversation(
        self,
        pool: asyncpg.Pool,
        customer_id,
        channel: str,
    ) -> dict:
        """Step 2: Reuse active conversation or create a new one."""
        conversation = await get_active_conversation(pool, customer_id, channel)
        if conversation:
            return conversation
        return await create_conversation(pool, customer_id, channel)

    async def _send_response(
        self,
        channel: str,
        response_text: str,
        customer_email: str,
        customer_phone: str,
        subject: str,
        event_metadata: dict,
    ) -> dict:
        """Step 5: Send the agent response via the appropriate channel."""
        if not response_text:
            logger.warning(f"Empty response_text for channel={channel}, skipping send")
            return {"delivery_status": "skipped", "channel_message_id": None}

        if channel == "email":
            from channels.gmail_handler import send_reply

            return await send_reply(
                to_email=customer_email,
                subject=subject,
                body=response_text,
                thread_id=event_metadata.get("gmail_thread_id"),
                in_reply_to=event_metadata.get("message_id_header"),
            )

        elif channel == "whatsapp":
            from channels.whatsapp_handler import send_message

            logger.info(
                f"Sending WhatsApp reply to: {customer_phone}, "
                f"response_length={len(response_text)}"
            )
            logger.info(f"Reply content preview: {response_text[:100]}")

            if not customer_phone:
                logger.error("Cannot send WhatsApp reply: customer_phone is empty")
                return {"delivery_status": "failed", "channel_message_id": None}

            delivery = await send_message(
                to_phone=customer_phone,
                body=response_text,
            )

            if delivery.get("delivery_status") == "failed":
                logger.error(
                    f"WhatsApp send failed: {delivery.get('error', 'unknown error')}"
                )
            else:
                logger.info(
                    f"WhatsApp send success: sid={delivery.get('channel_message_id')}"
                )

            return delivery

        elif channel == "web_form":
            # Web form responses are stored in DB and retrieved via GET endpoint
            return {"delivery_status": "stored", "channel_message_id": None}

        else:
            logger.warning(f"Unknown channel '{channel}', storing response in DB only")
            return {"delivery_status": "stored", "channel_message_id": None}

    def _compute_sentiment_trend(
        self, history: list[dict], current_score: float
    ) -> str:
        """Compute sentiment trend from recent conversation history."""
        scores = []
        for msg in history[-5:]:
            if msg.get("role") == "customer":
                s = msg.get("sentiment_score")
                if s is not None:
                    scores.append(float(s))

        if len(scores) < 2:
            return "stable"

        scores.append(current_score)
        recent = scores[-3:]
        avg_change = (recent[-1] - recent[0]) / len(recent)

        if avg_change > 0.15:
            return "improving"
        elif avg_change < -0.15:
            return "declining"
        return "stable"

    async def _record_metrics(
        self,
        pool: asyncpg.Pool,
        channel: str,
        latency_ms: int,
        escalated: bool,
        sentiment_score: float,
        tools_used: list,
    ) -> None:
        """Step 7: Record processing metrics directly to the database."""
        try:
            await record_metric(
                pool,
                metric_name="ticket_processed",
                metric_value=1,
                channel=channel,
                dimensions={
                    "latency_ms": latency_ms,
                    "escalated": escalated,
                    "sentiment_score": sentiment_score,
                    "tools_used": tools_used,
                },
            )
            await record_metric(
                pool,
                metric_name="response_latency_ms",
                metric_value=latency_ms,
                channel=channel,
            )
            await record_metric(
                pool,
                metric_name="escalation_rate",
                metric_value=1.0 if escalated else 0.0,
                channel=channel,
            )
            if sentiment_score is not None:
                await record_metric(
                    pool,
                    metric_name="sentiment_score",
                    metric_value=sentiment_score,
                    channel=channel,
                )
        except Exception:
            pass  # Metrics are best-effort

    async def _handle_processing_error(
        self,
        event: dict,
        error: Exception,
        channel: str,
        customer_email: str,
        customer_phone: str,
        conversation: Optional[dict],
    ) -> None:
        """Handle a processing failure — send apology and log the error."""
        apology = (
            "I apologize for the inconvenience. I'm experiencing a temporary "
            "issue processing your request. Our team has been notified and "
            "will follow up shortly. You can also reach us directly at "
            "support@techcorp.io."
        )

        try:
            await self._send_response(
                channel=channel,
                response_text=apology,
                customer_email=customer_email,
                customer_phone=customer_phone,
                subject="Support Request",
                event_metadata=event.get("metadata", {}),
            )
        except Exception as send_err:
            logger.error(f"Failed to send apology: {send_err}")

        # Store apology in conversation if we have one
        if conversation:
            try:
                pool = self._pool
                await add_message(
                    pool,
                    conversation_id=conversation["id"],
                    channel=channel,
                    direction="outbound",
                    role="system",
                    content=f"[Auto-apology sent due to processing error: {error}]",
                )
            except Exception:
                pass


# ── Entrypoint ──────────────────────────────────────────────────────────


async def main():
    """Run the message processor worker — stays alive until SIGTERM/SIGINT."""
    processor = UnifiedMessageProcessor()

    # Handle graceful shutdown signals
    loop = asyncio.get_event_loop()
    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    # Retry startup with exponential backoff
    max_retries = 10
    base_delay = 5.0
    for attempt in range(1, max_retries + 1):
        try:
            await processor.start()
            logger.info("Message processor started successfully")
            break
        except Exception as e:
            try:
                await processor.stop()
            except Exception:
                pass
            if attempt == max_retries:
                logger.error(f"Failed to start after {max_retries} attempts: {e}")
                return
            delay = min(base_delay * (2 ** (attempt - 1)), 60)
            logger.warning(
                f"Startup attempt {attempt}/{max_retries} failed: {e} — "
                f"retrying in {delay:.0f}s"
            )
            await asyncio.sleep(delay)

    try:
        # Start the poll loop as a background task
        consumer_task = asyncio.create_task(processor.run())

        # Keep main() alive until a shutdown signal arrives.
        # Also watch for the consumer task dying unexpectedly and restart it
        # so a transient error never causes the whole worker to exit.
        while not shutdown_event.is_set():
            if consumer_task.done():
                exc = consumer_task.exception() if not consumer_task.cancelled() else None
                if exc:
                    logger.error(f"Consumer task died unexpectedly: {exc} — restarting")
                else:
                    logger.warning("Consumer task exited without error — restarting")
                consumer_task = asyncio.create_task(processor.run())
            await asyncio.sleep(1)

        # Shutdown requested — stop the poll loop and wait for it to finish
        logger.info("Stopping consumer task ...")
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

    except Exception as e:
        logger.error(f"Processor error: {e}", exc_info=True)
    finally:
        await processor.stop()
        logger.info("Message processor shut down")


if __name__ == "__main__":
    asyncio.run(main())
