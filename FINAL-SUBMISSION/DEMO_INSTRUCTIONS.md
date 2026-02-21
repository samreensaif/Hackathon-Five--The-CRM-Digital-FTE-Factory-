# Demo Instructions
## How to Evaluate the 24/7 AI Customer Support Agent

---

## Quick 5-Minute Demo (Cloud — No Setup Required)

The API is live at `https://fte-api.onrender.com`.

> **Note on free tier:** The Render free tier spins down after 15 minutes of inactivity.
> The first request may take 30–60 seconds for cold start. Subsequent requests are instant.

### Test 1 — Health Check
```bash
curl https://fte-api.onrender.com/health
```
**Expected:**
```json
{"status": "healthy", "timestamp": "2025-02-21T10:00:00Z"}
```

### Test 2 — System Status
```bash
curl https://fte-api.onrender.com/health/detailed
```
**Expected:**
```json
{
  "status": "healthy",
  "checks": {
    "database": {"status": "healthy"},
    "queue": {"status": "healthy", "pending_messages": 0},
    "channels": {"email": {"enabled": true}, "whatsapp": {"enabled": true}, "web_form": {"enabled": true}}
  }
}
```

### Test 3 — Browse the API Documentation
Open in a browser: `https://fte-api.onrender.com/docs`

This shows the full Swagger UI with all endpoints, schemas, and try-it-out buttons.

### Test 4 — Submit a Support Ticket (Web Form Channel)
```bash
curl -X POST https://fte-api.onrender.com/support/submit \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alice Johnson",
    "email": "alice@example.com",
    "subject": "Cannot access my account",
    "message": "I have been locked out of my account for the past hour. I keep getting an authentication error. I need this resolved urgently for a client presentation.",
    "category": "technical",
    "priority": "high",
    "plan": "pro"
  }'
```
**Expected:**
```json
{
  "ticket_id": "TF-20250221-XXXX",
  "status": "received",
  "message": "Your support request has been received.",
  "estimated_response": "Within 4 hours (Pro plan SLA)"
}
```

### Test 5 — Trigger Full Pipeline Test
```bash
curl -X POST "https://fte-api.onrender.com/test/queue?message=I+need+help+with+billing"
```
**Expected:**
```json
{
  "status": "published",
  "queue": "message_queue",
  "topic": "fte.tickets.incoming",
  "message_id": 1,
  "channel_message_id": "test-abc12345"
}
```
The worker picks this up within 2 seconds, runs the AI agent, and stores the response in the database.

### Test 6 — Channel Metrics
```bash
curl "https://fte-api.onrender.com/metrics/channels?hours=24"
```
**Expected:**
```json
{
  "window_hours": 24,
  "channels": {
    "email": {"latency": {...}, "escalation_rate": {...}, "sentiment": {...}},
    "whatsapp": {...},
    "web_form": {...}
  }
}
```

---

## Full Local Demo (With Agent Processing)

### Prerequisites
- Docker running
- OpenAI API key

### Start Everything
```bash
# Terminal 1: PostgreSQL
docker run -d --name fte-pg \
  -e POSTGRES_USER=fte -e POSTGRES_PASSWORD=fte_secret \
  -e POSTGRES_DB=fte_production -p 5432:5432 \
  pgvector/pgvector:pg16

# Terminal 2: API
cd 4-Render-Deploy
DATABASE_URL=postgresql://fte:fte_secret@localhost:5432/fte_production \
OPENAI_API_KEY=sk-your-key \
uvicorn api.main:app --port 8000

# Terminal 3: Worker
cd 4-Render-Deploy
DATABASE_URL=postgresql://fte:fte_secret@localhost:5432/fte_production \
OPENAI_API_KEY=sk-your-key \
python -m workers.message_processor
```

### Demo Scenario A — General Technical Query
```bash
curl -X POST http://localhost:8000/test/queue \
  -G --data-urlencode "message=How do I set up task automation in TaskFlow?"
```
**Watch the worker logs:**
```
INFO: Poll: dequeued 1 message(s)
INFO: Processing: channel=whatsapp, customer=+923360840000
INFO: Message processed: ticket=TF-..., escalated=False, delivery=stored, total_ms=2840
```

### Demo Scenario B — Billing Escalation (Should Always Escalate)
```bash
curl -X POST http://localhost:8000/test/queue \
  -G --data-urlencode "message=I was charged twice this month and I need a refund immediately"
```
**Watch the worker logs — should escalate:**
```
INFO: Message processed: ticket=TF-..., escalated=True, delivery=stored, total_ms=3120
```

### Demo Scenario C — Security Issue (Always Escalates)
```bash
curl -X POST http://localhost:8000/test/queue \
  -G --data-urlencode "message=I think my account has been hacked. Someone changed my password."
```

### Demo Scenario D — Happy Customer (High Sentiment)
```bash
curl -X POST http://localhost:8000/test/queue \
  -G --data-urlencode "message=TaskFlow is amazing! I just wanted to say thank you for the great product."
```

---

## Demo Scenario Results — What to Expect

| Message Type | Escalates? | Routed To | Response Tone |
|-------------|-----------|-----------|---------------|
| Technical question | No | — | Helpful, solution-focused |
| Billing complaint | Yes | Lisa Tanaka | Empathetic, urgent |
| Legal/GDPR request | Yes | Rachel Foster | Formal, measured |
| Security concern | Yes | James Okafor | Urgent, reassuring |
| Angry customer | Yes (likely) | Support Queue | Highly empathetic |
| Feature question | No | — | Informative, encouraging |
| Account lockout | Yes (likely) | Support Queue | Empathetic, step-by-step |

---

## Testing the Web Form Channel End-to-End

```bash
# Step 1: Submit ticket
TICKET=$(curl -s -X POST http://localhost:8000/support/submit \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bob Smith",
    "email": "bob@company.com",
    "subject": "API rate limit question",
    "message": "What are the API rate limits for the Enterprise plan?",
    "category": "technical",
    "priority": "medium",
    "plan": "enterprise"
  }' | python -c "import sys,json; print(json.load(sys.stdin)['ticket_id'])")

echo "Created ticket: $TICKET"

# Step 2: Wait 5 seconds for agent to process
sleep 5

# Step 3: Check ticket status
curl "http://localhost:8000/support/ticket/$TICKET"
```

---

## Verifying the Database Directly

```bash
# Connect to the database
psql postgresql://fte:fte_secret@localhost:5432/fte_production

-- Check tables exist
\dt

-- See processed messages
SELECT id, topic, processed, created_at, processed_at
FROM message_queue
ORDER BY id DESC
LIMIT 10;

-- See tickets created
SELECT ref, subject, category, status, created_at
FROM tickets
ORDER BY created_at DESC
LIMIT 10;

-- See customers resolved
SELECT name, email, plan, total_conversations
FROM customers
ORDER BY created_at DESC
LIMIT 10;

-- See agent metrics
SELECT metric_name, metric_value, channel, recorded_at
FROM agent_metrics
ORDER BY recorded_at DESC
LIMIT 20;
```

---

## What the Evaluator Should Look For

1. **Speed:** Agent responses generated in 2–5 seconds end-to-end
2. **Accuracy:** Billing/legal/security always escalate; general questions handled autonomously
3. **Channel awareness:** Responses formatted differently per channel (WhatsApp < 300 chars)
4. **Customer identity resolution:** Same customer recognised across email and web form
5. **Conversation continuity:** Follow-up messages in same conversation, not new tickets
6. **Sentiment adaptation:** Empathy matrix adjusts tone based on sentiment score
7. **Ticket references:** Human-readable TF-YYYYMMDD-XXXX format in every response
8. **Metrics recording:** Every processed message records latency, escalation, sentiment
