# Screenshots Guide
## What to Capture and How

Place screenshot files in this folder (`FINAL-SUBMISSION/SCREENSHOTS/`).
Suggested filenames are listed below each instruction.

---

## Screenshot 1 — Local System Running

**What:** Docker containers for the database plus both application processes running.

**How:**
```bash
# Start everything (see DEPLOYMENT_GUIDE.md)
docker ps
```

**What the evaluator should see:**
- `fte-postgres` container with status `Up X minutes (healthy)`

**Suggested filename:** `01-docker-ps.png`

---

## Screenshot 2 — API Health Check

**What:** Terminal showing successful health check response from the running API.

**How:**
```bash
curl -s https://fte-api.onrender.com/health | python -m json.tool
# OR local:
curl -s http://localhost:8000/health | python -m json.tool
```

**What the evaluator should see:**
```json
{
    "status": "healthy",
    "timestamp": "..."
}
```

**Suggested filename:** `02-health-check.png`

---

## Screenshot 3 — Detailed Health Check

**What:** Terminal showing full system status including database and queue.

**How:**
```bash
curl -s https://fte-api.onrender.com/health/detailed | python -m json.tool
```

**What the evaluator should see:**
- `"database": {"status": "healthy"}`
- `"queue": {"status": "healthy", "pending_messages": 0}`
- All three channels listed

**Suggested filename:** `03-health-detailed.png`

---

## Screenshot 4 — Swagger UI API Documentation

**What:** Browser showing the Swagger UI at `/docs`.

**How:**
Open `https://fte-api.onrender.com/docs` in a browser.

**What the evaluator should see:**
- Full list of endpoints grouped by tag (health, webhooks, customers, metrics, etc.)
- The FastAPI title "Customer Success Digital FTE"

**Suggested filename:** `04-swagger-ui.png`

---

## Screenshot 5 — Ticket Created Successfully

**What:** Terminal showing a successful ticket submission response.

**How:**
```bash
curl -X POST https://fte-api.onrender.com/support/submit \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alice Johnson",
    "email": "alice@example.com",
    "subject": "Cannot access account",
    "message": "I have been locked out for two hours. This is urgent.",
    "category": "technical",
    "priority": "high",
    "plan": "pro"
  }' | python -m json.tool
```

**What the evaluator should see:**
- `"ticket_id": "TF-YYYYMMDD-XXXX"`
- `"estimated_response": "Within 4 hours (Pro plan SLA)"`

**Suggested filename:** `05-ticket-created.png`

---

## Screenshot 6 — Worker Processing a Message (Logs)

**What:** Terminal showing the worker consuming a message and running the agent.

**How:**
```bash
# In one terminal, watch the worker logs
python -m workers.message_processor

# In another terminal, inject a test message
curl -X POST "http://localhost:8000/test/queue?message=How+do+I+export+my+data?"
```

**What the evaluator should see:**
```
INFO: Poll: dequeued 1 message(s)
INFO: Processing: channel=whatsapp, customer=+923360840000
INFO: Message processed: ticket=TF-..., escalated=False, delivery=stored, total_ms=2840
```

**Suggested filename:** `06-worker-processing.png`

---

## Screenshot 7 — Escalation in Action

**What:** Worker logs showing a billing message being escalated.

**How:**
```bash
curl -X POST "http://localhost:8000/test/queue?message=I+was+charged+twice+this+month+and+want+a+refund"
```

**What the evaluator should see in worker logs:**
```
INFO: Message processed: ticket=TF-..., escalated=True, delivery=stored, total_ms=3120
```

**Suggested filename:** `07-escalation.png`

---

## Screenshot 8 — Database Tables

**What:** psql showing all 9 tables exist and the message_queue has processed messages.

**How:**
```bash
psql postgresql://fte:fte_secret@localhost:5432/fte_production

-- Show tables
\dt

-- Show recent queue activity
SELECT id, topic, processed, created_at, processed_at
FROM message_queue ORDER BY id DESC LIMIT 5;

-- Show tickets created
SELECT ref, subject, status FROM tickets ORDER BY created_at DESC LIMIT 5;
```

**Suggested filename:** `08-database-tables.png`

---

## Screenshot 9 — Channel Metrics

**What:** Terminal showing metrics output from the `/metrics/channels` endpoint.

**How:**
```bash
curl -s https://fte-api.onrender.com/metrics/channels | python -m json.tool
```

**Suggested filename:** `09-metrics.png`

---

## Screenshot 10 — GitHub Repository

**What:** Browser showing the GitHub repository with all four phase folders visible.

**How:**
Open `https://github.com/samreensaif/Hackathon-Five--The-CRM-Digital-FTE-Factory-`

**What the evaluator should see:**
- `1-Incubation-Phase/`
- `2-Transition-Phase/`
- `3-Specialization-Phase/`
- `4-Render-Deploy/`
- `FINAL-SUBMISSION/`
- Root `Dockerfile` and `requirements.txt`

**Suggested filename:** `10-github-repo.png`

---

## Screenshot 11 — Render.com Dashboard

**What:** Render dashboard showing all three services running.

**How:**
Log in to `https://dashboard.render.com` and navigate to the project.

**What the evaluator should see:**
- `fte-postgres` — database, green status
- `fte-api` — web service, green/live status
- `fte-worker` — background worker, running status

**Suggested filename:** `11-render-dashboard.png`

---

## Summary Checklist

- [ ] `01-docker-ps.png` — containers running
- [ ] `02-health-check.png` — API healthy
- [ ] `03-health-detailed.png` — DB + queue healthy
- [ ] `04-swagger-ui.png` — API documentation
- [ ] `05-ticket-created.png` — ticket submission response
- [ ] `06-worker-processing.png` — agent processing a message
- [ ] `07-escalation.png` — billing escalation triggered
- [ ] `08-database-tables.png` — all 9 tables + queue data
- [ ] `09-metrics.png` — channel metrics output
- [ ] `10-github-repo.png` — repository structure
- [ ] `11-render-dashboard.png` — cloud services running
