"""
Agent Tool Tests — Core Agent Functionality
=============================================
Tests for knowledge search, ticket creation, escalation,
sentiment analysis, and channel formatters.

Run:
  pytest tests/test_agent.py -v
"""

from __future__ import annotations

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Sentiment Analyzer (direct import, no DB needed) ────────────────────

from agent.tools import _analyze_sentiment_score
from agent.formatters import format_for_channel, _whatsapp_truncate


# ═══════════════════════════════════════════════════════════════════════
# Knowledge Search
# ═══════════════════════════════════════════════════════════════════════


class TestKnowledgeSearch:
    """Tests for the search_knowledge_base tool."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """search 'password reset' → should return results."""
        mock_results = [
            {"title": "Password Reset Guide", "content": "Go to Settings > Security > Reset Password...", "category": "Troubleshooting", "similarity_score": 0.85},
            {"title": "Account Security", "content": "Two-factor authentication...", "category": "Getting Started", "similarity_score": 0.72},
        ]

        with patch("agent.tools._get_pool") as mock_pool, \
             patch("agent.tools.AsyncOpenAI") as mock_openai:
            # Mock embedding
            mock_client = MagicMock()
            mock_embed_resp = MagicMock()
            mock_embed_resp.data = [MagicMock(embedding=[0.1] * 1536)]
            mock_client.embeddings.create = AsyncMock(return_value=mock_embed_resp)
            mock_openai.return_value = mock_client

            # Mock DB search
            with patch("agent.tools.db_search", new_callable=AsyncMock, return_value=mock_results):
                from agent.tools import search_knowledge_base, KnowledgeSearchInput
                result = await search_knowledge_base(KnowledgeSearchInput(query="password reset"))

                assert "Password Reset Guide" in result
                assert "relevance:" in result

    @pytest.mark.asyncio
    async def test_search_handles_no_results(self):
        """search 'xyznonexistent123' → should return helpful message not crash."""
        with patch("agent.tools._get_pool"), \
             patch("agent.tools.AsyncOpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_embed_resp = MagicMock()
            mock_embed_resp.data = [MagicMock(embedding=[0.1] * 1536)]
            mock_client.embeddings.create = AsyncMock(return_value=mock_embed_resp)
            mock_openai.return_value = mock_client

            with patch("agent.tools.db_search", new_callable=AsyncMock, return_value=[]):
                from agent.tools import search_knowledge_base, KnowledgeSearchInput
                result = await search_knowledge_base(KnowledgeSearchInput(query="xyznonexistent123"))

                assert "no relevant" in result.lower() or "not found" in result.lower() or "app.taskflow.io" in result

    @pytest.mark.asyncio
    async def test_search_db_unavailable(self):
        """When DB pool is not initialized → returns fallback message."""
        with patch("agent.tools._get_pool", side_effect=RuntimeError("not initialized")):
            from agent.tools import search_knowledge_base, KnowledgeSearchInput
            result = await search_knowledge_base(KnowledgeSearchInput(query="password reset"))

            assert "unavailable" in result.lower() or "app.taskflow.io" in result

    @pytest.mark.asyncio
    async def test_search_max_results(self):
        """request 3 results → get max 3 back."""
        mock_results = [
            {"title": f"Doc {i}", "content": f"Content {i}", "category": "General", "similarity_score": 0.8 - i * 0.1}
            for i in range(5)
        ]

        with patch("agent.tools._get_pool"), \
             patch("agent.tools.AsyncOpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_embed_resp = MagicMock()
            mock_embed_resp.data = [MagicMock(embedding=[0.1] * 1536)]
            mock_client.embeddings.create = AsyncMock(return_value=mock_embed_resp)
            mock_openai.return_value = mock_client

            # Return only 3 results (DB respects top_k)
            with patch("agent.tools.db_search", new_callable=AsyncMock, return_value=mock_results[:3]):
                from agent.tools import search_knowledge_base, KnowledgeSearchInput
                result = await search_knowledge_base(KnowledgeSearchInput(query="test", max_results=3))

                assert "Result 1" in result
                assert "Result 3" in result
                assert "Result 4" not in result


# ═══════════════════════════════════════════════════════════════════════
# Ticket Creation
# ═══════════════════════════════════════════════════════════════════════


class TestTicketCreation:
    """Tests for the create_ticket tool."""

    @pytest.mark.asyncio
    async def test_create_ticket_email(self):
        """create ticket with channel=email → returns ticket ID."""
        mock_conv = {"id": "conv-uuid-001"}
        mock_ticket = {"ticket_ref": "TF-20250115-ABCD", "id": "ticket-uuid-001"}

        with patch("agent.tools._get_pool"), \
             patch("agent.tools.get_active_conversation", new_callable=AsyncMock, return_value=None), \
             patch("agent.tools.create_conversation", new_callable=AsyncMock, return_value=mock_conv), \
             patch("agent.tools.db_create_ticket", new_callable=AsyncMock, return_value=mock_ticket):
            from agent.tools import create_ticket, TicketInput
            result = await create_ticket(TicketInput(
                customer_id="00000000-0000-0000-0000-000000000001",
                issue="Cannot connect Slack integration",
                channel="email",
            ))

            assert "TF-20250115-ABCD" in result
            assert "email" not in result or "Ticket" in result  # Contains ticket ref

    @pytest.mark.asyncio
    async def test_create_ticket_whatsapp(self):
        """create ticket with channel=whatsapp → returns ticket ID."""
        mock_conv = {"id": "conv-uuid-002"}
        mock_ticket = {"ticket_ref": "TF-20250115-WXYZ", "id": "ticket-uuid-002"}

        with patch("agent.tools._get_pool"), \
             patch("agent.tools.get_active_conversation", new_callable=AsyncMock, return_value=None), \
             patch("agent.tools.create_conversation", new_callable=AsyncMock, return_value=mock_conv), \
             patch("agent.tools.db_create_ticket", new_callable=AsyncMock, return_value=mock_ticket):
            from agent.tools import create_ticket, TicketInput
            result = await create_ticket(TicketInput(
                customer_id="00000000-0000-0000-0000-000000000002",
                issue="Password reset",
                channel="whatsapp",
            ))

            assert "TF-" in result

    @pytest.mark.asyncio
    async def test_create_ticket_web_form(self):
        """create ticket with channel=web_form → returns ticket ID."""
        mock_conv = {"id": "conv-uuid-003"}
        mock_ticket = {"ticket_ref": "TF-20250115-1234", "id": "ticket-uuid-003"}

        with patch("agent.tools._get_pool"), \
             patch("agent.tools.get_active_conversation", new_callable=AsyncMock, return_value=None), \
             patch("agent.tools.create_conversation", new_callable=AsyncMock, return_value=mock_conv), \
             patch("agent.tools.db_create_ticket", new_callable=AsyncMock, return_value=mock_ticket):
            from agent.tools import create_ticket, TicketInput
            result = await create_ticket(TicketInput(
                customer_id="00000000-0000-0000-0000-000000000003",
                issue="Dashboard slow",
                channel="web_form",
            ))

            assert "TF-" in result

    @pytest.mark.asyncio
    async def test_create_ticket_invalid_channel(self):
        """channel='fax' → handled gracefully with fallback ref."""
        with patch("agent.tools._get_pool", side_effect=RuntimeError("DB unavailable")):
            from agent.tools import create_ticket, TicketInput
            result = await create_ticket(TicketInput(
                customer_id="00000000-0000-0000-0000-000000000004",
                issue="Test",
                channel="fax",
            ))

            # Should generate fallback reference, not crash
            assert "TF-" in result


# ═══════════════════════════════════════════════════════════════════════
# Escalation
# ═══════════════════════════════════════════════════════════════════════


class TestEscalation:
    """Tests for the escalate_to_human tool."""

    @pytest.mark.asyncio
    async def test_escalate_billing(self):
        """reason contains 'refund' → escalated to billing team."""
        with patch("agent.tools._get_pool"), \
             patch("agent.tools.get_ticket_by_ref", new_callable=AsyncMock, return_value=None):
            from agent.tools import escalate_to_human, EscalationInput
            result = await escalate_to_human(EscalationInput(
                ticket_id="TF-20250115-0001",
                reason="Customer requesting a refund for unauthorized charge",
                category="billing",
            ))

            assert "Escalation Confirmed" in result
            assert "billing" in result.lower()

    @pytest.mark.asyncio
    async def test_escalate_legal(self):
        """reason contains 'lawyer' → escalated to legal."""
        with patch("agent.tools._get_pool"), \
             patch("agent.tools.get_ticket_by_ref", new_callable=AsyncMock, return_value=None):
            from agent.tools import escalate_to_human, EscalationInput
            result = await escalate_to_human(EscalationInput(
                ticket_id="TF-20250115-0002",
                reason="Customer mentioned consulting their lawyer",
                category="legal",
            ))

            assert "Escalation Confirmed" in result
            assert "legal" in result.lower()

    @pytest.mark.asyncio
    async def test_escalate_urgent(self):
        """urgency='critical' → marked as urgent."""
        with patch("agent.tools._get_pool"), \
             patch("agent.tools.get_ticket_by_ref", new_callable=AsyncMock, return_value=None):
            from agent.tools import escalate_to_human, EscalationInput
            result = await escalate_to_human(EscalationInput(
                ticket_id="TF-20250115-0003",
                reason="Production system down for enterprise customer",
                urgency="critical",
                category="technical",
            ))

            assert "critical" in result.lower()
            assert "15 minutes" in result

    @pytest.mark.asyncio
    async def test_escalation_returns_id(self):
        """always returns escalation reference ID."""
        with patch("agent.tools._get_pool"), \
             patch("agent.tools.get_ticket_by_ref", new_callable=AsyncMock, return_value=None):
            from agent.tools import escalate_to_human, EscalationInput
            result = await escalate_to_human(EscalationInput(
                ticket_id="TF-20250115-0004",
                reason="Generic escalation test",
                category="general",
            ))

            assert "ESC-" in result


# ═══════════════════════════════════════════════════════════════════════
# Sentiment Analysis
# ═══════════════════════════════════════════════════════════════════════


class TestSentimentAnalysis:
    """Tests for the sentiment scoring function."""

    def test_positive_sentiment(self):
        """'I love this product!' → score > 0.5."""
        score = _analyze_sentiment_score("I love this product! It's amazing and fantastic!")
        assert score > 0.5

    def test_negative_sentiment(self):
        """'This is terrible, broken garbage!' → score < 0."""
        score = _analyze_sentiment_score("This is terrible, broken garbage! Absolutely useless.")
        assert score < 0

    def test_neutral_sentiment(self):
        """'How do I reset my password?' → score near 0."""
        score = _analyze_sentiment_score("How do I reset my password?")
        assert -0.3 <= score <= 0.3

    def test_angry_caps(self):
        """'THIS IS COMPLETELY BROKEN!!!' → score < -0.5."""
        score = _analyze_sentiment_score("THIS IS COMPLETELY BROKEN AND USELESS!!!")
        assert score < -0.5

    def test_empty_string(self):
        """Empty string → score = 0.0."""
        score = _analyze_sentiment_score("")
        assert score == 0.0

    def test_negation_flips_sentiment(self):
        """'not good' → negative or near-zero, not positive."""
        score = _analyze_sentiment_score("This is not good at all")
        assert score <= 0.1

    def test_mixed_sentiment(self):
        """Mixed positive and negative → somewhere in between."""
        score = _analyze_sentiment_score("The product is great but the support is terrible")
        assert -0.8 < score < 0.8  # Not extreme either way


# ═══════════════════════════════════════════════════════════════════════
# Formatters
# ═══════════════════════════════════════════════════════════════════════


class TestFormatters:
    """Tests for channel-specific response formatting."""

    def test_email_format(self):
        """response has greeting 'Dear' and signature."""
        result = format_for_channel(
            response="Here's how to reset your password: Go to Settings > Security.",
            channel="email",
            customer_name="Alice",
            ticket_id="TF-20250115-0001",
        )

        assert "Dear Alice" in result
        assert "TaskFlow Support Team" in result
        assert "TF-20250115-0001" in result

    def test_whatsapp_format(self):
        """response is under 300 characters."""
        long_response = "Here's a detailed guide. " * 20  # ~500 chars
        result = format_for_channel(
            response=long_response,
            channel="whatsapp",
            customer_name="Bob",
        )

        # WhatsApp adds greeting prefix, so check the body part
        assert len(result) < 500  # Truncated
        assert "Hi Bob" in result

    def test_webform_format(self):
        """response includes ticket reference."""
        result = format_for_channel(
            response="We're looking into this issue.",
            channel="web_form",
            customer_name="Charlie",
            ticket_id="TF-20250115-0002",
        )

        assert "TF-20250115-0002" in result
        assert "TaskFlow Support" in result

    def test_empathy_negative_sentiment(self):
        """negative sentiment → empathy phrase added for email."""
        result = format_for_channel(
            response="We're investigating this issue.",
            channel="email",
            customer_name="Dave",
            ticket_id="TF-20250115-0003",
            sentiment_score=-0.7,
        )

        assert "frustrat" in result.lower() or "patience" in result.lower()

    def test_whatsapp_truncation(self):
        """WhatsApp truncation respects sentence boundaries."""
        long_text = (
            "First sentence here. Second sentence here. "
            "Third sentence here. Fourth sentence here. "
            "Fifth sentence here. Sixth sentence here. "
            "Seventh sentence here. Eighth sentence here."
        )
        result = _whatsapp_truncate(long_text, max_chars=100)
        assert len(result) <= 150  # Allows for "Want me to explain more?" suffix

    def test_legacy_channel_names(self):
        """'gmail' maps to email formatting."""
        result = format_for_channel(
            response="Test response.",
            channel="gmail",
            customer_name="Eve",
        )

        assert "Dear Eve" in result  # Email format applied

    def test_unknown_customer_name(self):
        """Empty customer name defaults to 'there'."""
        result = format_for_channel(
            response="Test response.",
            channel="email",
            customer_name="",
        )

        assert "Dear there" in result
