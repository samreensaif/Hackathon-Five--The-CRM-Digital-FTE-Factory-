"""
End-to-End Tests — Customer Journey Simulations
==================================================
Tests simulating real customer journeys across channels,
from form submission through agent processing to response delivery.

Run:
  pytest tests/test_e2e.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════
# Web Form Journey
# ═══════════════════════════════════════════════════════════════════════


class TestWebFormJourney:
    """End-to-end tests for the web form submission flow."""

    def test_complete_form_submission(self, test_client, sample_webform_submission):
        """Submit form → verify ticket_id returned + estimated_response_time."""
        with patch("channels.web_form_handler.get_producer", return_value=None), \
             patch("channels.web_form_handler._get_pool", side_effect=RuntimeError("no db")):
            response = test_client.post("/support/submit", json=sample_webform_submission)

            assert response.status_code == 200
            data = response.json()

            # Verify ticket ID format
            assert data["ticket_id"].startswith("TF-")
            assert len(data["ticket_id"]) == 16  # TF-YYYYMMDD-XXXX

            # Verify estimated response time
            assert "estimated_response_time" in data
            assert "within" in data["estimated_response_time"]

            # Verify status
            assert data["status"] == "received"

    def test_form_to_kafka_publish(self, test_client, sample_webform_submission):
        """Submit form → verify message published to Kafka."""
        mock_producer = MagicMock()
        mock_producer.publish = AsyncMock()

        with patch("channels.web_form_handler.get_producer", return_value=mock_producer), \
             patch("channels.web_form_handler._get_pool", side_effect=RuntimeError("no db")):
            response = test_client.post("/support/submit", json=sample_webform_submission)

            assert response.status_code == 200

            # Verify Kafka publish was called
            mock_producer.publish.assert_called_once()
            call_args = mock_producer.publish.call_args
            assert call_args[0][0] == "fte.channels.webform.inbound"
            published_msg = call_args[0][1]
            assert published_msg["channel"] == "web_form"
            assert published_msg["customer_email"] == "charlie@example.com"

    def test_enterprise_gets_fast_sla(self, test_client, sample_webform_submission):
        """Enterprise plan → 'within 1 hour' SLA."""
        sample_webform_submission["plan"] = "enterprise"

        with patch("channels.web_form_handler.get_producer", return_value=None), \
             patch("channels.web_form_handler._get_pool", side_effect=RuntimeError("no db")):
            response = test_client.post("/support/submit", json=sample_webform_submission)

            data = response.json()
            assert "1 hour" in data["estimated_response_time"]

    def test_free_gets_standard_sla(self, test_client):
        """Free plan → 'within 24 hours' SLA."""
        submission = {
            "name": "Free User",
            "email": "free@example.com",
            "subject": "How do I use this?",
            "category": "general",
            "priority": "low",
            "message": "I'm new to TaskFlow and trying to understand how it works.",
            "plan": "free",
        }

        with patch("channels.web_form_handler.get_producer", return_value=None), \
             patch("channels.web_form_handler._get_pool", side_effect=RuntimeError("no db")):
            response = test_client.post("/support/submit", json=submission)

            data = response.json()
            assert "24 hours" in data["estimated_response_time"]


# ═══════════════════════════════════════════════════════════════════════
# Cross-Channel Journey
# ═══════════════════════════════════════════════════════════════════════


class TestCrossChannelJourney:
    """Tests for cross-channel customer recognition."""

    @pytest.mark.asyncio
    async def test_customer_recognized_across_channels(self):
        """Same email on web form and WhatsApp → same customer resolved."""
        from database.queries import get_or_create_customer

        mock_pool = MagicMock()
        customer_record = {
            "id": "uuid-cross-001",
            "email": "crosschannel@example.com",
            "name": "Cross User",
            "plan": "pro",
            "phone": "+15559876543",
            "last_contact_at": None,
        }

        # First call creates, second call finds existing
        with patch("database.queries._fetchrow", new_callable=AsyncMock) as mock_fetch, \
             patch("database.queries._execute", new_callable=AsyncMock), \
             patch("database.queries.link_customer_identifier", new_callable=AsyncMock):

            # Simulate: first lookup by email returns the customer
            mock_fetch.return_value = customer_record

            result_web = await get_or_create_customer(
                mock_pool, email="crosschannel@example.com", name="Cross User"
            )
            result_whatsapp = await get_or_create_customer(
                mock_pool, email="crosschannel@example.com"
            )

            # Both should resolve to same customer
            assert result_web["id"] == result_whatsapp["id"]
            assert result_web["email"] == "crosschannel@example.com"


# ═══════════════════════════════════════════════════════════════════════
# Escalation Journey
# ═══════════════════════════════════════════════════════════════════════


class TestEscalationJourney:
    """Tests for escalation flows triggered by content and sentiment."""

    @pytest.mark.asyncio
    async def test_billing_escalation_flow(self):
        """Submit 'refund request' → escalation triggered with billing team."""
        with patch("agent.tools._get_pool"), \
             patch("agent.tools.get_ticket_by_ref", new_callable=AsyncMock, return_value=None):
            from agent.tools import escalate_to_human, EscalationInput

            result = await escalate_to_human(EscalationInput(
                ticket_id="TF-20250115-BILL",
                reason="Customer requesting refund for unauthorized charge",
                category="billing",
                urgency="high",
            ))

            assert "Escalation Confirmed" in result
            assert "billing" in result.lower()
            assert "TF-20250115-BILL" in result

    @pytest.mark.asyncio
    async def test_angry_customer_triggers_negative_sentiment(self):
        """Very negative message → sentiment detected as negative."""
        from agent.tools import _analyze_sentiment_score

        score = _analyze_sentiment_score(
            "THIS IS RIDICULOUS YOUR PRODUCT IS COMPLETELY BROKEN "
            "AND USELESS! I've been trying for THREE DAYS and NOTHING works. "
            "This is the WORST software I've EVER used!!!"
        )

        assert score < -0.3  # Definitely negative

    @pytest.mark.asyncio
    async def test_escalation_includes_assigned_team(self):
        """Escalation response includes assigned team and response time."""
        with patch("agent.tools._get_pool"), \
             patch("agent.tools.get_ticket_by_ref", new_callable=AsyncMock, return_value=None):
            from agent.tools import escalate_to_human, EscalationInput

            result = await escalate_to_human(EscalationInput(
                ticket_id="TF-20250115-TEAM",
                reason="Security vulnerability report",
                category="security",
                urgency="critical",
            ))

            assert "Assigned to:" in result
            assert "Expected response:" in result
            assert "15 minutes" in result  # critical urgency


# ═══════════════════════════════════════════════════════════════════════
# Channel Metrics
# ═══════════════════════════════════════════════════════════════════════


class TestChannelMetrics:
    """Tests for the metrics endpoint."""

    def test_health_endpoint(self, test_client):
        """GET /health → status: healthy."""
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_metrics_endpoint_structure(self, test_client):
        """GET /metrics/channels → response has correct structure."""
        mock_summary = {
            "metric_name": "test",
            "window_hours": 24,
            "channel": "email",
            "count": 0,
            "avg": None,
            "min": None,
            "max": None,
            "p50": None,
            "p95": None,
        }

        with patch("api.main.get_metrics_summary", new_callable=AsyncMock, return_value=mock_summary):
            response = test_client.get("/metrics/channels?hours=24")

            assert response.status_code == 200
            data = response.json()
            assert "window_hours" in data
            assert "channels" in data or "generated_at" in data
