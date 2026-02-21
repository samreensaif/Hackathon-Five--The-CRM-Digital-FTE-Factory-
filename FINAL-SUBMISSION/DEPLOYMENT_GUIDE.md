# Deployment Guide
## 24/7 AI Customer Support Agent

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | https://python.org |
| Docker | 24+ | https://docker.com |
| PostgreSQL | 15+ with pgvector | via Docker (see below) |
| Git | any | https://git-scm.com |

API keys required:
- **OpenAI API key** (GPT-4o access)
- **Twilio Account SID + Auth Token** (WhatsApp — optional for local)
- **Google OAuth credentials** (Gmail — optional for local)

---

## Option A — Local Setup (4-Render-Deploy version)

### Step 1: Clone and Install

```bash
git clone https://github.com/samreensaif/Hackathon-Five--The-CRM-Digital-FTE-Factory-.git
cd Hackathon-Five/4-Render-Deploy
pip install -r requirements.txt
```

### Step 2: Start PostgreSQL with pgvector

```bash
docker run -d \
  --name fte-postgres \
  -e POSTGRES_USER=fte \
  -e POSTGRES_PASSWORD=fte_secret \
  -e POSTGRES_DB=fte_production \
  -p 5432:5432 \
  pgvector/pgvector:pg16

# Verify it's running
docker ps | grep fte-postgres
```

### Step 3: Configure Environment

```bash
# Create .env file
cat > .env << 'EOF'
DATABASE_URL=postgresql://fte:fte_secret@localhost:5432/fte_production
OPENAI_API_KEY=sk-your-key-here
ENVIRONMENT=development
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000

# Optional — WhatsApp
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_NUMBER=

# Optional — Gmail
GMAIL_SUPPORT_EMAIL=
GMAIL_CREDENTIALS_PATH=./credentials/gmail_credentials.json
GMAIL_TOKEN_PATH=./credentials/gmail_token.json
EOF
```

### Step 4: Initialise the Database

```bash
python database/init_db.py
```

Expected output:
```
Connecting to PostgreSQL at localhost/fte_production ...
Connected.
Enabling pgvector extension ...
  pgvector: OK
Applying schema.sql ...
  schema.sql: executed successfully
Verifying tables ...
  agent_metrics: OK
  channel_configs: OK
  conversations: OK
  customer_identifiers: OK
  customers: OK
  knowledge_base: OK
  message_queue: OK
  messages: OK
  tickets: OK

Database initialised successfully — 9 tables ready.
```

### Step 5: Load the Knowledge Base

```bash
export DATABASE_URL="postgresql://fte:fte_secret@localhost:5432/fte_production"
export OPENAI_API_KEY="sk-your-key-here"
python database/load_knowledge_base.py \
  --docs ../1-Incubation-Phase/context/product-docs.md
```

### Step 6: Start the API Server

```bash
# Terminal 1
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

You should see:
```
INFO: Starting Customer Success Digital FTE API (Render edition)...
INFO: PostgreSQL pool connected
INFO: API startup complete
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8000
```

### Step 7: Start the Worker

```bash
# Terminal 2
python -m workers.message_processor
```

You should see:
```
INFO: PostgreSQL pool connected
INFO: Message processor started successfully
INFO: Message processor running — polling every 2.0s on topic='fte.tickets.incoming'
```

### Step 8: Verify Everything Works

```bash
# Health check
curl http://localhost:8000/health
# {"status":"healthy","timestamp":"..."}

# Detailed health (shows DB + queue status)
curl http://localhost:8000/health/detailed

# Submit a test ticket through the web form channel
curl -X POST http://localhost:8000/support/submit \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alice Johnson",
    "email": "alice@example.com",
    "subject": "Cannot access my account",
    "message": "I have been trying to log in for the past hour and keep getting an error. I need this resolved urgently.",
    "category": "technical",
    "priority": "high",
    "plan": "pro"
  }'

# Trigger a test message through the queue directly
curl -X POST "http://localhost:8000/test/queue?message=Hello+I+need+help+with+billing"

# Browse API docs
open http://localhost:8000/docs
```

---

## Option B — Full Docker Compose (Local)

```bash
cd 4-Render-Deploy

# Build the image
docker build -t fte-render .

# Run API
docker run -d \
  --name fte-api \
  --link fte-postgres:postgres \
  -e DATABASE_URL=postgresql://fte:fte_secret@postgres:5432/fte_production \
  -e OPENAI_API_KEY=sk-your-key \
  -p 8000:8000 \
  fte-render

# Run Worker
docker run -d \
  --name fte-worker \
  --link fte-postgres:postgres \
  -e DATABASE_URL=postgresql://fte:fte_secret@postgres:5432/fte_production \
  -e OPENAI_API_KEY=sk-your-key \
  fte-render \
  python -m workers.message_processor

# Verify both containers running
docker ps
```

---

## Option C — Render.com Cloud Deployment

### Step 1: Fork / Push the Repository

Ensure the repository is on GitHub (already done):
`https://github.com/samreensaif/Hackathon-Five--The-CRM-Digital-FTE-Factory-`

### Step 2: Create Blueprint on Render

1. Go to [dashboard.render.com](https://dashboard.render.com)
2. Click **New** → **Blueprint**
3. Connect GitHub → select the repository
4. Render detects `4-Render-Deploy/render.yaml`
5. Click **Apply** — Render creates:
   - `fte-postgres` (managed PostgreSQL)
   - `fte-api` (web service on port 8000)
   - `fte-worker` (background worker)

### Step 3: Set Secret Environment Variables

In Render Dashboard → each service → **Environment**:

| Service | Variable | Value |
|---------|----------|-------|
| fte-api + fte-worker | `OPENAI_API_KEY` | `sk-...` |
| fte-api + fte-worker | `TWILIO_ACCOUNT_SID` | From Twilio |
| fte-api + fte-worker | `TWILIO_AUTH_TOKEN` | From Twilio |
| fte-api + fte-worker | `TWILIO_WHATSAPP_NUMBER` | `whatsapp:+1...` |
| fte-api + fte-worker | `TWILIO_WEBHOOK_URL` | `https://fte-api.onrender.com/webhooks/whatsapp` |
| fte-api + fte-worker | `GMAIL_SUPPORT_EMAIL` | `support@yourcompany.com` |

`DATABASE_URL` is injected automatically via `fromDatabase: connectionString`.

### Step 4: Initialise the Database

After the first successful deploy:

1. Render Dashboard → `fte-api` → **Shell** tab
2. Run:
```bash
python database/init_db.py
```

### Step 5: Verify Cloud Deployment

```bash
# Health check
curl https://fte-api.onrender.com/health

# Detailed health
curl https://fte-api.onrender.com/health/detailed

# Submit test ticket
curl -X POST https://fte-api.onrender.com/support/submit \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","email":"test@example.com","subject":"Test","message":"This is a test","category":"general","priority":"low","plan":"free"}'
```

---

## Endpoints Reference

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /health` | None | Liveness (Render health check) |
| `GET /health/detailed` | None | Full system status |
| `GET /docs` | None | Swagger UI — interactive API explorer |
| `POST /support/submit` | None | Submit web form ticket |
| `GET /support/ticket/{ref}` | None | Get ticket status |
| `POST /webhooks/gmail` | Pub/Sub | Gmail inbound (Google Cloud) |
| `POST /webhooks/whatsapp` | HMAC | WhatsApp inbound (Twilio) |
| `GET /metrics/channels` | None | Channel metrics (24h window) |
| `GET /conversations/{id}` | None | Conversation history |
| `GET /customers/lookup?email=` | None | Customer lookup |
| `POST /test/queue` | None | End-to-end pipeline test |
