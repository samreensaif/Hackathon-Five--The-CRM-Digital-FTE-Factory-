# Customer Success Digital FTE — Render.com Deployment

Cloud-ready version of the production Customer Success agent, with Kafka
replaced by a PostgreSQL-based message queue for one-click Render.com deployment.

## What Changed from Production

| Component | Production (`3-Specialization-Phase/`) | This folder (`4-Render-Deploy/`) |
|-----------|---------------------------------------|----------------------------------|
| Message broker | Apache Kafka (aiokafka) | PostgreSQL `message_queue` table |
| API publish | `kafka_producer.publish()` | `publish_message()` from `database/queue.py` |
| Worker consume | `FTEKafkaConsumer` loop | `consume_messages()` polled every 2s |
| Metrics publish | Kafka `fte.metrics` topic | Direct `record_metric()` to DB |
| Infrastructure | Zookeeper + Kafka + Postgres | Postgres only |

Everything else is identical: the AI agent, all tools, channel handlers (Gmail,
WhatsApp, Web Form), and the database schema.

---

## Architecture

```
Webhook (Gmail / WhatsApp / Web Form)
        │
        ▼
  ┌─────────────┐    INSERT INTO      ┌─────────────────┐
  │  fte-api    │ ─── message_queue ──▶  fte-postgres   │
  │  (FastAPI)  │                     │  (PostgreSQL)   │
  └─────────────┘                     └────────┬────────┘
                                               │
                                    SELECT FOR UPDATE SKIP LOCKED
                                               │
                                               ▼
                                      ┌─────────────────┐
                                      │  fte-worker     │
                                      │  (polls every   │
                                      │   2 seconds)    │
                                      └────────┬────────┘
                                               │
                                    run_agent() → send_response()
                                               │
                                    Gmail API / Twilio / DB
```

---

## Deployment Steps

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "Initial Render.com deployment"
git remote add origin https://github.com/YOUR_ORG/fte-render.git
git push -u origin main
```

### 2. Create Render Services

**Option A — Blueprint (recommended):**
1. Go to [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint**
2. Connect your GitHub repo
3. Render detects `render.yaml` and creates all three services automatically

**Option B — Manual:**
1. Create a **PostgreSQL** database named `fte-postgres`
2. Create a **Web Service** (Docker) for the API pointing to this repo
3. Create a **Background Worker** (Docker) for the worker, overriding CMD:
   `python -m workers.message_processor`

### 3. Set Secret Environment Variables

In the Render dashboard, set these for **both** `fte-api` and `fte-worker`:

| Variable | Value |
|----------|-------|
| `OPENAI_API_KEY` | Your OpenAI API key |
| `TWILIO_ACCOUNT_SID` | From Twilio console |
| `TWILIO_AUTH_TOKEN` | From Twilio console |
| `TWILIO_WHATSAPP_NUMBER` | `whatsapp:+1...` |
| `TWILIO_WEBHOOK_URL` | `https://fte-api.onrender.com/webhooks/whatsapp` |
| `GMAIL_SUPPORT_EMAIL` | `support@yourcompany.com` |

For Gmail credentials, upload `gmail_credentials.json` and `gmail_token.json`
as **Secret Files** at `/etc/secrets/gmail_credentials.json` and
`/etc/secrets/gmail_token.json`.

### 4. Initialize the Database

After the first deploy, open the **Render Shell** for `fte-api`
(Dashboard → fte-api → Shell) and run:

```bash
python database/init_db.py
```

Expected output:

```
Connecting to PostgreSQL at <host>/<db> ...
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
Connection closed.
```

The script is safe to re-run at any time — every statement in schema.sql
uses `IF NOT EXISTS` so existing data is never affected.

**Alternative (psql from local machine):**
```bash
# Get DATABASE_URL from Render Dashboard → fte-postgres → Connection
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql "$DATABASE_URL" < 4-Render-Deploy/database/schema.sql
```

### 5. Load the Knowledge Base (optional)

```bash
pip install -r requirements.txt
export DATABASE_URL="postgresql://..."
export OPENAI_API_KEY="sk-..."
python database/load_knowledge_base.py --docs ../1-Incubation-Phase/context/product-docs.md
```

### 6. Verify

```bash
curl https://fte-api.onrender.com/health
# {"status":"healthy","timestamp":"..."}

curl https://fte-api.onrender.com/health/detailed
# {"status":"healthy","checks":{"database":{"status":"healthy"},"queue":{"status":"healthy","pending_messages":0},...}}
```

---

## Local Development

```bash
# Clone and install
pip install -r requirements.txt
cp .env.example .env   # fill in your secrets

# Start a local PostgreSQL (Docker)
docker run -d --name fte-pg \
  -e POSTGRES_USER=fte \
  -e POSTGRES_PASSWORD=fte_secret \
  -e POSTGRES_DB=fte_production \
  -p 5432:5432 \
  pgvector/pgvector:pg16

# Apply schema
psql postgresql://fte:fte_secret@localhost:5432/fte_production < database/schema.sql

# Run API
uvicorn api.main:app --reload

# Run worker (separate terminal)
python -m workers.message_processor
```

---

## Testing the Queue

Use the built-in test endpoint to verify the full pipeline:

```bash
curl -X POST "https://fte-api.onrender.com/test/queue?message=Hello+from+render"
# {"status":"published","queue":"message_queue","topic":"fte.tickets.incoming","message_id":1,...}
```

The worker will pick this up within 2 seconds and process it through the agent.

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `ENVIRONMENT` | No | `development` | Set to `production` to enable Twilio signature validation |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Comma-separated allowed origins |
| `POLL_INTERVAL_SECONDS` | No | `2` | Worker polling interval in seconds |
| `TWILIO_ACCOUNT_SID` | WhatsApp | — | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | WhatsApp | — | Twilio auth token |
| `TWILIO_WHATSAPP_NUMBER` | WhatsApp | — | WhatsApp sender number |
| `TWILIO_WEBHOOK_URL` | WhatsApp | — | Full webhook URL for signature validation |
| `GMAIL_CREDENTIALS_PATH` | Gmail | — | Path to `gmail_credentials.json` |
| `GMAIL_TOKEN_PATH` | Gmail | — | Path to `gmail_token.json` |
| `GMAIL_SUPPORT_EMAIL` | Gmail | — | Support email address |

---

## Migrating Back to Kafka

This deployment uses the same logical topic names as the Kafka version:
- `fte.tickets.incoming`
- `fte.channels.email.inbound`
- `fte.channels.whatsapp.inbound`

To migrate back, replace `publish_message()` calls in `api/main.py` with
`producer.publish()`, and replace the polling loop in `workers/message_processor.py`
with the `FTEKafkaConsumer` from the production folder.
