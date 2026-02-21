# Live Demo Guide
## API Endpoints — Active on Render.com

---

## Live API Base URL

```
https://fte-api.onrender.com
```

> **Cold Start Notice:** The Render.com free tier spins down services after 15 minutes
> of inactivity. The first request after a dormant period may take 30–60 seconds.
> This is a hosting tier limitation, not an application issue. All subsequent requests
> respond immediately.

---

## Endpoint 1 — Health Check

**Purpose:** Confirms the API is running.

```bash
curl https://fte-api.onrender.com/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-02-21T10:00:00.000000+00:00"
}
```

---

## Endpoint 2 — Detailed Health Check

**Purpose:** Shows database connectivity, queue depth, and channel configuration.

```bash
curl https://fte-api.onrender.com/health/detailed
```

**Expected response:**
```json
{
  "status": "healthy",
  "checks": {
    "database": {
      "status": "healthy"
    },
    "queue": {
      "status": "healthy",
      "pending_messages": 0
    },
    "channels": {
      "email": {"enabled": true},
      "whatsapp": {"enabled": true},
      "web_form": {"enabled": true}
    }
  }
}
```

---

## Endpoint 3 — Interactive API Documentation

**Purpose:** Full Swagger UI — browse all endpoints, view schemas, try requests in-browser.

**URL:** `https://fte-api.onrender.com/docs`

Open this URL in a web browser. You will see the complete API explorer with:
- All 11 endpoints organised by tag
- Request/response schemas
- Try-it-out functionality for every endpoint
- Example request bodies

---

## Endpoint 4 — Submit a Support Ticket

**Purpose:** Tests the complete web form → queue → agent → response pipeline.

```bash
curl -X POST https://fte-api.onrender.com/support/submit \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alice Johnson",
    "email": "alice.johnson@example.com",
    "subject": "Cannot export my project data",
    "message": "I have been trying to export my project data for the last two days but the export button is greyed out. I need this data for a client report due tomorrow.",
    "category": "technical",
    "priority": "high",
    "plan": "pro"
  }'
```

**Expected response:**
```json
{
  "ticket_id": "TF-20250221-0001",
  "status": "received",
  "message": "Your support request has been received and is being processed.",
  "estimated_response": "Within 4 hours (Pro plan SLA)"
}
```

---

## Endpoint 5 — Pipeline Test (Bypass Webhook)

**Purpose:** Directly injects a message into the queue, bypassing the webhook layer.
The worker will consume it within 2 seconds and run the full agent pipeline.

```bash
# General query
curl -X POST "https://fte-api.onrender.com/test/queue?message=How+do+I+set+up+task+automation?"

# Billing query (should trigger escalation)
curl -X POST "https://fte-api.onrender.com/test/queue?message=I+was+charged+twice+this+month"

# Security concern (always escalates)
curl -X POST "https://fte-api.onrender.com/test/queue?message=I+think+my+account+was+compromised"
```

**Expected response:**
```json
{
  "status": "published",
  "queue": "message_queue",
  "topic": "fte.tickets.incoming",
  "message_id": 42,
  "channel_message_id": "test-a1b2c3d4"
}
```

---

## Endpoint 6 — Channel Metrics

**Purpose:** Shows aggregated performance metrics for the last 24 hours.

```bash
# All channels, last 24 hours
curl "https://fte-api.onrender.com/metrics/channels?hours=24"

# Web form only
curl "https://fte-api.onrender.com/metrics/channels?channel=web_form"
```

**Expected response:**
```json
{
  "window_hours": 24,
  "channels": {
    "email": {
      "latency": {"count": 0, "p50": null, "p95": null, "avg": null},
      "escalation_rate": {"count": 0, "avg": null},
      "sentiment": {"count": 0, "avg": null}
    },
    "whatsapp": {...},
    "web_form": {
      "latency": {"count": 3, "p50": 2840, "p95": 4120, "avg": 3200},
      "escalation_rate": {"count": 3, "avg": 0.33},
      "sentiment": {"count": 3, "avg": -0.12}
    }
  },
  "generated_at": "2025-02-21T10:00:00Z"
}
```

---

## Note on Worker Free Tier

The `fte-worker` background service is running on Render.com's free tier. When the worker
is active, messages submitted via `/test/queue` or `/support/submit` are processed
within 2 seconds and results are stored in the database.

On the free tier, the worker may also spin down during periods of inactivity. If the
worker is dormant, messages will accumulate in the `message_queue` table and be processed
when the worker restarts — no messages are lost, because the queue is persistent in
PostgreSQL.

**To verify the worker is running:**
```bash
# Queue depth should return to 0 after a few seconds if worker is active
curl https://fte-api.onrender.com/health/detailed | python -m json.tool
```

---

## GitHub Repository

All source code, commit history, and documentation:

`https://github.com/samreensaif/Hackathon-Five--The-CRM-Digital-FTE-Factory-`

The repository contains all three development phases plus the cloud deployment:
- `1-Incubation-Phase/` — Agent development and 62-ticket evaluation
- `2-Transition-Phase/` — Architecture and design documentation
- `3-Specialization-Phase/` — Full production Kafka-based implementation
- `4-Render-Deploy/` — Cloud-ready PostgreSQL queue version (this deployment)
- `FINAL-SUBMISSION/` — This documentation package
