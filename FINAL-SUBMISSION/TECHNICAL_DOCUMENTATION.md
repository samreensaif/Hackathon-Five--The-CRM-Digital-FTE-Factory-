# Technical Documentation
## 24/7 AI Customer Support Agent — System Architecture

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         INBOUND CHANNELS                            │
├──────────────┬──────────────────────┬──────────────────────────────┤
│    Gmail     │      WhatsApp        │         Web Form             │
│  (Pub/Sub)   │  (Twilio Webhook)    │    (FastAPI POST)            │
└──────┬───────┴──────────┬───────────┴──────────────┬───────────────┘
       │                  │                           │
       ▼                  ▼                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      fte-api  (FastAPI)                             │
│                                                                     │
│  /webhooks/gmail        /webhooks/whatsapp     /support/submit      │
│  /webhooks/whatsapp/status                     /support/ticket/:id  │
│  /health   /health/detailed   /metrics/channels                     │
│  /conversations/:id   /customers/lookup   /test/queue               │
└────────────────────────────┬────────────────────────────────────────┘
                             │ publish_message()
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 PostgreSQL  (fte-postgres)                           │
│                                                                     │
│  message_queue        ← event bus (replaces Kafka on Render)        │
│  customers            ← canonical identity                          │
│  customer_identifiers ← cross-channel linking (email/phone/wa)      │
│  conversations        ← session state + sentiment tracking          │
│  messages             ← inbound + outbound message log              │
│  tickets              ← human-readable refs (TF-YYYYMMDD-XXXX)     │
│  knowledge_base       ← product docs with pgvector embeddings       │
│  channel_configs      ← per-channel settings and templates          │
│  agent_metrics        ← latency, escalation rate, sentiment         │
└────────────────────────────┬────────────────────────────────────────┘
                             │ consume_messages() every 2s
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   fte-worker  (Background)                          │
│                                                                     │
│  1. resolve_customer()       → get_or_create (email/phone)          │
│  2. get_or_create_conversation()                                    │
│  3. add_message()            → store inbound                        │
│  4. run_agent()              → GPT-4o + 6 tools                     │
│  5. _send_response()         → Gmail / Twilio / DB                  │
│  6. update_conversation_sentiment()                                 │
│  7. record_metric()          → latency, escalation, sentiment       │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    AI AGENT PIPELINE                                │
│                                                                     │
│  System Prompt (98% accuracy, Phase 1 validated)                    │
│                                                                     │
│  Tool 1: search_knowledge_base  → pgvector cosine similarity        │
│  Tool 2: create_ticket          → TF-YYYYMMDD-XXXX references       │
│  Tool 3: get_customer_history   → cross-channel interaction log     │
│  Tool 4: escalate_to_human      → routed by category/team member    │
│  Tool 5: send_response          → channel-formatted delivery        │
│  Tool 6: analyze_sentiment      → -1.0 to +1.0 scoring             │
│                                                                     │
│  Escalation routing:                                                │
│    billing   → Lisa Tanaka                                          │
│    legal     → Rachel Foster                                        │
│    security  → James Okafor                                         │
│    technical → Marcus Webb                                          │
│    general   → Support Queue                                        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Three-Phase Development

### Phase 1 — Incubation (`1-Incubation-Phase/`)

**Goal:** Prove the AI agent concept before building infrastructure.

- Crafted the system prompt through iterative refinement against real support scenarios
- Defined escalation rules: ALWAYS escalate (billing, legal, security, account deletion),
  LIKELY escalate (churn risk, angry customers, data loss, critical bugs)
- Built the sentiment analyzer: keyword dictionaries, negation detection, intensifier
  multipliers, ALL_CAPS amplification
- Implemented channel-specific formatting: email (formal), WhatsApp (<300 chars, approved
  emojis), web form (semi-formal with ticket ref)
- **Result: 98% accuracy on 62 test tickets** across all support categories

### Phase 2 — Transition (`2-Transition-Phase/`)

- Designed the full production database schema (9 tables, pgvector extension)
- Defined the Kafka event streaming topology (7 topics)
- Documented the channel integration patterns (OAuth2 Gmail, Twilio HMAC validation)
- Established the cross-channel customer identity resolution approach
- Created the migration plan from prototype to production

### Phase 3 — Specialization (`3-Specialization-Phase/production/`)

Full production implementation:
- FastAPI application with async lifecycle management
- Kafka producer/consumer pipeline (aiokafka)
- All three channel handlers with proper authentication
- Six agent tools backed by asyncpg database operations
- Metrics collection and alerting thresholds
- Docker + Kubernetes deployment configuration

### Cloud Edition (`4-Render-Deploy/`)

Render.com adaptation:
- Kafka replaced with PostgreSQL `message_queue` table
- `publish_message()` / `consume_messages()` with `FOR UPDATE SKIP LOCKED`
- Single-dependency infrastructure (PostgreSQL only)
- `render.yaml` blueprint with three managed services

---

## Component Breakdown

### API Layer (`api/main.py`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Liveness probe (Render health check) |
| `/health/detailed` | GET | DB + queue status, channel configs |
| `/webhooks/gmail` | POST | Google Pub/Sub push notifications |
| `/webhooks/whatsapp` | POST | Twilio webhook (HMAC validated) |
| `/webhooks/whatsapp/status` | POST | Delivery status tracking |
| `/support/submit` | POST | Web form ticket submission |
| `/support/ticket/{id}` | GET | Ticket status and history |
| `/metrics/channels` | GET | P50/P95 latency, escalation rate, sentiment |
| `/conversations/{id}` | GET | Full conversation history |
| `/customers/lookup` | GET | Customer lookup by email |
| `/test/queue` | POST | End-to-end pipeline test |

### Agent Tools (`agent/tools.py`)

| Tool | Input | Output | DB Operation |
|------|-------|--------|-------------|
| `search_knowledge_base` | query string | top-k articles | pgvector `<=>` cosine search |
| `create_ticket` | subject, category, priority | ticket ref | INSERT tickets |
| `get_customer_history` | customer_id | conversations, sentiment | JOIN across 4 tables |
| `escalate_to_human` | category, reason | team member, instructions | UPDATE tickets |
| `send_response` | text, channel | formatted message | channel-specific API call |
| `analyze_sentiment` | text | score (-1.0–1.0), label | in-memory keyword analysis |

### Channel Handlers (`channels/`)

**Gmail (`gmail_handler.py`):**
- OAuth2 with token auto-refresh
- Base64 Pub/Sub message decoding
- Plain text preferred, HTML fallback with tag stripping
- Reply threading with `In-Reply-To` / `References` headers
- `lastHistoryId` tracking to prevent reprocessing

**WhatsApp (`whatsapp_handler.py`):**
- HMAC-SHA1 Twilio signature validation (production only)
- Media message handling
- Message splitting at sentence boundaries (1600 char Twilio limit)
- Delivery status tracking (queued → sent → delivered → read)

**Web Form (`web_form_handler.py`):**
- Pydantic-validated submission model
- SLA estimate returned immediately based on customer plan
- Async ticket creation and DB storage
- Status polling endpoint

### Database Queue (`database/queue.py`)

```python
# Producer (API side)
await publish_message(pool, "fte.tickets.incoming", payload)

# Consumer (Worker side) — atomic, safe for concurrent workers
messages = await consume_messages(pool, "fte.tickets.incoming", batch_size=10)
# Uses: SELECT ... FOR UPDATE SKIP LOCKED
#       UPDATE message_queue SET processed = true ...
```

---

## Technology Choices and Rationale

| Decision | Choice | Why |
|----------|--------|-----|
| AI Framework | OpenAI Agents SDK | Native tool-calling, structured outputs, built-in retry |
| Model | GPT-4o | Best reasoning for support classification + multi-step tool use |
| Database driver | asyncpg | 3-5x faster than psycopg2 for async workloads |
| Vector search | pgvector | No extra service (Pinecone/Weaviate); colocated with operational data |
| Queue (cloud) | PostgreSQL table | Eliminates Kafka/Redis dependency; Render free tier compatible |
| API framework | FastAPI | Native async, automatic OpenAPI docs, Pydantic integration |
| Containerisation | Docker slim | Minimal attack surface, fast cold starts on Render |
| Cloud platform | Render.com | Blueprint YAML, managed Postgres, free tier for demo |

---

## Code Structure Overview

```
Hackathon-Five/
├── 1-Incubation-Phase/         Phase 1: agent prompt + accuracy testing
│   ├── context/product-docs.md     Knowledge base source
│   └── testing/                    62-ticket evaluation suite
│
├── 2-Transition-Phase/         Phase 2: architecture + design docs
│
├── 3-Specialization-Phase/     Phase 3: full Kafka production system
│   └── production/
│       ├── api/main.py             FastAPI app (562 lines)
│       ├── agent/                  GPT-4o agent + 6 tools (~1,300 lines)
│       ├── channels/               Gmail + WhatsApp + Web Form (~1,280 lines)
│       ├── database/               Schema + queries + migrations (~1,135 lines)
│       ├── workers/                Kafka consumer + metrics collector
│       ├── kafka_client.py         Producer/consumer infrastructure (1,247 lines)
│       └── k8s/                    Kubernetes deployment manifests
│
├── 4-Render-Deploy/            Cloud edition: Kafka → PostgreSQL queue
│   ├── api/main.py                 Kafka removed, publish_message() used
│   ├── agent/                      Identical to production (copied)
│   ├── channels/                   Identical to production (copied)
│   ├── database/
│   │   ├── schema.sql              9 tables including message_queue
│   │   ├── queries.py              Identical to production (copied)
│   │   ├── queue.py                PostgreSQL message queue (new)
│   │   └── init_db.py              One-command DB initialisation
│   ├── workers/message_processor.py  Polling loop, no Kafka
│   ├── Dockerfile
│   ├── requirements.txt            No aiokafka
│   └── render.yaml                 Blueprint: postgres + api + worker
│
└── FINAL-SUBMISSION/           This folder
```
