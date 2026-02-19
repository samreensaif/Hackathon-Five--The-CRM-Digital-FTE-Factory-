"""
Channel Handler Tests — Gmail, WhatsApp, Web Form
===================================================
Tests for channel-specific message processing, validation,
and response delivery.

Run:
  pytest tests/test_channels.py -v
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════
# Web Form Validation
# ═══════════════════════════════════════════════════════════════════════


class TestWebFormValidation:
    """Tests for web form submission validation via FastAPI."""

    def test_valid_submission(self, test_client, sample_webform_submission):
        """all fields valid → 200 response with ticket_id."""
        with patch("channels.web_form_handler.get_producer", return_value=None), \
             patch("channels.web_form_handler._get_pool", side_effect=RuntimeError("no db")):
            response = test_client.post("/support/submit", json=sample_webform_submission)

            assert response.status_code == 200
            data = response.json()
            assert "ticket_id" in data
            assert data["ticket_id"].startswith("TF-")
            assert "status" in data

    def test_name_too_short(self, test_client, sample_webform_submission):
        """name='A' → 422 validation error."""
        sample_webform_submission["name"] = "A"
        response = test_client.post("/support/submit", json=sample_webform_submission)
        assert response.status_code == 422

    def test_invalid_email(self, test_client, sample_webform_submission):
        """email='notanemail' → 422 validation error."""
        sample_webform_submission["email"] = "notanemail"
        response = test_client.post("/support/submit", json=sample_webform_submission)
        assert response.status_code == 422

    def test_message_too_short(self, test_client, sample_webform_submission):
        """message='Hi' → 422 validation error."""
        sample_webform_submission["message"] = "Hi"
        response = test_client.post("/support/submit", json=sample_webform_submission)
        assert response.status_code == 422

    def test_invalid_category(self, test_client, sample_webform_submission):
        """category='unknown' → 422 validation error."""
        sample_webform_submission["category"] = "unknown"
        response = test_client.post("/support/submit", json=sample_webform_submission)
        assert response.status_code == 422

    def test_subject_too_short(self, test_client, sample_webform_submission):
        """subject='Hi' → 422 validation error."""
        sample_webform_submission["subject"] = "Hi"
        response = test_client.post("/support/submit", json=sample_webform_submission)
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
# Gmail Handler
# ═══════════════════════════════════════════════════════════════════════


class TestGmailHandler:
    """Tests for Gmail message processing utilities."""

    def test_extract_email(self):
        """'John Doe <john@example.com>' → 'john@example.com'."""
        from channels.gmail_handler import extract_email

        assert extract_email("John Doe <john@example.com>") == "john@example.com"
        assert extract_email("<john@example.com>") == "john@example.com"
        assert extract_email("john@example.com") == "john@example.com"
        assert extract_email("") is None

    def test_extract_name(self):
        """'John Doe <john@example.com>' → 'John Doe'."""
        from channels.gmail_handler import extract_name

        assert extract_name("John Doe <john@example.com>") == "John Doe"
        assert extract_name('"Jane Smith" <jane@example.com>') == "Jane Smith"
        assert extract_name("john@example.com") is None

    def test_body_extraction(self):
        """multipart email → extracts text/plain part."""
        from channels.gmail_handler import _extract_body

        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {
                        # "Hello world" base64url encoded
                        "data": "SGVsbG8gd29ybGQ",
                    },
                },
                {
                    "mimeType": "text/html",
                    "body": {
                        "data": "PGI+SGVsbG8gd29ybGQ8L2I+",
                    },
                },
            ],
        }

        result = _extract_body(payload)
        assert "Hello world" in result

    def test_body_extraction_plain(self):
        """Simple text/plain → extracted directly."""
        from channels.gmail_handler import _extract_body

        payload = {
            "mimeType": "text/plain",
            "body": {"data": "SGVsbG8"},
        }

        result = _extract_body(payload)
        assert "Hello" in result

    def test_subject_re_prefix(self):
        """subject already has 'Re:' → not duplicated."""
        from channels.gmail_handler import _clean_subject

        assert _clean_subject("Re: Support Request") == "Support Request"
        assert _clean_subject("Re: Re: Re: Help") == "Help"
        assert _clean_subject("Fwd: Re: Help") == "Help"
        assert _clean_subject("") == "Support Request"  # fallback


# ═══════════════════════════════════════════════════════════════════════
# WhatsApp Handler
# ═══════════════════════════════════════════════════════════════════════


class TestWhatsAppHandler:
    """Tests for WhatsApp message processing."""

    def test_phone_normalization(self):
        """'+1234567890' → 'whatsapp:+1234567890'."""
        from channels.whatsapp_handler import _normalize_phone, _to_whatsapp_format

        assert _normalize_phone("whatsapp:+1234567890") == "+1234567890"
        assert _normalize_phone("+1234567890") == "+1234567890"
        assert _normalize_phone("1234567890") == "+1234567890"
        assert _to_whatsapp_format("+1234567890") == "whatsapp:+1234567890"

    def test_message_splitting(self):
        """message > 1600 chars → splits at sentence boundary."""
        from channels.whatsapp_handler import split_message

        long_msg = "This is a test sentence. " * 100  # ~2500 chars
        parts = split_message(long_msg, max_length=1600)

        assert len(parts) >= 2
        for part in parts:
            assert len(part) <= 1600

    def test_short_message_no_split(self):
        """message < 1600 chars → returns single message."""
        from channels.whatsapp_handler import split_message

        short_msg = "Hello, how can I help?"
        parts = split_message(short_msg)

        assert len(parts) == 1
        assert parts[0] == short_msg

    @pytest.mark.asyncio
    async def test_process_webhook(self):
        """valid form data → normalized message dict."""
        from channels.whatsapp_handler import process_webhook

        form_data = {
            "MessageSid": "SM1234567890",
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+14155238886",
            "Body": "How do I reset my password?",
            "ProfileName": "Test User",
            "WaId": "15551234567",
            "NumMedia": "0",
            "SmsStatus": "received",
        }

        result = await process_webhook(form_data)

        assert result is not None
        assert result["channel"] == "whatsapp"
        assert result["customer_phone"] == "+15551234567"
        assert result["content"] == "How do I reset my password?"
        assert result["customer_name"] == "Test User"

    @pytest.mark.asyncio
    async def test_process_webhook_empty_message(self):
        """empty message body with no media → returns None."""
        from channels.whatsapp_handler import process_webhook

        form_data = {
            "MessageSid": "SM9999999999",
            "From": "whatsapp:+15559999999",
            "Body": "",
            "NumMedia": "0",
        }

        result = await process_webhook(form_data)
        assert result is None

    @pytest.mark.asyncio
    async def test_process_webhook_missing_sid(self):
        """missing MessageSid → returns None."""
        from channels.whatsapp_handler import process_webhook

        form_data = {
            "From": "whatsapp:+15551111111",
            "Body": "Hello",
        }

        result = await process_webhook(form_data)
        assert result is None
