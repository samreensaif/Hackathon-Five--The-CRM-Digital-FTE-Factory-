"""
Shared Test Fixtures — Customer Success Digital FTE
=====================================================
Provides reusable fixtures for all test modules.

Usage:
  pytest tests/ -v
"""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the production package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── FastAPI Test Client ──────────────────────────────────────────────────


@pytest.fixture
def test_client():
    """FastAPI TestClient with mocked DB pool and Kafka producer."""
    from fastapi.testclient import TestClient

    # Mock the database pool before importing app
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock())

    with patch("api.main.asyncpg") as mock_asyncpg, \
         patch("api.main.init_producer", new_callable=AsyncMock), \
         patch("api.main.shutdown_producer", new_callable=AsyncMock), \
         patch("agent.tools.set_db_pool"):
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

        from api.main import app
        client = TestClient(app)
        yield client


# ── Sample Ticket Fixtures ──────────────────────────────────────────────


@pytest.fixture
def sample_email_ticket():
    """Normalized email ticket message."""
    return {
        "channel": "email",
        "channel_message_id": "msg-001-gmail",
        "customer_email": "alice@example.com",
        "customer_name": "Alice Johnson",
        "customer_plan": "pro",
        "subject": "Cannot connect Slack integration",
        "content": "Hi, I've been trying to set up the Slack integration for my team but keep getting an authentication error. Can you help?",
        "received_at": "2025-01-15T10:30:00Z",
        "metadata": {
            "gmail_message_id": "msg-001-gmail",
            "gmail_thread_id": "thread-001",
            "message_id_header": "<abc123@mail.gmail.com>",
        },
    }


@pytest.fixture
def sample_whatsapp_ticket():
    """Normalized WhatsApp ticket message."""
    return {
        "channel": "whatsapp",
        "channel_message_id": "SM1234567890abcdef",
        "customer_phone": "+15551234567",
        "customer_name": "Bob Smith",
        "customer_plan": "free",
        "subject": "",
        "content": "Hey, how do I reset my password? I forgot it and can't log in.",
        "received_at": "2025-01-15T11:00:00Z",
        "metadata": {
            "wa_id": "15551234567",
            "num_media": "0",
        },
    }


@pytest.fixture
def sample_webform_submission():
    """Valid web form submission payload."""
    return {
        "name": "Charlie Brown",
        "email": "charlie@example.com",
        "subject": "Dashboard loading slowly",
        "category": "technical",
        "priority": "medium",
        "message": "My dashboard has been loading very slowly for the past two days. It takes about 30 seconds to load each page.",
        "plan": "enterprise",
    }


@pytest.fixture
def angry_customer_message():
    """Message with very negative sentiment for escalation testing."""
    return {
        "channel": "email",
        "channel_message_id": "msg-angry-001",
        "customer_email": "angry@example.com",
        "customer_name": "Frustrated User",
        "customer_plan": "pro",
        "subject": "THIS IS COMPLETELY UNACCEPTABLE",
        "content": (
            "THIS IS RIDICULOUS! YOUR PRODUCT IS COMPLETELY BROKEN AND "
            "USELESS! I've been trying to use it for three days and NOTHING "
            "works. I want a full refund and I'm telling everyone to avoid "
            "TaskFlow. This is the worst software I've ever used!!!"
        ),
        "received_at": "2025-01-15T14:00:00Z",
        "metadata": {},
    }


@pytest.fixture
def billing_escalation_message():
    """Message that should trigger billing escalation."""
    return {
        "channel": "web_form",
        "channel_message_id": "msg-billing-001",
        "customer_email": "billing@example.com",
        "customer_name": "Jane Doe",
        "customer_plan": "pro",
        "subject": "Refund request for last month",
        "content": (
            "I was charged $29.99 last month but I cancelled my subscription "
            "on the 2nd. I would like a full refund for this unauthorized charge. "
            "Please process this as soon as possible."
        ),
        "received_at": "2025-01-15T15:00:00Z",
        "metadata": {},
    }
