"""
Unified Message Processor — Worker Service
=============================================
Consumes incoming messages from all channels via Kafka, processes them
through the AI agent pipeline, and dispatches responses.

Pipeline (per message):
  1. resolve_customer() — get or create customer in DB
  2. get_or_create_conversation() — reuse active or create new
  3. Store inbound message in DB
  4. run_agent() — call the AI agent
  5. send_response() — deliver via Gmail / Twilio / store for web
  6. Update conversation sentiment in DB
  7. Publish metrics to Kafka

Run:
  python -m workers.message_processor

Dependencies:
  - PostgreSQL (asyncpg)
  - Kafka (aiokafka)
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
from agent.tools import set_db_pool, _get_pool
from database.queries import (
    add_message,
    create_conversation,
    get_active_conversation,
    get_conversation_history,
    get_or_create_customer,
    update_conversation_sentiment,
)
from kafka_client import (
    TOPICS,
    FTEKafkaConsumer,
    get_producer,
    init_producer,
    shutdown_producer,
)

logger = logging.getLogger("worker.processor")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

# ── Configuration ────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://{user}:{password}@{host}:{port}/{db}".format(
        user=os.environ.get("POSTGRES_USER", "fte"),
        password=os.environ.get("POSTGRES_PASSWORD", "fte_secret"),
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        db=os.environ.get("POSTGRES_DB", "fte_production"),
    ),
)


# ── Unified Message Processor ───────────────────────────────────────────


class UnifiedMessageProcessor:
    """Processes messages from all channels through the agent pipeline.

    Lifecycle:
      processor = UnifiedMessageProcessor()
      await processor.start()    # Connect DB + Kafka
      await processor.run()      # Blocking consume loop
      await processor.stop()     # Graceful shutdown
    """

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._consumer: Optional[FTEKafkaConsumer] = None
        self._running = False

    async def start(self) -> None:
        """Connect to PostgreSQL and Kafka."""
        # 1. Database pool
        self._pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        set_db_pool(self._pool)
        logger.info("PostgreSQL pool connected")

        # 2. Kafka producer (for publishing metrics + escalations)
        await init_producer()
        logger.info("Kafka producer started")

        # 3. Kafka consumer (unified incoming topic)
        self._consumer = FTEKafkaConsumer(
            topics=[TOPICS["tickets_incoming"]],
            group_id="fte-processor-group",
        )
        await self._consumer.start()
        logger.info("Kafka consumer started on fte.tickets.incoming")

        self._running = True

    async def stop(self) -> None:
        """Graceful shutdown of all connections."""
        self._running = False

        if self._consumer:
            await self._consumer.stop()
            logger.info("Kafka consumer stopped")

        await shutdown_producer()
        logger.info("Kafka producer stopped")

        if self._pool:
            await self._pool.close()
            logger.info("PostgreSQL pool closed")

    async def run(self) -> None:
        """Start the consume loop — blocks until stopped."""
        if not self._consumer:
            raise RuntimeError("Processor not started. Call start() first.")

        logger.info("Message processor running — waiting for messages...")
        await self._consumer.consume(handler=self._handle_message)

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

            # Step 7: Publish metrics to Kafka
            await self._publish_metrics(
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
                # Try to extract sentiment if available
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

    async def _publish_metrics(
        self,
        channel: str,
        latency_ms: int,
        escalated: bool,
        sentiment_score: float,
        tools_used: list,
    ) -> None:
        """Step 7: Publish processing metrics to Kafka."""
        try:
            producer = get_producer()
            if producer:
                await producer.publish_metric({
                    "metric_name": "ticket_processed",
                    "channel": channel,
                    "latency_ms": latency_ms,
                    "escalated": escalated,
                    "sentiment_score": sentiment_score,
                    "tools_used": tools_used,
                })
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
        """Handle a processing failure — send apology and publish to DLQ."""
        # Send apology to customer
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

        # Publish to DLQ
        try:
            producer = get_producer()
            if producer:
                await producer.publish_to_dlq(event, str(error))
        except Exception as dlq_err:
            logger.error(f"Failed to publish to DLQ: {dlq_err}")


# ── Entrypoint ──────────────────────────────────────────────────────────


async def main():
    """Run the message processor worker."""
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
            # Clean up any partial state (e.g., pool opened but Kafka failed)
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
        # Run consumer in background, wait for shutdown signal
        consumer_task = asyncio.create_task(processor.run())

        # Wait for either the consumer to finish or a shutdown signal
        done, pending = await asyncio.wait(
            [consumer_task, asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        logger.error(f"Processor error: {e}", exc_info=True)
    finally:
        await processor.stop()
        logger.info("Message processor shut down")


if __name__ == "__main__":
    asyncio.run(main())
