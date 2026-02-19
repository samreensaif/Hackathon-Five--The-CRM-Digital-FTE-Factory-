"""
Kafka Client — Event Streaming for Multi-Channel Intake
========================================================
Producer and consumer for the Customer Success FTE event pipeline.

Architecture:
  Channel handlers → Kafka topics → Consumer → Agent → Response
  Escalations → Kafka escalation topic → Human notification service

Topics:
  fte.tickets.incoming       — Unified incoming tickets (all channels)
  fte.channels.email.inbound — Gmail-specific inbound
  fte.channels.whatsapp.inbound — WhatsApp-specific inbound
  fte.channels.webform.inbound  — Web form submissions
  fte.escalations            — Tickets escalated to human agents
  fte.metrics                — Performance metrics events
  fte.dlq                    — Dead letter queue (failed processing)

Setup:
  Environment variables:
    KAFKA_BOOTSTRAP_SERVERS — Comma-separated broker list (default: kafka:9092)
    KAFKA_CONSUMER_GROUP   — Consumer group ID (default: fte-agent-group)

Dependencies:
  aiokafka
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger("kafka")

# ── Configuration ────────────────────────────────────────────────────────

KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_CONSUMER_GROUP = os.environ.get("KAFKA_CONSUMER_GROUP", "fte-agent-group")

# Topic definitions — centralized so all modules reference the same names
TOPICS = {
    "tickets_incoming": "fte.tickets.incoming",
    "email_inbound": "fte.channels.email.inbound",
    "whatsapp_inbound": "fte.channels.whatsapp.inbound",
    "webform_inbound": "fte.channels.webform.inbound",
    "escalations": "fte.escalations",
    "metrics": "fte.metrics",
    "dlq": "fte.dlq",
}

# All inbound channel topics (for the unified consumer)
INBOUND_TOPICS = [
    TOPICS["email_inbound"],
    TOPICS["whatsapp_inbound"],
    TOPICS["webform_inbound"],
]


# ── Singleton Access ─────────────────────────────────────────────────────
# Used by channel handlers to publish without managing lifecycle.

_producer_instance: Optional[FTEKafkaProducer] = None


def get_producer() -> Optional[FTEKafkaProducer]:
    """Get the global Kafka producer instance (None if not started)."""
    return _producer_instance


async def init_producer() -> FTEKafkaProducer:
    """Initialize and start the global Kafka producer."""
    global _producer_instance
    if _producer_instance is None:
        producer = FTEKafkaProducer()
        await producer.start()
        _producer_instance = producer
    return _producer_instance


async def shutdown_producer() -> None:
    """Shut down the global Kafka producer gracefully."""
    global _producer_instance
    if _producer_instance:
        await _producer_instance.stop()
        _producer_instance = None


# ── Producer ─────────────────────────────────────────────────────────────


class FTEKafkaProducer:
    """Kafka producer for publishing events to the FTE pipeline.

    Serializes events as JSON with automatic timestamp injection.

    Usage:
        producer = FTEKafkaProducer()
        await producer.start()
        await producer.publish("fte.channels.email.inbound", {"channel": "email", ...})
        await producer.stop()
    """

    def __init__(self, bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS):
        self._bootstrap_servers = bootstrap_servers
        self._producer = None

    async def start(self) -> None:
        """Start the Kafka producer connection."""
        from aiokafka import AIOKafkaProducer

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            # Reliability settings
            acks="all",  # Wait for all replicas
            retry_backoff_ms=100,
        )
        await self._producer.start()
        logger.info(f"Kafka producer started: {self._bootstrap_servers}")

    async def stop(self) -> None:
        """Flush pending messages and close the producer."""
        if self._producer:
            await self._producer.stop()
            self._producer = None
            logger.info("Kafka producer stopped")

    async def publish(
        self,
        topic: str,
        event: dict,
        key: Optional[str] = None,
    ) -> None:
        """Publish an event to a Kafka topic.

        Automatically adds a timestamp and event_id if not present.

        Args:
            topic: Kafka topic name
            event: Event payload dict
            key: Optional partition key (e.g., customer_email for ordering)
        """
        if not self._producer:
            raise RuntimeError("Producer not started. Call start() first.")

        # Inject metadata
        if "timestamp" not in event:
            event["timestamp"] = datetime.now(timezone.utc).isoformat()
        if "event_id" not in event:
            import uuid
            event["event_id"] = str(uuid.uuid4())

        await self._producer.send_and_wait(topic, value=event, key=key)
        logger.debug(f"Published to {topic}: event_id={event.get('event_id')}")

    async def publish_ticket(self, normalized_message: dict) -> None:
        """Convenience: publish a normalized channel message as a ticket event.

        Uses the customer_email as the partition key so all messages from
        the same customer go to the same partition (ordering guarantee).
        """
        key = normalized_message.get("customer_email") or normalized_message.get(
            "customer_phone", ""
        )
        await self.publish(TOPICS["tickets_incoming"], normalized_message, key=key)

    async def publish_escalation(self, escalation: dict) -> None:
        """Convenience: publish an escalation event."""
        key = escalation.get("ticket_id", "")
        await self.publish(TOPICS["escalations"], escalation, key=key)

    async def publish_metric(self, metric: dict) -> None:
        """Convenience: publish a metrics event."""
        await self.publish(TOPICS["metrics"], metric)

    async def publish_to_dlq(self, failed_event: dict, error: str) -> None:
        """Publish a failed event to the dead letter queue.

        Wraps the original event with error context for debugging.
        """
        dlq_event = {
            "original_event": failed_event,
            "error": error,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.publish(TOPICS["dlq"], dlq_event)


# ── Consumer ─────────────────────────────────────────────────────────────


class FTEKafkaConsumer:
    """Kafka consumer for processing incoming ticket events.

    Subscribes to one or more topics and calls a handler function
    for each message received.

    Usage:
        consumer = FTEKafkaConsumer(
            topics=["fte.channels.email.inbound", "fte.channels.whatsapp.inbound"],
            group_id="fte-agent-group",
        )
        await consumer.start()
        await consumer.consume(handler=process_ticket)
        await consumer.stop()
    """

    def __init__(
        self,
        topics: list[str],
        group_id: str = KAFKA_CONSUMER_GROUP,
        bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS,
    ):
        self._topics = topics
        self._group_id = group_id
        self._bootstrap_servers = bootstrap_servers
        self._consumer = None
        self._running = False

    async def start(self) -> None:
        """Start the Kafka consumer and subscribe to topics."""
        from aiokafka import AIOKafkaConsumer

        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            # Consumer settings
            auto_offset_reset="earliest",  # Process from beginning on first run
            enable_auto_commit=True,
            auto_commit_interval_ms=5000,
            max_poll_records=10,  # Process in small batches
        )
        await self._consumer.start()
        self._running = True
        logger.info(
            f"Kafka consumer started: topics={self._topics}, group={self._group_id}"
        )

    async def stop(self) -> None:
        """Stop consuming and close the connection."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
            logger.info("Kafka consumer stopped")

    async def consume(
        self,
        handler: Callable[[str, dict], Coroutine[Any, Any, None]],
    ) -> None:
        """Consume messages and call handler for each.

        The handler receives (topic: str, event: dict) and should process
        the event. If the handler raises an exception, the event is sent
        to the dead letter queue.

        Args:
            handler: Async function(topic, event) to process each message.
        """
        if not self._consumer:
            raise RuntimeError("Consumer not started. Call start() first.")

        logger.info("Starting message consumption loop")

        async for msg in self._consumer:
            if not self._running:
                break

            topic = msg.topic
            event = msg.value

            try:
                await handler(topic, event)
                logger.debug(
                    f"Processed message from {topic}: event_id={event.get('event_id', '?')}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to process message from {topic}: {e}",
                    exc_info=True,
                )
                # Send to dead letter queue
                try:
                    producer = get_producer()
                    if producer:
                        await producer.publish_to_dlq(event, str(e))
                except Exception as dlq_error:
                    logger.error(f"Failed to publish to DLQ: {dlq_error}")


# ── Unified Ticket Handler ──────────────────────────────────────────────
# Default handler that routes inbound messages to the agent.


async def default_ticket_handler(topic: str, event: dict) -> None:
    """Default handler for incoming ticket events.

    Routes normalized messages from any channel to the agent for processing.
    Called by FTEKafkaConsumer.consume().

    Args:
        topic: Source Kafka topic
        event: Normalized message dict from a channel handler
    """
    from agent.customer_success_agent import run_agent
    from database.queries import get_or_create_customer
    from agent.tools import _get_pool

    channel = event.get("channel", "web_form")
    customer_email = event.get("customer_email", "")
    customer_phone = event.get("customer_phone", "")
    customer_name = event.get("customer_name", "Customer")
    customer_plan = event.get("customer_plan", "free")
    subject = event.get("subject", "Support Request")
    content = event.get("content", "")

    if not content:
        logger.warning(f"Skipping empty message from {topic}")
        return

    logger.info(
        f"Processing ticket from {topic}: channel={channel}, "
        f"customer={customer_email or customer_phone}"
    )

    # Resolve customer
    customer_id = None
    try:
        pool = _get_pool()
        customer = await get_or_create_customer(
            pool,
            email=customer_email or None,
            phone=customer_phone or None,
            name=customer_name,
            plan=customer_plan,
        )
        customer_id = str(customer["id"])
    except Exception as e:
        logger.warning(f"Customer resolution failed: {e}")

    # Run the agent
    result = await run_agent(
        customer_message=content,
        customer_email=customer_email or customer_phone,
        channel=channel,
        customer_name=customer_name,
        customer_plan=customer_plan,
        customer_id=customer_id,
        ticket_subject=subject,
    )

    # If escalated, publish to escalation topic
    if result.get("escalated"):
        try:
            producer = get_producer()
            if producer:
                await producer.publish_escalation({
                    "ticket_id": result.get("ticket_id"),
                    "channel": channel,
                    "customer_email": customer_email,
                    "customer_name": customer_name,
                    "escalation_details": result.get("escalation_details"),
                    "sentiment_score": result.get("sentiment_score"),
                })
        except Exception as e:
            logger.error(f"Failed to publish escalation: {e}")

    # Publish metrics
    try:
        producer = get_producer()
        if producer:
            await producer.publish_metric({
                "metric_name": "ticket_processed",
                "channel": channel,
                "latency_ms": result.get("latency_ms", 0),
                "escalated": result.get("escalated", False),
                "sentiment_score": result.get("sentiment_score", 0.0),
                "tools_used": result.get("tools_used", []),
            })
    except Exception:
        pass  # Metrics are best-effort

    logger.info(
        f"Ticket processed: ticket_id={result.get('ticket_id')}, "
        f"escalated={result.get('escalated')}, "
        f"latency={result.get('latency_ms')}ms"
    )
