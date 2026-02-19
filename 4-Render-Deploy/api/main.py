"""
Customer Success Digital FTE — FastAPI Application (Render.com Edition)
========================================================================
Main application entry point with lifecycle management, webhook endpoints,
and monitoring routes.

Differences from production/:
  - Kafka replaced with PostgreSQL-based message queue (database.queue)
  - No Kafka producer/consumer imports or initialization
  - publish_message() used instead of producer.publish()

Startup:
  1. Connect to PostgreSQL (asyncpg pool)
  2. Register channel routers

Shutdown:
  1. Close PostgreSQL pool

Run:
  uvicorn api.main:app --host 0.0.0.0 --port 8000

Environment:
  DATABASE_URL — PostgreSQL connection string
  CORS_ORIGINS — Comma-separated allowed origins
"""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import asyncpg
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent.tools import set_db_pool
from channels.web_form_handler import router as web_form_router
from database.queue import publish_message

logger = logging.getLogger("api")
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

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")

# Logical topic names (match production Kafka topics for easy migration)
TOPIC_TICKETS_INCOMING = "fte.tickets.incoming"
TOPIC_EMAIL_INBOUND = "fte.channels.email.inbound"
TOPIC_WHATSAPP_INBOUND = "fte.channels.whatsapp.inbound"


# ── Lifespan ────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and shutdown."""
    # ── Startup ──────────────────────────────────────────────────────
    logger.info("Starting Customer Success Digital FTE API (Render edition)...")

    # Connect to PostgreSQL
    try:
        pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        app.state.db_pool = pool
        set_db_pool(pool)
        logger.info("PostgreSQL pool connected")
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        raise

    logger.info("API startup complete")
    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("Shutting down API...")

    try:
        pool = app.state.db_pool
        if pool:
            await pool.close()
            logger.info("PostgreSQL pool closed")
    except Exception as e:
        logger.warning(f"Error closing PostgreSQL pool: {e}")


# ── App ──────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Customer Success Digital FTE",
    description="24/7 AI customer support agent for TaskFlow by TechCorp",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include channel routers
app.include_router(web_form_router)


# ── Health Checks ────────────────────────────────────────────────────────


@app.get("/health", tags=["health"])
async def health_check():
    """Render.com health check — lightweight probe."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/health/detailed", tags=["health"])
async def health_check_detailed(request: Request):
    """Detailed health check — validates DB and channel status."""
    checks = {}

    # Database check
    try:
        pool = request.app.state.db_pool
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["database"] = {"status": "healthy"}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}

    # Queue depth check
    try:
        pool = request.app.state.db_pool
        async with pool.acquire() as conn:
            pending = await conn.fetchval(
                "SELECT COUNT(*) FROM message_queue WHERE processed = false"
            )
        checks["queue"] = {"status": "healthy", "pending_messages": pending}
    except Exception as e:
        checks["queue"] = {"status": "unhealthy", "error": str(e)}

    # Channel status
    channels = {}
    try:
        from database.queries import get_all_channel_configs

        pool = request.app.state.db_pool
        configs = await get_all_channel_configs(pool)
        for cfg in configs:
            channels[cfg["channel"]] = {"enabled": cfg.get("enabled", False)}
    except Exception:
        channels = {"error": "Could not load channel configs"}
    checks["channels"] = channels

    overall = "healthy" if checks["database"].get("status") == "healthy" else "degraded"

    return {"status": overall, "checks": checks}


# ── Gmail Webhook ────────────────────────────────────────────────────────


@app.post("/webhooks/gmail", tags=["webhooks"])
async def gmail_webhook(request: Request):
    """Receive Gmail Pub/Sub push notifications.

    Google Cloud Pub/Sub sends POST requests when new emails arrive.
    We decode the notification, fetch new messages, and publish to the
    PostgreSQL queue.
    """
    try:
        body = await request.json()
        message = body.get("message", {})
        data = message.get("data", "")

        if not data:
            return JSONResponse({"status": "no_data"}, status_code=200)

        # Decode base64-encoded Pub/Sub message
        decoded = base64.b64decode(data).decode("utf-8")
        pubsub_message = json.loads(decoded)

        logger.info(f"Gmail Pub/Sub notification: {pubsub_message.get('emailAddress')}")

        # Process notification to get normalized messages
        from channels.gmail_handler import process_notification

        messages = await process_notification(pubsub_message)

        # Publish each new message to the PostgreSQL queue
        pool = request.app.state.db_pool
        published = 0
        for msg in messages:
            try:
                await publish_message(pool, TOPIC_EMAIL_INBOUND, msg)
                await publish_message(pool, TOPIC_TICKETS_INCOMING, msg)
                published += 1
            except Exception as e:
                logger.error(f"Failed to enqueue email message: {e}")

        return JSONResponse({
            "status": "ok",
            "messages_processed": len(messages),
            "messages_published": published,
        })

    except Exception as e:
        logger.error(f"Gmail webhook error: {e}", exc_info=True)
        # Return 200 to prevent Pub/Sub retries on application errors
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=200)


# ── WhatsApp Webhooks ────────────────────────────────────────────────────


@app.post("/webhooks/whatsapp", tags=["webhooks"])
async def whatsapp_webhook(request: Request):
    """Receive incoming WhatsApp messages via Twilio webhook.

    Validates the Twilio signature, processes the message, and publishes
    to the PostgreSQL queue. Returns TwiML response.
    """
    try:
        form_data = dict(await request.form())
        logger.info(f"WhatsApp webhook received: From={form_data.get('From')}, Body={str(form_data.get('Body', ''))[:80]}")

        # Validate Twilio signature (skip in development)
        from channels.whatsapp_handler import (
            TWILIO_WEBHOOK_URL,
            process_webhook,
            validate_webhook,
        )

        if os.getenv("ENVIRONMENT", "development") == "production":
            signature = request.headers.get("X-Twilio-Signature", "")
            webhook_url = TWILIO_WEBHOOK_URL or str(request.url)

            if not validate_webhook(signature, webhook_url, form_data):
                logger.warning("Invalid Twilio webhook signature")
                raise HTTPException(status_code=403, detail="Invalid signature")
        else:
            logger.debug("Skipping Twilio signature validation (ENVIRONMENT != production)")

        # Process the incoming message
        normalized = await process_webhook(form_data)

        if not normalized:
            logger.warning("WhatsApp webhook: process_webhook returned None, skipping")
            twiml = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
            return Response(content=twiml, media_type="application/xml")

        logger.info(
            f"WhatsApp message normalized: phone={normalized.get('customer_phone')}, "
            f"content_length={len(normalized.get('content', ''))}"
        )

        # Publish to PostgreSQL queue
        pool = request.app.state.db_pool
        try:
            await publish_message(pool, TOPIC_WHATSAPP_INBOUND, normalized)
            await publish_message(pool, TOPIC_TICKETS_INCOMING, normalized)
            logger.info("WhatsApp message enqueued successfully")
        except Exception as e:
            logger.error(f"Failed to enqueue WhatsApp message: {e}", exc_info=True)

        # Return TwiML response (empty — agent responds async via Twilio API)
        twiml = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
        return Response(content=twiml, media_type="application/xml")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}", exc_info=True)
        twiml = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
        return Response(content=twiml, media_type="application/xml")


@app.post("/webhooks/whatsapp/status", tags=["webhooks"])
async def whatsapp_status_webhook(request: Request):
    """Receive WhatsApp delivery status updates from Twilio."""
    try:
        form_data = dict(await request.form())

        from channels.whatsapp_handler import process_status_callback

        status = await process_status_callback(form_data)

        # Update message delivery status in DB
        if status.get("channel_message_id"):
            try:
                from database.queries import _execute

                pool = request.app.state.db_pool
                await _execute(
                    pool,
                    """
                    UPDATE messages
                    SET delivery_status = $2
                    WHERE channel_message_id = $1
                    """,
                    status["channel_message_id"],
                    status.get("delivery_status", "unknown"),
                )
            except Exception as e:
                logger.warning(f"Failed to update delivery status: {e}")

        return JSONResponse({"status": "ok"})

    except Exception as e:
        logger.error(f"WhatsApp status webhook error: {e}", exc_info=True)
        return JSONResponse({"status": "error"}, status_code=200)


# ── Metrics ──────────────────────────────────────────────────────────────


@app.get("/metrics/channels", tags=["metrics"])
async def get_channel_metrics(
    request: Request,
    hours: int = 24,
    channel: Optional[str] = None,
):
    """Get aggregated metrics per channel.

    Returns response latency, escalation rate, sentiment, and ticket
    counts for each channel over the specified time window.
    """
    try:
        from database.queries import get_metrics_summary

        pool = request.app.state.db_pool
        channels = ["email", "whatsapp", "web_form"] if not channel else [channel]

        metrics = {}
        for ch in channels:
            latency = await get_metrics_summary(pool, "response_latency_ms", hours, ch)
            escalation = await get_metrics_summary(pool, "escalation_rate", hours, ch)
            sentiment = await get_metrics_summary(pool, "sentiment_score", hours, ch)

            metrics[ch] = {
                "latency": latency,
                "escalation_rate": escalation,
                "sentiment": sentiment,
            }

        return {
            "window_hours": hours,
            "channels": metrics,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to fetch metrics: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Metrics unavailable")


# ── Conversations ────────────────────────────────────────────────────────


@app.get("/conversations/{conversation_id}", tags=["conversations"])
async def get_conversation(request: Request, conversation_id: str):
    """Get conversation history by ID."""
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID format")

    try:
        from database.queries import get_conversation_history

        pool = request.app.state.db_pool
        messages = await get_conversation_history(pool, conv_uuid)

        if not messages:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return {
            "conversation_id": conversation_id,
            "message_count": len(messages),
            "messages": [
                {
                    "id": str(m["id"]),
                    "role": m.get("role", ""),
                    "content": m.get("content", ""),
                    "channel": m.get("channel", ""),
                    "direction": m.get("direction", ""),
                    "sentiment_score": float(m["sentiment_score"])
                    if m.get("sentiment_score") is not None
                    else None,
                    "created_at": m["created_at"].isoformat()
                    if hasattr(m.get("created_at"), "isoformat")
                    else str(m.get("created_at", "")),
                }
                for m in messages
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch conversation: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Unable to retrieve conversation")


# ── Customer Lookup ──────────────────────────────────────────────────────


@app.get("/customers/lookup", tags=["customers"])
async def lookup_customer(request: Request, email: Optional[str] = None):
    """Look up a customer by email address."""
    if not email:
        raise HTTPException(status_code=400, detail="Email parameter required")

    try:
        from database.queries import get_or_create_customer

        pool = request.app.state.db_pool
        customer = await get_or_create_customer(pool, email=email)

        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        return {
            "id": str(customer["id"]),
            "email": customer.get("email"),
            "name": customer.get("name"),
            "plan": customer.get("plan"),
            "phone": customer.get("phone"),
            "created_at": customer["created_at"].isoformat()
            if hasattr(customer.get("created_at"), "isoformat")
            else str(customer.get("created_at", "")),
            "last_contact_at": customer["last_contact_at"].isoformat()
            if hasattr(customer.get("last_contact_at"), "isoformat")
            else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Customer lookup failed: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Customer lookup unavailable")


# ── Test / Debug Endpoints ───────────────────────────────────────────────


@app.post("/test/queue", tags=["debug"])
async def test_queue_publish(request: Request, message: str = "test"):
    """Publish a test message to the PostgreSQL queue to verify the pipeline."""
    pool = request.app.state.db_pool

    test_event = {
        "channel": "whatsapp",
        "customer_phone": "+923360840000",
        "customer_name": "Test User",
        "content": message,
        "subject": "Test Message",
        "received_at": datetime.now(timezone.utc).isoformat(),
        "channel_message_id": f"test-{uuid.uuid4().hex[:8]}",
    }

    try:
        msg_id = await publish_message(pool, TOPIC_TICKETS_INCOMING, test_event)
        logger.info(f"Test message enqueued: id={msg_id}")
        return {
            "status": "published",
            "queue": "message_queue",
            "topic": TOPIC_TICKETS_INCOMING,
            "message_id": msg_id,
            "channel_message_id": test_event["channel_message_id"],
        }
    except Exception as e:
        logger.error(f"Test enqueue failed: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Queue publish failed: {e}")


# ── Global Error Handler ─────────────────────────────────────────────────


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all error handler to prevent unhandled 500 errors."""
    logger.error(f"Unhandled error on {request.method} {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal error occurred. Please try again later.",
            "request_id": str(uuid.uuid4()),
        },
    )
