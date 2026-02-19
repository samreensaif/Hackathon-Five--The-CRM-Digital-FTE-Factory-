"""
Gmail Channel Handler — Email Integration
==========================================
Receives and sends email via the Gmail API with OAuth2 authentication.

Incoming flow:
  Gmail Pub/Sub notification → process_notification() → normalized message dict
  → published to Kafka topic (fte.channels.email.inbound)

Outgoing flow:
  Agent response → send_reply() → Gmail API → delivery confirmation

Setup:
  1. Create a Google Cloud project with Gmail API enabled
  2. Create OAuth2 credentials (Desktop or Web Application)
  3. Set environment variables:
     - GMAIL_CREDENTIALS_JSON: Path to credentials.json
     - GMAIL_TOKEN_JSON: Path to token.json (auto-created on first auth)
     - GMAIL_WATCH_TOPIC: Pub/Sub topic for push notifications
     - GMAIL_SUPPORT_EMAIL: The support inbox email (support@techcorp.io)
  4. Run setup_watch() once to register Pub/Sub notifications

Dependencies:
  google-api-python-client, google-auth-oauthlib, google-auth-httplib2
"""

from __future__ import annotations

import base64
import email
import logging
import os
import re
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger("channels.gmail")

# ── Configuration ────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

CREDENTIALS_PATH = os.environ.get("GMAIL_CREDENTIALS_JSON", "credentials.json")
TOKEN_PATH = os.environ.get("GMAIL_TOKEN_JSON", "token.json")
WATCH_TOPIC = os.environ.get(
    "GMAIL_WATCH_TOPIC", "projects/taskflow-support/topics/gmail-push"
)
SUPPORT_EMAIL = os.environ.get("GMAIL_SUPPORT_EMAIL", "support@techcorp.io")

# Track the last processed historyId to avoid reprocessing
_last_history_id: Optional[str] = None


# ── Authentication ───────────────────────────────────────────────────────


def get_gmail_service():
    """Authenticate and return a Gmail API service instance.

    Uses OAuth2 with stored credentials. On first run, opens a browser
    for authorization. Subsequent runs use the stored token.

    Returns:
        googleapiclient.discovery.Resource: Gmail API service
    """
    creds = None

    # Load existing token
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    # Refresh or create credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthRequest())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"Gmail credentials not found at {CREDENTIALS_PATH}. "
                    "Download from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for future runs
        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# ── Gmail Push Notifications (Pub/Sub) ───────────────────────────────────


async def setup_watch() -> dict:
    """Register Gmail push notifications via Google Cloud Pub/Sub.

    Watches the INBOX label for new messages. Must be re-registered
    every 7 days (Google's expiration policy). Use a cron job for renewal.

    Returns:
        dict with historyId and expiration timestamp.
    """
    service = get_gmail_service()

    request_body = {
        "labelIds": ["INBOX"],
        "topicName": WATCH_TOPIC,
        "labelFilterBehavior": "INCLUDE",
    }

    result = service.users().watch(userId="me", body=request_body).execute()
    logger.info(
        f"Gmail watch registered. historyId={result.get('historyId')}, "
        f"expiration={result.get('expiration')}"
    )

    global _last_history_id
    _last_history_id = result.get("historyId")

    return {
        "history_id": result.get("historyId"),
        "expiration": result.get("expiration"),
    }


async def stop_watch() -> None:
    """Unregister Gmail push notifications."""
    service = get_gmail_service()
    service.users().stop(userId="me").execute()
    logger.info("Gmail watch stopped.")


# ── Incoming Email Processing ────────────────────────────────────────────


async def process_notification(pubsub_message: dict) -> list[dict]:
    """Process a Gmail Pub/Sub push notification and fetch new messages.

    Called by the FastAPI Pub/Sub webhook endpoint when Gmail sends
    a notification about new inbox messages.

    Args:
        pubsub_message: Decoded Pub/Sub message with 'emailAddress' and 'historyId'

    Returns:
        List of normalized message dicts ready for agent processing.
    """
    global _last_history_id

    history_id = pubsub_message.get("historyId")
    email_address = pubsub_message.get("emailAddress")

    if not history_id:
        logger.warning("Pub/Sub notification missing historyId")
        return []

    logger.info(f"Processing Gmail notification: historyId={history_id}, email={email_address}")

    service = get_gmail_service()
    messages = []

    try:
        # Fetch message history since the last processed historyId
        start_history = _last_history_id or history_id
        history_response = (
            service.users()
            .history()
            .list(
                userId="me",
                startHistoryId=start_history,
                historyTypes=["messageAdded"],
                labelId="INBOX",
            )
            .execute()
        )

        # Update the last processed historyId
        _last_history_id = history_response.get("historyId", history_id)

        # Extract new message IDs from history
        message_ids = set()
        for history_record in history_response.get("history", []):
            for msg_added in history_record.get("messagesAdded", []):
                msg = msg_added.get("message", {})
                # Skip messages sent by us (from the support email)
                labels = msg.get("labelIds", [])
                if "SENT" not in labels:
                    message_ids.add(msg["id"])

        # Fetch full details for each new message
        for msg_id in message_ids:
            try:
                normalized = await _fetch_and_normalize_message(service, msg_id)
                if normalized:
                    messages.append(normalized)
            except Exception as e:
                logger.error(f"Failed to fetch message {msg_id}: {e}")

    except Exception as e:
        # historyId may be too old — fall back to listing recent messages
        if "404" in str(e) or "historyId" in str(e).lower():
            logger.warning(f"History expired, fetching recent INBOX messages: {e}")
            messages = await _fetch_recent_inbox(service, max_results=5)
        else:
            logger.error(f"Failed to process Gmail notification: {e}")
            raise

    logger.info(f"Processed {len(messages)} new email(s)")
    return messages


async def _fetch_and_normalize_message(service, message_id: str) -> Optional[dict]:
    """Fetch a single Gmail message and normalize it.

    Args:
        service: Gmail API service instance
        message_id: Gmail message ID

    Returns:
        Normalized message dict or None if message should be skipped.
    """
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )

    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}

    from_header = headers.get("from", "")
    subject = headers.get("subject", "")
    date_header = headers.get("date", "")
    message_id_header = headers.get("message-id", "")
    thread_id = msg.get("threadId", "")

    # Skip messages from ourselves
    customer_email = extract_email(from_header)
    if customer_email and customer_email.lower() == SUPPORT_EMAIL.lower():
        return None

    # Extract customer name
    customer_name = extract_name(from_header)

    # Extract body text
    body = _extract_body(msg.get("payload", {}))

    # Skip empty messages
    if not body or not body.strip():
        return None

    # Parse received timestamp
    received_at = datetime.now(timezone.utc).isoformat()
    if date_header:
        try:
            parsed = email.utils.parsedate_to_datetime(date_header)
            received_at = parsed.isoformat()
        except Exception:
            pass

    return {
        "channel": "email",
        "channel_message_id": message_id,
        "customer_email": customer_email or from_header,
        "customer_name": customer_name or "Customer",
        "subject": _clean_subject(subject),
        "content": body.strip(),
        "thread_id": thread_id,
        "received_at": received_at,
        "metadata": {
            "gmail_message_id": message_id,
            "gmail_thread_id": thread_id,
            "message_id_header": message_id_header,
            "labels": msg.get("labelIds", []),
            "from_raw": from_header,
        },
    }


async def _fetch_recent_inbox(service, max_results: int = 5) -> list[dict]:
    """Fallback: fetch recent unread INBOX messages when history is unavailable."""
    response = (
        service.users()
        .messages()
        .list(
            userId="me",
            labelIds=["INBOX", "UNREAD"],
            maxResults=max_results,
        )
        .execute()
    )

    messages = []
    for msg_stub in response.get("messages", []):
        try:
            normalized = await _fetch_and_normalize_message(service, msg_stub["id"])
            if normalized:
                messages.append(normalized)
        except Exception as e:
            logger.error(f"Failed to fetch message {msg_stub['id']}: {e}")

    return messages


# ── Outgoing Email ───────────────────────────────────────────────────────


async def send_reply(
    to_email: str,
    subject: str,
    body: str,
    thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
) -> dict:
    """Send an email reply via the Gmail API.

    Args:
        to_email: Recipient email address
        subject: Email subject (Re: prefix added automatically)
        body: Email body text (already formatted by formatters.py)
        thread_id: Gmail thread ID for proper threading
        in_reply_to: Message-ID header for threading

    Returns:
        dict with channel_message_id and delivery_status.
    """
    service = get_gmail_service()

    # Build MIME message
    message = MIMEMultipart("alternative")
    message["to"] = to_email
    message["from"] = SUPPORT_EMAIL

    # Add Re: prefix if replying and not already present
    if thread_id and not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    message["subject"] = subject

    # Thread headers for proper Gmail threading
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
        message["References"] = in_reply_to

    # Attach plain text body
    text_part = MIMEText(body, "plain", "utf-8")
    message.attach(text_part)

    # Also attach an HTML version with basic formatting
    html_body = _text_to_html(body)
    html_part = MIMEText(html_body, "html", "utf-8")
    message.attach(html_part)

    # Encode and send
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    send_body = {"raw": raw}
    if thread_id:
        send_body["threadId"] = thread_id

    try:
        sent = (
            service.users()
            .messages()
            .send(userId="me", body=send_body)
            .execute()
        )

        logger.info(f"Email sent to {to_email}, messageId={sent.get('id')}")

        return {
            "channel_message_id": sent.get("id"),
            "thread_id": sent.get("threadId"),
            "delivery_status": "sent",
        }

    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return {
            "channel_message_id": None,
            "thread_id": thread_id,
            "delivery_status": "failed",
            "error": str(e),
        }


# ── Helper Functions ─────────────────────────────────────────────────────


def extract_email(from_header: str) -> Optional[str]:
    """Extract email address from 'Name <email@domain.com>' format.

    Handles:
      - "Alice Smith <alice@example.com>" → "alice@example.com"
      - "alice@example.com" → "alice@example.com"
      - "<alice@example.com>" → "alice@example.com"
    """
    match = re.search(r"<([^>]+)>", from_header)
    if match:
        return match.group(1).strip()

    # Try bare email
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", from_header)
    if match:
        return match.group(0)

    return None


def extract_name(from_header: str) -> Optional[str]:
    """Extract display name from 'Name <email@domain.com>' format.

    Handles:
      - "Alice Smith <alice@example.com>" → "Alice Smith"
      - '"Alice Smith" <alice@example.com>' → "Alice Smith"
      - "alice@example.com" → None (use email as fallback)
    """
    # Strip quoted name
    match = re.match(r'^"?([^"<]+)"?\s*<', from_header)
    if match:
        name = match.group(1).strip()
        if name and not re.match(r"^[\w.+-]+@", name):
            return name

    return None


def _extract_body(payload: dict) -> str:
    """Extract plain text body from a Gmail message payload.

    Handles:
      - Simple text/plain messages
      - Multipart messages (text/plain preferred, falls back to text/html)
      - Nested multipart structures
    """
    mime_type = payload.get("mimeType", "")

    # Simple single-part message
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return _decode_base64(data)

    # Multipart: search for text/plain first, then text/html
    parts = payload.get("parts", [])
    plain_text = None
    html_text = None

    for part in parts:
        part_mime = part.get("mimeType", "")

        if part_mime == "text/plain":
            data = part.get("body", {}).get("data", "")
            plain_text = _decode_base64(data)
        elif part_mime == "text/html":
            data = part.get("body", {}).get("data", "")
            html_text = _decode_base64(data)
        elif part_mime.startswith("multipart/"):
            # Recurse into nested multipart
            nested = _extract_body(part)
            if nested:
                plain_text = plain_text or nested

    if plain_text:
        return plain_text

    # Fall back to HTML with tag stripping
    if html_text:
        return _strip_html(html_text)

    return ""


def _decode_base64(data: str) -> str:
    """Decode base64url-encoded string from Gmail API."""
    if not data:
        return ""
    # Gmail uses URL-safe base64 without padding
    padded = data + "=" * (4 - len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _strip_html(html: str) -> str:
    """Simple HTML tag stripping for fallback body extraction."""
    # Remove <style> and <script> blocks
    text = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Replace <br> and <p> with newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_subject(subject: str) -> str:
    """Remove excess Re:/Fwd: prefixes from email subject."""
    # Strip multiple Re:/Fwd: prefixes but keep one Re: if present
    cleaned = re.sub(r"^(Re:\s*|Fwd?:\s*)+", "", subject, flags=re.IGNORECASE).strip()
    return cleaned or "Support Request"


def _text_to_html(text: str) -> str:
    """Convert plain text to simple HTML for email clients that prefer HTML."""
    import html as html_module

    escaped = html_module.escape(text)
    # Convert newlines to <br>
    html_body = escaped.replace("\n", "<br>\n")
    # Bold markdown-style **text**
    html_body = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html_body)

    return f"""\
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; color: #333; line-height: 1.6;">
{html_body}
</body>
</html>"""
