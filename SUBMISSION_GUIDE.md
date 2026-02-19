# Hackathon 5 — Submission Guide

Complete guide for evaluators to review, run, and score this project.

---

## Step 1: Verify Project Structure

```
Hackathon-Five/
├── 1-Incubation-Phase/               # Phase 1: Prototype
│   ├── src/agent/
│   │   ├── prototype.py              # Claude-powered prototype agent
│   │   └── mcp_server.py             # MCP server with 6 tools
│   ├── context/
│   │   ├── product-docs.md           # TaskFlow product documentation
│   │   ├── brand-voice.md            # Brand voice guidelines
│   │   └── escalation-rules.md       # Escalation routing table
│   ├── specs/
│   │   ├── discovery-log.md          # 5 exploration entries
│   │   ├── customer-success-fte-spec.md  # Full FTE specification
│   │   └── agent-skills.yaml         # 6-skill manifest
│   ├── tests/
│   │   └── sample-tickets.json       # 62 test tickets (98% accuracy)
│   └── templates/
│       ├── email-template.md
│       ├── whatsapp-template.md
│       └── webform-template.md
│
├── 2-Transition-to-Production/       # Phase 2: Documentation
│   └── documentation/
│       ├── extracted-prompts.md       # Working system prompts
│       ├── code-mapping.md           # Incubation → production mapping
│       ├── edge-cases.md             # 22 edge cases (10 resolved + 12 anticipated)
│       ├── performance-baseline.md   # Metrics and targets
│       └── transition-checklist.md   # All transition criteria verified
│
├── 3-Specialization-Phase/           # Phase 3: Production System
│   ├── production/
│   │   ├── agent/
│   │   │   ├── customer_success_agent.py  # Agent definition + run_agent()
│   │   │   ├── tools.py                   # 6 @function_tool implementations
│   │   │   ├── formatters.py              # Channel formatting + empathy matrix
│   │   │   └── prompts.py                 # System prompt + channel instructions
│   │   ├── api/
│   │   │   └── main.py               # FastAPI app, 8 endpoints, lifespan
│   │   ├── channels/
│   │   │   ├── gmail_handler.py       # Gmail API OAuth2 + Pub/Sub
│   │   │   ├── whatsapp_handler.py    # Twilio webhook + HMAC validation
│   │   │   └── web_form_handler.py    # FastAPI router + Pydantic v2
│   │   ├── database/
│   │   │   ├── schema.sql             # 8 tables, pgvector, 15+ indexes
│   │   │   ├── queries.py            # 12+ async functions (asyncpg)
│   │   │   ├── migrations/001_initial_schema.sql  # Idempotent migration
│   │   │   └── load_knowledge_base.py # Embedding generation + IVFFlat
│   │   ├── workers/
│   │   │   ├── message_processor.py   # 7-step unified pipeline
│   │   │   └── metrics_collector.py   # Metrics storage + alerting
│   │   ├── tests/
│   │   │   ├── conftest.py            # 6 shared fixtures
│   │   │   ├── test_agent.py          # 19 tests
│   │   │   ├── test_channels.py       # 14 tests
│   │   │   ├── test_e2e.py            # 9 tests
│   │   │   └── test_transition.py     # 12 tests
│   │   ├── k8s/                       # 11 Kubernetes manifests
│   │   │   ├── namespace.yaml
│   │   │   ├── configmap.yaml
│   │   │   ├── secrets.yaml
│   │   │   ├── deployment-api.yaml
│   │   │   ├── deployment-worker.yaml
│   │   │   ├── deployment-metrics.yaml
│   │   │   ├── service.yaml
│   │   │   ├── ingress.yaml
│   │   │   ├── hpa.yaml
│   │   │   ├── postgres.yaml
│   │   │   └── README.md
│   │   ├── kafka_client.py            # Producer/consumer, 7 topics, DLQ
│   │   ├── Dockerfile                 # python:3.11-slim + health check
│   │   ├── docker-compose.yml         # 6 services
│   │   ├── requirements.txt           # 14 dependencies
│   │   └── .env.example               # All env var placeholders
│   └── web-form/
│       ├── SupportForm.jsx            # React + Tailwind component
│       ├── index.html                 # Zero-build test page
│       └── README.md                  # Embedding guide
│
├── README.md                          # Project overview
├── DELIVERABLES.md                    # Complete deliverables checklist
└── SUBMISSION_GUIDE.md                # This file
```

**Quick verification command:**
```bash
# Count all files (excluding .git, node_modules, __pycache__)
find . -type f \
  ! -path './.git/*' \
  ! -path '*/__pycache__/*' \
  ! -path '*/node_modules/*' \
  | wc -l
# Expected: ~60+ files
```

---

## Step 2: Run the Tests

### Prerequisites
- Python 3.11+
- pip

### Setup
```bash
cd 3-Specialization-Phase/production

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-asyncio
```

### Run All Tests
```bash
pytest tests/ -v
```

### Expected Output
```
tests/test_agent.py::TestKnowledgeSearch::test_search_returns_results PASSED
tests/test_agent.py::TestKnowledgeSearch::test_search_no_results PASSED
tests/test_agent.py::TestKnowledgeSearch::test_search_db_unavailable PASSED
tests/test_agent.py::TestKnowledgeSearch::test_search_max_results PASSED
tests/test_agent.py::TestTicketCreation::test_create_email_ticket PASSED
tests/test_agent.py::TestTicketCreation::test_create_whatsapp_ticket PASSED
tests/test_agent.py::TestTicketCreation::test_create_webform_ticket PASSED
tests/test_agent.py::TestTicketCreation::test_invalid_channel PASSED
tests/test_agent.py::TestEscalation::test_billing_escalation PASSED
tests/test_agent.py::TestEscalation::test_legal_escalation PASSED
tests/test_agent.py::TestEscalation::test_urgent_escalation_response_time PASSED
tests/test_agent.py::TestEscalation::test_critical_escalation_includes_id PASSED
tests/test_agent.py::TestSentimentAnalysis::test_positive_sentiment PASSED
... (54+ tests total)

============================== 54 passed ==============================
```

### Run Specific Test Files
```bash
# Agent tools and formatters
pytest tests/test_agent.py -v

# Channel handlers (Gmail, WhatsApp, Web Form)
pytest tests/test_channels.py -v

# End-to-end customer journeys
pytest tests/test_e2e.py -v

# Incubation → production parity verification
pytest tests/test_transition.py -v
```

---

## Step 3: Run Locally with Docker

### Prerequisites
- Docker & Docker Compose
- OpenAI API key

### Steps
```bash
cd 3-Specialization-Phase/production

# 1. Create environment file
cp .env.example .env

# 2. Set your API key (minimum required)
#    Edit .env and set:
#    OPENAI_API_KEY=sk-your-key-here
#    POSTGRES_PASSWORD=your-secure-password

# 3. Start all services
docker compose up --build

# 4. Wait for health checks to pass (~30 seconds)
#    You should see:
#    fte-api-1     | INFO: Uvicorn running on http://0.0.0.0:8000
#    fte-worker-1  | INFO: Message processor started
#    fte-metrics-1 | INFO: Metrics collector started
```

### Verify Services
```bash
# Health check
curl http://localhost:8000/health
# → {"status": "healthy", "timestamp": "2025-..."}

# Detailed health (shows DB + Kafka status)
curl http://localhost:8000/health/detailed
# → {"status": "healthy", "database": "connected", "kafka": "connected", ...}

# Submit a test ticket
curl -X POST http://localhost:8000/support/submit \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test User",
    "email": "test@example.com",
    "subject": "Cannot reset my password",
    "category": "technical",
    "priority": "medium",
    "message": "I have been trying to reset my password for 30 minutes but the reset link never arrives. Please help!",
    "plan": "pro"
  }'
# → {"ticket_id": "TF-20250217-XXXX", "status": "received", "estimated_response_time": "within 4 hours"}
```

### Test the Web Form
Open `3-Specialization-Phase/web-form/index.html` in your browser. Fill out the form and submit. You'll see a success screen with the ticket ID.

### Stop Services
```bash
docker compose down        # Stop and remove containers
docker compose down -v     # Also remove volumes (database data)
```

---

## Step 4: Key Things to Demo

### 1. Multi-Channel Support
Show the three intake channels working:
- **Web Form**: Open `web-form/index.html`, submit a ticket
- **Gmail**: `POST /webhooks/gmail` with Pub/Sub notification payload
- **WhatsApp**: `POST /webhooks/whatsapp` with Twilio form data

All three produce the same internal message format and flow through the same 7-step pipeline.

### 2. Smart Escalation (98% Accuracy)
```bash
# Billing escalation
curl -X POST http://localhost:8000/support/submit \
  -H "Content-Type: application/json" \
  -d '{"name":"Jane","email":"jane@co.com","subject":"Refund request","category":"billing","priority":"high","message":"I want a full refund for last month. I was charged twice and nobody has responded to my previous requests.","plan":"pro"}'

# Legal escalation (mention of lawyer)
curl -X POST http://localhost:8000/support/submit \
  -H "Content-Type: application/json" \
  -d '{"name":"Bob","email":"bob@co.com","subject":"Legal matter","category":"general","priority":"urgent","message":"Your terms of service are misleading. I am going to contact my lawyer about this billing issue.","plan":"enterprise"}'
```

### 3. Cross-Channel Customer Recognition
Same customer contacting via email AND WhatsApp → resolved to single customer record via email/phone identity linking in `customer_identifiers` table.

Demonstrated in: `tests/test_e2e.py::TestCrossChannelJourney::test_customer_recognized_across_channels`

### 4. Sentiment-Driven Empathy
The agent detects customer frustration and adjusts tone:
- **Negative sentiment** (-1.0 to -0.3): Adds empathy phrases like "I understand your frustration"
- **Neutral** (-0.3 to 0.3): Standard professional tone
- **Positive** (0.3 to 1.0): Warm, appreciative tone

Demonstrated in: `tests/test_transition.py::test_angry_customer_gets_empathy`

### 5. Channel-Specific Formatting
- **Email**: Formal greeting ("Dear Alice"), full explanation, sign-off with ticket reference
- **WhatsApp**: Concise (< 280 chars), emoji-friendly, auto-split if > 1600 chars
- **Web Form**: Structured with ticket reference, bulleted steps, support team signature

Demonstrated in: `tests/test_agent.py::TestFormatters`

### 6. Production Infrastructure
- **Kubernetes**: 11 manifests with HPA (3-20 API pods, 3-30 worker pods), StatefulSet for Postgres
- **Kafka**: 7 topics for event streaming with Dead Letter Queue for failed messages
- **Docker Compose**: One-command local deployment of 6 services
- **Health checks**: Liveness + readiness probes for zero-downtime deployments

---

## Step 5: Answering Evaluator Questions

### Q: "How does the agent decide when to escalate?"
The agent uses a two-layer escalation system:

1. **Content-based rules** (in `agent/prompts.py`): The system prompt instructs the agent to ALWAYS escalate billing disputes, refund requests, legal threats, security vulnerabilities, and account deletion requests. These are hard rules — the agent cannot override them.

2. **Sentiment-based escalation** (in `agent/tools.py`): The `_analyze_sentiment_score()` function scores each message from -1.0 to +1.0 using keyword analysis. Scores below -0.5 trigger automatic escalation regardless of content.

The escalation tool (`escalate_to_human`) routes to the correct team (billing, legal, security, technical) with urgency-based SLAs (critical: 15 min, high: 1 hour, medium: 4 hours, low: 24 hours).

**Evidence**: 62 tickets tested during incubation with 98% accuracy (61/62 correct). The one miss was a borderline case subsequently addressed.

### Q: "How do you handle the same customer across channels?"
Cross-channel identity resolution uses a `customer_identifiers` table that links emails and phone numbers to a single `customer_id`:

1. When a message arrives, we look up the customer by email OR phone
2. If found, we return the existing customer record
3. If new, we create the customer and link their identifier
4. If they later contact from another channel, the same customer is resolved

This is implemented in `database/queries.py::get_or_create_customer()` and `link_customer_identifier()`.

### Q: "What happens if a message fails to process?"
Three-layer error handling:

1. **Retry**: The Kafka consumer automatically retries failed messages (configurable retry count)
2. **Dead Letter Queue**: After max retries, the message is published to `fte.dlq` topic with full error context (original message, error type, timestamp, retry count)
3. **Customer notification**: The `_handle_processing_error()` method in `message_processor.py` sends an apology to the customer with their ticket ID and a promise of follow-up

### Q: "How does the system scale?"
Kubernetes Horizontal Pod Autoscaler (HPA) manages scaling:

- **API pods**: 3 minimum → 20 maximum, scales at 70% CPU
- **Worker pods**: 3 minimum → 30 maximum, scales at 70% CPU
- **Kafka partitions**: Workers consume in parallel, one partition per consumer
- **PostgreSQL**: Connection pooling with asyncpg (min 2, max 10 connections per pod)

At peak load, the system can handle 30 concurrent message processors with 20 API servers.

### Q: "Why OpenAI Agents SDK instead of raw API calls?"
The OpenAI Agents SDK provides:

1. **Structured tool calling**: `@function_tool` decorators with Pydantic schemas for type-safe inputs
2. **Automatic conversation management**: The SDK handles message history, tool call results, and multi-turn conversations
3. **Built-in guardrails**: Input validation through Pydantic models before tools execute
4. **Composability**: Easy to add new tools or modify the agent's behavior without changing the orchestration logic

This mirrors the incubation phase (where Claude Code served as the AI backbone) but with production-grade reliability.

---

## Step 6: Files to Highlight for Each Scoring Criteria

### Incubation Quality (10 pts)
| File | Why |
|------|-----|
| `1-Incubation-Phase/specs/discovery-log.md` | 5 exploration entries showing iterative development |
| `1-Incubation-Phase/specs/customer-success-fte-spec.md` | Complete FTE specification |
| `1-Incubation-Phase/tests/sample-tickets.json` | 62 tickets tested, 98% accuracy |
| `1-Incubation-Phase/specs/agent-skills.yaml` | 6 skills defined for the agent |
| `1-Incubation-Phase/src/agent/prototype.py` | Working prototype code |

### Agent Implementation (10 pts)
| File | Why |
|------|-----|
| `3-Specialization-Phase/production/agent/customer_success_agent.py` | Agent definition with `run_agent()` entry point |
| `3-Specialization-Phase/production/agent/tools.py` | 6 `@function_tool` implementations with Pydantic schemas |
| `3-Specialization-Phase/production/agent/prompts.py` | System prompt + channel-specific instructions |
| `3-Specialization-Phase/production/agent/formatters.py` | Channel formatting + empathy matrix |

### Web Support Form (10 pts)
| File | Why |
|------|-----|
| `3-Specialization-Phase/web-form/SupportForm.jsx` | Full React + Tailwind component with validation |
| `3-Specialization-Phase/web-form/index.html` | Zero-build test page (open in browser) |
| `3-Specialization-Phase/production/channels/web_form_handler.py` | Server-side FastAPI router + Pydantic v2 |

### Channel Integrations (10 pts)
| File | Why |
|------|-----|
| `3-Specialization-Phase/production/channels/gmail_handler.py` | Gmail API OAuth2 + Pub/Sub push notifications |
| `3-Specialization-Phase/production/channels/whatsapp_handler.py` | Twilio HMAC-SHA1 validation + httpx sending |
| `3-Specialization-Phase/production/channels/web_form_handler.py` | FastAPI router with plan-based SLA |

### Database & Kafka (5 pts)
| File | Why |
|------|-----|
| `3-Specialization-Phase/production/database/schema.sql` | 8 tables, pgvector, 15+ indexes, 3 triggers |
| `3-Specialization-Phase/production/database/queries.py` | 12+ async functions with asyncpg |
| `3-Specialization-Phase/production/kafka_client.py` | 7 topics, DLQ, producer/consumer |
| `3-Specialization-Phase/production/database/load_knowledge_base.py` | Embedding generation + IVFFlat indexing |

### Kubernetes Deployment (5 pts)
| File | Why |
|------|-----|
| `3-Specialization-Phase/production/k8s/deployment-api.yaml` | 3 replicas, liveness/readiness probes |
| `3-Specialization-Phase/production/k8s/hpa.yaml` | Auto-scaling (3-20 API, 3-30 workers) |
| `3-Specialization-Phase/production/k8s/postgres.yaml` | StatefulSet with 20Gi PVC |
| `3-Specialization-Phase/production/k8s/README.md` | 10-step deployment guide |

### 24/7 Readiness (10 pts)
| File | Why |
|------|-----|
| `3-Specialization-Phase/production/k8s/hpa.yaml` | Auto-scaling for load spikes |
| `3-Specialization-Phase/production/k8s/deployment-api.yaml` | Health checks + rolling updates |
| `3-Specialization-Phase/production/workers/message_processor.py` | Graceful shutdown + signal handling |
| `3-Specialization-Phase/production/docker-compose.yml` | Health check dependencies between services |

### Cross-Channel Continuity (10 pts)
| File | Why |
|------|-----|
| `3-Specialization-Phase/production/database/queries.py` | `get_or_create_customer()` + `link_customer_identifier()` |
| `3-Specialization-Phase/production/database/schema.sql` | `customer_identifiers` table for identity linking |
| `3-Specialization-Phase/production/workers/message_processor.py` | Unified pipeline resolves customer across channels |
| `3-Specialization-Phase/production/tests/test_e2e.py` | `TestCrossChannelJourney` proves it works |

### Monitoring (5 pts)
| File | Why |
|------|-----|
| `3-Specialization-Phase/production/workers/metrics_collector.py` | P50/P95 latency, daily reports, alert thresholds |
| `3-Specialization-Phase/production/api/main.py` | `/metrics/channels` and `/health/detailed` endpoints |
| `3-Specialization-Phase/production/kafka_client.py` | `fte.metrics` topic for event streaming |

### Customer Experience (10 pts)
| File | Why |
|------|-----|
| `3-Specialization-Phase/production/agent/formatters.py` | EMPATHY_MATRIX: sentiment × channel → empathy phrase |
| `1-Incubation-Phase/context/brand-voice.md` | Brand voice guidelines |
| `3-Specialization-Phase/production/agent/prompts.py` | System prompt with empathy and tone instructions |
| `3-Specialization-Phase/production/tests/test_transition.py` | Tests for empathy and sentiment-driven responses |

### Documentation (5 pts)
| File | Why |
|------|-----|
| `2-Transition-to-Production/documentation/edge-cases.md` | 22 edge cases documented |
| `2-Transition-to-Production/documentation/extracted-prompts.md` | Working prompts captured |
| `README.md` | Full project overview with architecture diagram |
| `DELIVERABLES.md` | Complete deliverables checklist |

### Creative Solutions (5 pts)
| Feature | Where |
|---------|-------|
| Sentiment-driven empathy matrix | `agent/formatters.py` — EMPATHY_MATRIX maps (escalation, sentiment, channel) to empathy phrases |
| Dual-write reliability | `channels/web_form_handler.py` — writes to both Kafka and direct DB for resilience |
| Dead Letter Queue | `kafka_client.py` — failed events preserved with full error context |
| Sentence-boundary truncation | `agent/formatters.py` — WhatsApp messages split at sentence boundaries, not mid-word |

### Evolution Demonstration (5 pts)
| Phase | Evidence |
|-------|----------|
| Phase 1 → 2 | `2-Transition-to-Production/documentation/code-mapping.md` maps prototype concepts to production architecture |
| Phase 2 → 3 | `3-Specialization-Phase/production/tests/test_transition.py` — 12 tests proving production matches incubation behavior |
| Full arc | `DELIVERABLES.md` — complete inventory across all three phases |

---

## Final Project Statistics

| Metric | Count |
|--------|-------|
| **Total files created** | 59 real-content files + 13 placeholder/init files |
| **Total lines of code** | ~17,300 lines |
| **Total test cases** | 54+ (19 agent + 14 channel + 9 E2E + 12 transition) |
| **Phases completed** | 3 of 3 |
| **Channels supported** | 3 (Gmail, WhatsApp, Web Form) |
| **Agent tools** | 6 (@function_tool with Pydantic schemas) |
| **Database tables** | 8 (with pgvector + 15 indexes + 3 triggers) |
| **Kafka topics** | 7 (including Dead Letter Queue) |
| **Kubernetes manifests** | 11 files |
| **Docker services** | 6 (postgres, zookeeper, kafka, api, worker, metrics) |
| **Edge cases documented** | 22 (10 resolved + 12 anticipated) |
| **Sample tickets tested** | 62 (98% escalation accuracy) |
| **Escalation accuracy** | 98% (61/62 correct) |
| **Self-assessed score** | 89/100 |

---

## One-Line Summary

> A production-grade AI customer support agent that handles Gmail, WhatsApp, and Web Form inquiries 24/7 with 98% escalation accuracy, sentiment-driven empathy, cross-channel customer recognition, and auto-scaling Kubernetes deployment — built across three phases from prototype to production in ~17,300 lines of code.
