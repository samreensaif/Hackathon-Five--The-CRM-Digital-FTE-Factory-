# Code Mapping: Incubation to Production

**Purpose:** Map every incubation-phase component to its production-grade counterpart in Phase 3 (Specialization). This document serves as the implementation blueprint for the production build.

---

## Component Mapping Table

### Core Agent Components

| Incubation Component | Class/Function | Production Component | Technology | Status |
|---------------------|---------------|---------------------|------------|--------|
| `1-Incubation-Phase/src/agent/prototype.py` | `CustomerSuccessAgent` | `3-Specialization-Phase/production/agent/customer_success_agent.py` | OpenAI Agents SDK `Agent` class | Pending |
| `prototype.py` | `KnowledgeBase` (TF-IDF) | `production/agent/knowledge_base.py` | FAISS/Chroma vector store + OpenAI embeddings | Pending |
| `prototype.py` | `SentimentAnalyzer` (keyword) | `production/agent/sentiment.py` | LLM-based sentiment (Claude/GPT function call) | Pending |
| `prototype.py` | `EscalationEngine` (regex) | `production/agent/escalation.py` + system prompt rules | Hybrid: regex pre-filter + LLM judgment | Pending |
| `prototype.py` | `IntentDetector` (keyword) | Removed — LLM handles intent naturally | OpenAI Agents SDK built-in | Pending |
| `prototype.py` | `ResponseFormatter` (templates) | `production/agent/formatters.py` | LLM generation with channel-specific system prompts | Pending |
| `1-Incubation-Phase/src/agent/conversation_manager.py` | `ConversationManager` | `production/services/conversation_service.py` | PostgreSQL + SQLAlchemy ORM | Pending |
| `1-Incubation-Phase/src/agent/mcp_server.py` | 6 MCP tools | `production/agent/tools.py` | OpenAI Agents SDK `@function_tool` decorators | Pending |

### Data & Storage

| Incubation Component | Storage Method | Production Component | Technology | Notes |
|---------------------|---------------|---------------------|------------|-------|
| `ConversationManager._conversations` | In-memory `dict` | `conversations` table | PostgreSQL | UUID primary key, indexed by customer_id |
| `ConversationManager._customer_index` | In-memory `dict` | `customers` table | PostgreSQL | Email as primary key, with indexes |
| `ConversationManager._identity_links` | In-memory `dict` | `identity_links` table | PostgreSQL | Bidirectional email ↔ phone mapping |
| `ConversationManager.messages[]` | In-memory `list` in dataclass | `messages` table | PostgreSQL | Foreign key to conversations, indexed by timestamp |
| `ConversationManager.sentiment_history[]` | In-memory `list` in dataclass | `sentiment_history` column (JSONB) | PostgreSQL | Or separate `sentiment_entries` table |
| `KnowledgeBase.sections[]` | In-memory parsed from markdown | `doc_sections` table + vector index | PostgreSQL + pgvector (or FAISS) | Embeddings stored as vectors |
| Product docs, escalation rules, brand voice | Markdown files in `context/` | `agent_config` table or config files | PostgreSQL or mounted ConfigMap | Version-controlled, hot-reloadable |

### Channel Integrations

| Incubation Component | Method | Production Component | Technology | Notes |
|---------------------|--------|---------------------|------------|-------|
| `Ticket` dataclass (JSON input) | Parsed from `sample-tickets.json` | `production/channels/gmail_handler.py` | Gmail API (OAuth 2.0) | Webhook for new emails |
| `Ticket` dataclass (JSON input) | Parsed from `sample-tickets.json` | `production/channels/whatsapp_handler.py` | WhatsApp Business API | Webhook for incoming messages |
| `Ticket` dataclass (JSON input) | Parsed from `sample-tickets.json` | `production/channels/webform_handler.py` | FastAPI POST endpoint | React form → API |
| `ResponseFormatter._format_email()` | Python string templates | Gmail API `messages.send()` | Gmail API | Formatted HTML/plain text |
| `ResponseFormatter._format_whatsapp()` | Python string templates | WhatsApp Business API `messages` endpoint | WhatsApp Cloud API | Max 300 chars enforced |
| `ResponseFormatter._format_webform()` | Python string templates | FastAPI JSON response + email notification | FastAPI + SendGrid/SES | Ticket ID in response |

### Testing

| Incubation Component | Method | Production Component | Technology | Notes |
|---------------------|--------|---------------------|------------|-------|
| `tests/test_conversation_flow.py` | 61 manual assertion tests | `tests/unit/` | pytest + pytest-asyncio | Automated in CI/CD |
| `prototype.py --all` (62 tickets) | CLI script against JSON | `tests/integration/test_escalation.py` | pytest against test DB | Seeded with 62 tickets |
| Manual MCP tool testing | Direct function calls | `tests/integration/test_tools.py` | pytest with mocked LLM | Tool input/output validation |
| Manual WhatsApp truncation testing | Inline in test suite | `tests/unit/test_formatters.py` | pytest parametrized | Edge cases for truncation |
| No load testing | N/A | `tests/load/` | Locust or k6 | Concurrent ticket processing |
| No end-to-end | N/A | `tests/e2e/` | Playwright + API tests | Full channel → response flow |

---

## Detailed Conversion Guides

### 1. MCP Tools → OpenAI Agents SDK `@function_tool`

Each MCP tool converts to an OpenAI Agents SDK function tool:

```python
# INCUBATION (MCP Server — mcp_server.py)
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("TaskFlow Customer Success FTE")

@mcp.tool()
def search_knowledge_base(query: str, max_results: int = 5) -> str:
    """Search TaskFlow product documentation using TF-IDF relevance scoring."""
    results = _kb.search(query, top_k=max_results)
    ...

# PRODUCTION (OpenAI Agents SDK — tools.py)
from agents import function_tool

@function_tool
async def search_knowledge_base(query: str, max_results: int = 5) -> str:
    """Search TaskFlow product documentation for relevant answers.

    Use this tool when a customer asks about TaskFlow features, needs
    troubleshooting steps, or asks about integrations and pricing.

    Args:
        query: Search query using the customer's own words
        max_results: Number of doc sections to return (1-10, default 5)
    """
    results = await knowledge_service.search(query, top_k=max_results)
    ...
```

**Full tool mapping:**

| MCP Tool | SDK Function Tool | Key Changes |
|----------|-------------------|-------------|
| `search_knowledge_base` | `search_knowledge_base` | Async, uses vector store instead of TF-IDF |
| `create_ticket` | `create_ticket` | Async, writes to PostgreSQL, triggers conversation service |
| `get_customer_history` | `get_customer_history` | Async, queries PostgreSQL with joins |
| `escalate_to_human` | `escalate_to_human` | Async, sends real notification (email/Slack), writes to DB |
| `send_response` | `send_response` | Async, calls real channel APIs (Gmail/WhatsApp/webhook) |
| `analyze_sentiment` | `analyze_sentiment` | Uses LLM instead of keyword analysis, returns richer data |

### 2. Regex Escalation Rules → System Prompt + Hybrid Engine

The incubation escalation engine has ~60 regex patterns across 12 categories. In production, these are split into two layers:

**Layer 1: Fast regex pre-filter (keep from incubation)**
```python
# production/agent/escalation.py
class EscalationPreFilter:
    """Fast regex check that runs BEFORE the LLM.
    Catches obvious cases with zero LLM cost."""

    ALWAYS_ESCALATE = {
        "billing": [r'\brefund\b', r'\bmoney\s*back\b', ...],
        "legal": [r'\bgdpr\b', r'\blawyer\b', ...],
        "security": [r'\bdata\s*breach\b', ...],
        "account": [r'\b(workspace|account)\s*deletion\b', ...],
    }
    # If ANY pattern matches → escalate immediately, skip LLM
```

**Layer 2: LLM judgment for LIKELY_ESCALATE (new in production)**
```
# Embedded in system prompt (see extracted-prompts.md)
For the following categories, use your judgment to decide if escalation
is needed based on the full context of the message:
- Churn risk: customer mentions competitors or cancellation
- Data loss: customer reports lost work or missing data
- Enterprise critical: enterprise customer + severity + affects team
- etc.
```

**Why hybrid:** The regex pre-filter catches 100% of ALWAYS_ESCALATE cases (billing, legal, security, account) with zero LLM tokens. The LLM handles nuanced LIKELY_ESCALATE cases that regex can't (like TF-0015 where "unusable" and "affects all users" are far apart).

### 3. In-Memory State → PostgreSQL Schema

```sql
-- conversations table
CREATE TABLE conversations (
    conversation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id VARCHAR(255) NOT NULL REFERENCES customers(email),
    channel VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, resolved, escalated
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolution_status VARCHAR(50),
    escalation_id VARCHAR(50),
    escalation_reason TEXT,
    topics_discussed TEXT[] DEFAULT '{}',
    channels_used TEXT[] DEFAULT ARRAY[channel],
    customer_plan VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_conversations_customer ON conversations(customer_id);
CREATE INDEX idx_conversations_status ON conversations(status);

-- messages table
CREATE TABLE messages (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(conversation_id),
    role VARCHAR(20) NOT NULL,  -- customer, agent
    content TEXT NOT NULL,
    channel VARCHAR(20) NOT NULL,
    sentiment FLOAT,
    intent VARCHAR(50),
    ticket_id VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_created ON messages(created_at);

-- customers table
CREATE TABLE customers (
    email VARCHAR(255) PRIMARY KEY,
    display_name VARCHAR(255),
    plan VARCHAR(20) DEFAULT 'free',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_contact_at TIMESTAMPTZ
);

-- identity_links table (for cross-channel resolution)
CREATE TABLE identity_links (
    primary_email VARCHAR(255) NOT NULL REFERENCES customers(email),
    alt_identifier VARCHAR(255) NOT NULL,
    identifier_type VARCHAR(20) NOT NULL,  -- phone, secondary_email
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (primary_email, alt_identifier)
);
CREATE INDEX idx_identity_alt ON identity_links(alt_identifier);

-- doc_sections table (for vector search)
CREATE TABLE doc_sections (
    section_id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    body TEXT NOT NULL,
    full_text TEXT NOT NULL,
    embedding vector(1536),  -- OpenAI ada-002 dimension
    source_file VARCHAR(255),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_doc_embedding ON doc_sections USING ivfflat (embedding vector_cosine_ops);
```

**Migration path from in-memory:**

| In-Memory Structure | PostgreSQL Table | Migration Notes |
|---------------------|-----------------|-----------------|
| `_conversations[conv_id]` → `Conversation` | `conversations` row | Flatten dataclass fields into columns. `messages[]` moves to separate table. `sentiment_history[]` can be JSONB column or computed from messages table. |
| `_customer_index[email]` → `[conv_ids]` | `conversations` table (query by customer_id) | No separate index table needed — use SQL WHERE clause |
| `_identity_links[id]` → `email` | `identity_links` table | Bidirectional mapping preserved via two rows (email→phone, phone→email) |
| `KnowledgeBase.sections[]` | `doc_sections` table | Replace word counts with vector embeddings. Title boost becomes metadata filter. |

### 4. Testing Strategy Changes

| Aspect | Incubation | Production |
|--------|-----------|------------|
| **Test runner** | `python prototype.py --all` + `python test_conversation_flow.py` | `pytest` with markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.e2e` |
| **Test data** | `sample-tickets.json` (62 tickets) | Same 62 tickets seeded into test DB + synthetic data for load tests |
| **Escalation accuracy** | Calculated inline with `pass`/`fail` counters | `tests/integration/test_escalation.py` — parametrized test per ticket ID |
| **Conversation tests** | Direct function calls with assertions | `tests/integration/test_conversations.py` — uses test DB, cleans up after each test |
| **MCP tool tests** | Direct function calls in test_conversation_flow.py | `tests/integration/test_tools.py` — mocked LLM, real DB |
| **Channel formatting** | Inline assertions in test suite | `tests/unit/test_formatters.py` — parametrized: (input, channel, expected_output) |
| **Regression** | Manual re-run of `--all` | CI/CD pipeline runs full suite on every PR |
| **Load testing** | None | `tests/load/locustfile.py` — simulate 200 tickets/hour across 3 channels |
| **Monitoring** | None | Prometheus metrics: response_time, escalation_rate, confidence_distribution |

---

## Architecture Comparison

### Incubation Architecture

```
┌──────────────────────────────────────────────────┐
│  CLI / Test Script                                │
│  (python prototype.py --all)                      │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│  CustomerSuccessAgent (single Python process)     │
│  ├── SentimentAnalyzer (keyword)                  │
│  ├── IntentDetector (keyword)                     │
│  ├── EscalationEngine (regex)                     │
│  ├── KnowledgeBase (TF-IDF, in-memory)            │
│  └── ResponseFormatter (templates)                │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│  ConversationManager (in-memory dicts)            │
└──────────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│  MCP Server (FastMCP, stdio/SSE)                  │
│  6 tools, 4 resources                             │
└──────────────────────────────────────────────────┘
```

### Production Architecture (Phase 3)

```
┌─────────────────────────────────────────────────────────────┐
│  Channel Ingress                                             │
│  ├── Gmail Webhook → gmail_handler.py                        │
│  ├── WhatsApp Webhook → whatsapp_handler.py                  │
│  └── Web Form POST → webform_handler.py                      │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  FastAPI Application Server                                  │
│  ├── POST /api/tickets       → create ticket                 │
│  ├── GET  /api/customers/:id → customer history              │
│  ├── POST /api/escalate      → manual escalation             │
│  └── WebSocket /ws/agent     → real-time agent interaction   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  OpenAI Agents SDK — Customer Success Agent                  │
│  ├── System prompt (from extracted-prompts.md)               │
│  ├── @function_tool search_knowledge_base                    │
│  ├── @function_tool create_ticket                            │
│  ├── @function_tool get_customer_history                     │
│  ├── @function_tool escalate_to_human                        │
│  ├── @function_tool send_response                            │
│  └── @function_tool analyze_sentiment                        │
│  + EscalationPreFilter (regex, runs before LLM)              │
└──────────┬──────────────────────────────────┬───────────────┘
           │                                  │
┌──────────▼──────────┐            ┌──────────▼──────────────┐
│  PostgreSQL          │            │  Vector Store            │
│  ├── conversations   │            │  (pgvector or FAISS)     │
│  ├── messages        │            │  ├── doc_sections        │
│  ├── customers       │            │  └── embeddings index    │
│  └── identity_links  │            └─────────────────────────┘
└─────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────┐
│  Observability Stack                                         │
│  ├── Prometheus (metrics: latency, escalation rate, etc.)    │
│  ├── Grafana (dashboards)                                    │
│  └── Structured logging (JSON, correlation IDs)              │
└─────────────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────┐
│  Kubernetes Deployment                                       │
│  ├── FastAPI pods (auto-scaling)                             │
│  ├── PostgreSQL (managed, e.g., Cloud SQL / RDS)             │
│  ├── Redis (optional: caching, rate limiting)                │
│  └── Ingress (HTTPS, rate limiting)                          │
└─────────────────────────────────────────────────────────────┘
```
