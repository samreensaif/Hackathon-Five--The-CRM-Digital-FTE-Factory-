"""
Web Form Channel Handler — FastAPI Router
==========================================
Receives support form submissions via HTTP POST and returns
structured responses with ticket IDs.

Endpoints:
  POST /support/submit   — Submit a new support request
  GET  /support/ticket/{id} — Check ticket status and history

Incoming flow:
  Browser form → POST /support/submit → validate → normalize
  → publish to Kafka → return ticket confirmation

This is the simplest channel: no external APIs, no webhooks,
just validated HTTP requests from our own frontend.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator

logger = logging.getLogger("channels.web_form")

router = APIRouter(prefix="/support", tags=["support-form"])


# ── Request / Response Models ────────────────────────────────────────────


VALID_CATEGORIES = ["general", "technical", "billing", "feedback", "bug_report"]
VALID_PRIORITIES = ["low", "medium", "high", "urgent"]


class SupportFormSubmission(BaseModel):
    """Support form submission with validation.

    All fields are validated before processing. Invalid submissions
    return 422 with specific field errors.
    """

    name: str = Field(min_length=2, max_length=255, description="Customer's full name")
    email: EmailStr = Field(description="Customer's email address")
    subject: str = Field(min_length=3, max_length=500, description="Issue subject line")
    category: str = Field(
        default="general",
        description="Issue category: general, technical, billing, feedback, bug_report",
    )
    message: str = Field(min_length=10, max_length=5000, description="Detailed description of the issue")
    priority: str = Field(default="medium", description="Priority: low, medium, high, urgent")
    plan: str = Field(default="free", description="Customer plan: free, pro, enterprise")

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v

    @field_validator("subject")
    @classmethod
    def subject_must_have_content(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Subject must be at least 3 characters")
        return v

    @field_validator("message")
    @classmethod
    def message_must_have_content(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Message must be at least 10 characters")
        return v

    @field_validator("category")
    @classmethod
    def category_must_be_valid(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError(f"Category must be one of: {VALID_CATEGORIES}")
        return v

    @field_validator("priority")
    @classmethod
    def priority_must_be_valid(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"Priority must be one of: {VALID_PRIORITIES}")
        return v


class SupportFormResponse(BaseModel):
    """Response after successful form submission."""

    ticket_id: str = Field(description="Unique ticket reference (TF-YYYYMMDD-XXXX)")
    message: str = Field(description="Confirmation message")
    estimated_response_time: str = Field(description="SLA-based response time estimate")
    status: str = Field(default="received", description="Ticket status")


class TicketStatusResponse(BaseModel):
    """Response for ticket status queries."""

    ticket_id: str
    status: str
    created_at: str
    subject: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    messages: list[dict] = Field(default_factory=list)
    assigned_to: Optional[str] = None


# ── SLA Configuration ────────────────────────────────────────────────────

SLA_RESPONSE_TIMES = {
    "enterprise": "within 1 hour",
    "pro": "within 4 hours",
    "free": "within 24 hours",
}


# ── Endpoints ────────────────────────────────────────────────────────────


@router.post("/submit", response_model=SupportFormResponse)
async def submit_support_form(submission: SupportFormSubmission):
    """Handle a new support form submission.

    Workflow:
      1. Validate the submission (handled by Pydantic)
      2. Generate a ticket reference ID
      3. Normalize to standard message format
      4. Publish to Kafka for agent processing
      5. Store initial record in database
      6. Return confirmation with ticket ID and SLA
    """
    # Generate ticket reference
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    short_id = uuid.uuid4().hex[:4].upper()
    ticket_id = f"TF-{date_str}-{short_id}"

    # Build normalized message (same format as other channels)
    normalized_message = {
        "channel": "web_form",
        "channel_message_id": ticket_id,
        "customer_email": submission.email,
        "customer_name": submission.name,
        "subject": submission.subject,
        "content": submission.message,
        "category": submission.category,
        "priority": submission.priority,
        "customer_plan": submission.plan,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "form_version": "1.0",
            "source": "web_form",
        },
    }

    # Publish to Kafka for async processing
    try:
        from kafka_client import get_producer

        producer = get_producer()
        if producer:
            await producer.publish("fte.channels.webform.inbound", normalized_message)
            logger.info(f"Web form submission published to Kafka: {ticket_id}")
    except Exception as e:
        logger.warning(f"Kafka publish failed (processing synchronously): {e}")

    # Also attempt direct database storage for immediate tracking
    try:
        from agent.tools import _get_pool
        from database.queries import (
            create_conversation,
            create_ticket,
            get_or_create_customer,
        )

        pool = _get_pool()

        # Get or create customer
        customer = await get_or_create_customer(
            pool,
            email=submission.email,
            name=submission.name,
            plan=submission.plan,
        )

        # Create conversation
        conversation = await create_conversation(
            pool, customer["id"], "web_form"
        )

        # Create ticket
        await create_ticket(
            pool,
            conversation_id=conversation["id"],
            customer_id=customer["id"],
            source_channel="web_form",
            subject=submission.subject,
            category=submission.category,
            priority=submission.priority,
        )

        logger.info(f"Web form submission stored in DB: {ticket_id}")

    except Exception as e:
        logger.warning(f"DB storage failed (Kafka will handle): {e}")

    # Determine SLA response time
    response_time = SLA_RESPONSE_TIMES.get(submission.plan, "within 24 hours")

    logger.info(
        f"Support form submitted: ticket={ticket_id}, "
        f"email={submission.email}, category={submission.category}"
    )

    return SupportFormResponse(
        ticket_id=ticket_id,
        message=(
            f"Thank you for contacting TaskFlow Support, {submission.name}! "
            f"We've received your request and will respond {response_time}."
        ),
        estimated_response_time=response_time,
        status="received",
    )


@router.get("/ticket/{ticket_id}", response_model=TicketStatusResponse)
async def get_ticket_status(ticket_id: str):
    """Get the current status of a support ticket.

    Returns ticket details, status, and conversation messages.
    Used by the frontend to show ticket progress to customers.
    """
    # Validate ticket_id format
    import re

    if not re.match(r"^TF-\d{8}-[A-Z0-9]{4}$", ticket_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid ticket ID format. Expected: TF-YYYYMMDD-XXXX",
        )

    try:
        from agent.tools import _get_pool
        from database.queries import get_conversation_history, get_ticket_by_ref

        pool = _get_pool()
        ticket = await get_ticket_by_ref(pool, ticket_id)

        if not ticket:
            raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")

        # Fetch conversation messages
        messages = []
        if ticket.get("conversation_id"):
            raw_messages = await get_conversation_history(
                pool, ticket["conversation_id"], limit=50
            )
            messages = [
                {
                    "role": m.get("role", ""),
                    "content": m.get("content", ""),
                    "channel": m.get("channel", ""),
                    "created_at": m.get("created_at", "").isoformat()
                    if hasattr(m.get("created_at", ""), "isoformat")
                    else str(m.get("created_at", "")),
                }
                for m in raw_messages
            ]

        return TicketStatusResponse(
            ticket_id=ticket_id,
            status=ticket.get("status", "unknown"),
            created_at=ticket.get("created_at", "").isoformat()
            if hasattr(ticket.get("created_at", ""), "isoformat")
            else str(ticket.get("created_at", "")),
            subject=ticket.get("subject"),
            category=ticket.get("category"),
            priority=ticket.get("priority"),
            messages=messages,
            assigned_to=ticket.get("assigned_to"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch ticket status for {ticket_id}: {e}")
        raise HTTPException(
            status_code=503,
            detail="Unable to retrieve ticket status. Please try again later.",
        )


# ── Health Check ─────────────────────────────────────────────────────────


@router.get("/health")
async def health_check():
    """Health check endpoint for the web form service."""
    return {"status": "ok", "channel": "web_form"}
