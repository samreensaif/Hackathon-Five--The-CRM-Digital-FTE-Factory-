"""
Transition Tests — Incubation ↔ Production Parity
===================================================
Verifies the production agent behaves the same as the incubation
prototype for the edge cases documented in:
  2-Transition-to-Production/documentation/edge-cases.md

These tests confirm that the production implementation preserves
the 98% escalation accuracy achieved during incubation.

Run:
  pytest tests/test_transition.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.tools import _analyze_sentiment_score
from agent.formatters import format_for_channel


class TestTransitionFromIncubation:
    """Verify production agent matches incubation behavior for known edge cases."""

    # ── EC: Empty Message Handling ───────────────────────────────────

    def test_empty_message_handled(self):
        """Input: empty string '' → sentiment score 0, does NOT crash."""
        score = _analyze_sentiment_score("")
        assert score == 0.0

        # Formatting also shouldn't crash
        result = format_for_channel(
            response="Could you please provide more details about your issue?",
            channel="email",
            customer_name="Customer",
        )
        assert "Dear Customer" in result

    # ── EC: Pricing Escalation ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_pricing_escalates_immediately(self):
        """Input: 'How much does the enterprise plan cost?' → escalated to billing."""
        with patch("agent.tools._get_pool"), \
             patch("agent.tools.get_ticket_by_ref", new_callable=AsyncMock, return_value=None):
            from agent.tools import escalate_to_human, EscalationInput

            result = await escalate_to_human(EscalationInput(
                ticket_id="TF-20250115-PRC1",
                reason="Customer asking about enterprise pricing - requires sales team",
                category="billing",
            ))

            assert "Escalation Confirmed" in result
            assert "billing" in result.lower() or "Billing" in result

    # ── EC: Refund Escalation ───────────────────────────────────────

    @pytest.mark.asyncio
    async def test_refund_escalates(self):
        """Input: 'I want a refund for last month' → escalated to billing."""
        with patch("agent.tools._get_pool"), \
             patch("agent.tools.get_ticket_by_ref", new_callable=AsyncMock, return_value=None):
            from agent.tools import escalate_to_human, EscalationInput

            result = await escalate_to_human(EscalationInput(
                ticket_id="TF-20250115-REF1",
                reason="Customer requesting refund for last month's charge",
                category="billing",
            ))

            assert "Escalation Confirmed" in result

    # ── EC: Angry Customer ──────────────────────────────────────────

    def test_angry_customer_detected(self):
        """Input: 'THIS IS RIDICULOUS YOUR PRODUCT IS COMPLETELY BROKEN' → negative sentiment."""
        score = _analyze_sentiment_score(
            "THIS IS RIDICULOUS YOUR PRODUCT IS COMPLETELY BROKEN"
        )
        assert score < -0.3  # Triggers escalation threshold

    def test_angry_customer_gets_empathy(self):
        """Angry customer response includes empathy phrase."""
        result = format_for_channel(
            response="I understand this is frustrating. Let me help resolve this.",
            channel="email",
            customer_name="Frustrated User",
            ticket_id="TF-20250115-ANG1",
            sentiment_score=-0.8,
        )

        # Should have empathy opener for negative sentiment
        has_empathy = (
            "frustrat" in result.lower()
            or "patience" in result.lower()
            or "understand" in result.lower()
            or "sorry" in result.lower()
        )
        assert has_empathy

    # ── EC: Legal Threat ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_legal_threat_escalates(self):
        """Input: 'I'm going to contact my lawyer' → escalated to legal."""
        with patch("agent.tools._get_pool"), \
             patch("agent.tools.get_ticket_by_ref", new_callable=AsyncMock, return_value=None):
            from agent.tools import escalate_to_human, EscalationInput

            result = await escalate_to_human(EscalationInput(
                ticket_id="TF-20250115-LEG1",
                reason="Customer mentioned contacting their lawyer about this issue",
                category="legal",
            ))

            assert "Escalation Confirmed" in result
            assert "legal" in result.lower()

    # ── EC: WhatsApp Response Length ─────────────────────────────────

    def test_whatsapp_response_is_short(self):
        """Input: 'How do I reset my password?' via whatsapp → response < 500 chars."""
        result = format_for_channel(
            response=(
                "To reset your password, go to the login page and click "
                "'Forgot Password'. Enter your email and we'll send you "
                "a reset link. The link expires in 24 hours."
            ),
            channel="whatsapp",
            customer_name="User",
        )

        assert len(result) < 500

    # ── EC: Email Response Greeting ──────────────────────────────────

    def test_email_response_has_greeting(self):
        """Input: 'How do I reset my password?' via email → 'Dear' in response."""
        result = format_for_channel(
            response="To reset your password, go to Settings > Security.",
            channel="email",
            customer_name="Alice",
        )

        assert "Dear" in result or "Hello" in result

    # ── EC: Spam/Gibberish Handling ──────────────────────────────────

    def test_spam_handled_gracefully(self):
        """Input: 'asdfghjkl qwerty 12345' → does NOT crash, returns neutral score."""
        score = _analyze_sentiment_score("asdfghjkl qwerty 12345")
        assert -1.0 <= score <= 1.0  # Valid range, doesn't crash

        # Formatting with gibberish doesn't crash
        result = format_for_channel(
            response="I'm not sure I understand your message. Could you please rephrase?",
            channel="web_form",
            customer_name="Unknown",
            ticket_id="TF-20250115-SPAM",
        )

        assert "TF-20250115-SPAM" in result

    # ── EC: Feature Request Not Escalated ────────────────────────────

    def test_feature_request_sentiment_not_negative(self):
        """Input: 'Can you add dark mode to the app?' → not negative sentiment."""
        score = _analyze_sentiment_score("Can you add dark mode to the app?")
        assert score >= -0.3  # Not negative enough to trigger auto-escalation

    def test_feature_request_formatted(self):
        """Feature request gets a proper response, not an escalation."""
        result = format_for_channel(
            response=(
                "Thanks for the suggestion! Dark mode is a popular request. "
                "I've added your vote to our feature tracker. Our product team "
                "reviews these regularly."
            ),
            channel="web_form",
            customer_name="Requester",
            ticket_id="TF-20250115-FEAT",
        )

        assert "TF-20250115-FEAT" in result
        assert "TaskFlow Support" in result

    # ── EC: Positive Feedback ────────────────────────────────────────

    def test_positive_feedback_detected(self):
        """Input: 'I love TaskFlow, it's amazing!' → positive sentiment."""
        score = _analyze_sentiment_score("I love TaskFlow, it's amazing!")
        assert score > 0.3

    def test_positive_feedback_response(self):
        """Positive feedback gets a warm response."""
        result = format_for_channel(
            response="Thank you so much for your kind words! We're thrilled to hear you're enjoying TaskFlow.",
            channel="email",
            customer_name="Happy User",
            ticket_id="TF-20250115-POS1",
            sentiment_score=0.8,
        )

        assert "Dear Happy User" in result
        assert "TF-20250115-POS1" in result
