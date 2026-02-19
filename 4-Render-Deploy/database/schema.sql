-- ============================================================================
-- Customer Success Digital FTE — Production Database Schema
-- ============================================================================
-- PostgreSQL 15+ required (for gen_random_uuid, JSONB, array types)
-- Extensions: uuid-ossp, pgvector
--
-- Tables:
--   1. customers           — Customer profiles (email as canonical ID)
--   2. customer_identifiers — Cross-channel identity linking (email, phone, etc.)
--   3. conversations       — Per-customer conversation sessions with state machine
--   4. messages            — Individual messages within conversations
--   5. tickets             — Support tickets linked to conversations
--   6. knowledge_base      — Product documentation with vector embeddings
--   7. channel_configs     — Per-channel settings (API keys, templates, limits)
--   8. agent_metrics       — Observability metrics for monitoring & alerting
--
-- Designed from: 2-Transition-to-Production/specs/code-mapping.md
-- Migrates from: 1-Incubation-Phase/src/agent/conversation_manager.py (in-memory)
-- ============================================================================

-- ── Extensions ──────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";  -- pgvector for semantic search

-- ── 1. Customers ────────────────────────────────────────────────────────────
-- Stores customer profiles. Email is the canonical identifier (from incubation).
-- Phone is stored separately for WhatsApp channel resolution.
-- Maps from: ConversationManager._customer_index (in-memory dict)

CREATE TABLE IF NOT EXISTS customers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email               VARCHAR(255) UNIQUE,          -- canonical ID (nullable for phone-only)
    phone               VARCHAR(50),                  -- WhatsApp phone number
    name                VARCHAR(255),                 -- display name for greetings
    plan                VARCHAR(20) DEFAULT 'free'
                        CHECK (plan IN ('free', 'pro', 'enterprise')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_contact_at     TIMESTAMPTZ,                  -- updated on every new message
    total_conversations INTEGER NOT NULL DEFAULT 0,   -- denormalized counter
    metadata            JSONB DEFAULT '{}'::jsonb      -- extensible fields (company, role, etc.)
);

COMMENT ON TABLE customers IS 'Customer profiles with email as canonical identifier. Migrated from ConversationManager._customer_index.';
COMMENT ON COLUMN customers.email IS 'Primary identifier — used by Gmail and Web Form channels.';
COMMENT ON COLUMN customers.phone IS 'WhatsApp phone number in E.164 format (e.g., +15551234567).';
COMMENT ON COLUMN customers.plan IS 'Subscription tier. Determines SLA: enterprise=1hr, pro=4hr, free=24hr.';

-- ── 2. Customer Identifiers ────────────────────────────────────────────────
-- Cross-channel identity linking. A customer may have multiple identifiers
-- (email, phone, secondary email). This enables resolving any identifier
-- to the canonical customer record.
-- Maps from: ConversationManager._identity_links (in-memory dict)

CREATE TABLE IF NOT EXISTS customer_identifiers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id         UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    identifier_type     VARCHAR(20) NOT NULL
                        CHECK (identifier_type IN ('email', 'phone', 'whatsapp')),
    identifier_value    VARCHAR(255) NOT NULL,         -- the actual email/phone value
    verified            BOOLEAN NOT NULL DEFAULT false, -- whether identity was verified
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (identifier_type, identifier_value)          -- one value per type
);

COMMENT ON TABLE customer_identifiers IS 'Cross-channel identity linking. Resolves email/phone/whatsapp ID to canonical customer. Migrated from ConversationManager._identity_links.';

-- ── 3. Conversations ────────────────────────────────────────────────────────
-- Per-customer conversation sessions. State machine: active → resolved | escalated.
-- Escalated conversations are reused for follow-up messages (from incubation learning).
-- Maps from: ConversationManager._conversations (in-memory dict of Conversation dataclass)

CREATE TABLE IF NOT EXISTS conversations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id         UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    initial_channel     VARCHAR(20) NOT NULL
                        CHECK (initial_channel IN ('email', 'whatsapp', 'web_form')),
    current_channel     VARCHAR(20)
                        CHECK (current_channel IN ('email', 'whatsapp', 'web_form')),
    channels_used       TEXT[] NOT NULL DEFAULT '{}',  -- tracks all channels used
    status              VARCHAR(20) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'resolved', 'escalated')),
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at            TIMESTAMPTZ,                   -- set when resolved/closed

    -- Sentiment tracking (migrated from Conversation.sentiment_history[])
    sentiment_score     DECIMAL(4,2),                  -- latest sentiment (-1.00 to 1.00)
    sentiment_trend     VARCHAR(20) DEFAULT 'stable'
                        CHECK (sentiment_trend IN ('improving', 'stable', 'declining', 'unknown')),

    -- Topic tracking (migrated from Conversation.topics_discussed[])
    topics              TEXT[] DEFAULT '{}',

    -- Escalation fields
    escalation_reason   TEXT,
    escalated_to        VARCHAR(255),                  -- team member name
    escalated_to_email  VARCHAR(255),                  -- team member email
    escalation_id       VARCHAR(50),                   -- external escalation reference

    -- Resolution
    resolution_notes    TEXT,

    -- Extensible
    metadata            JSONB DEFAULT '{}'::jsonb
);

COMMENT ON TABLE conversations IS 'Per-customer conversation sessions with state machine (active/resolved/escalated). Escalated conversations are reused for follow-ups.';
COMMENT ON COLUMN conversations.channels_used IS 'Array of all channels used in this conversation. Enables cross-channel context detection.';
COMMENT ON COLUMN conversations.sentiment_trend IS 'Computed from message sentiment history. "declining" triggers auto-escalation after 3+ negative messages.';

-- ── 4. Messages ─────────────────────────────────────────────────────────────
-- Individual messages within a conversation. Both customer and agent messages.
-- Maps from: Conversation.messages[] (in-memory list of Message dataclass)

CREATE TABLE IF NOT EXISTS messages (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    channel             VARCHAR(20) NOT NULL
                        CHECK (channel IN ('email', 'whatsapp', 'web_form')),
    direction           VARCHAR(10) NOT NULL
                        CHECK (direction IN ('inbound', 'outbound')),
    role                VARCHAR(10) NOT NULL
                        CHECK (role IN ('customer', 'agent', 'system')),
    content             TEXT NOT NULL,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Analysis fields (populated by agent pipeline)
    sentiment_score     DECIMAL(4,2),                  -- -1.00 to 1.00 (null for agent msgs)
    intent              VARCHAR(50),                   -- detected intent (null for agent msgs)

    -- Performance tracking
    tokens_used         INTEGER,                       -- LLM tokens consumed (null for customer)
    latency_ms          INTEGER,                       -- response generation time in ms

    -- Tool usage (for agent messages)
    tool_calls          JSONB,                         -- array of {tool, args, result} objects

    -- Channel-specific
    channel_message_id  VARCHAR(255),                  -- Gmail message ID / WhatsApp message ID
    delivery_status     VARCHAR(20) DEFAULT 'pending'
                        CHECK (delivery_status IN ('pending', 'sent', 'delivered', 'failed', 'read'))
);

COMMENT ON TABLE messages IS 'Individual messages within conversations. Stores both customer (inbound) and agent (outbound) messages.';
COMMENT ON COLUMN messages.channel_message_id IS 'External message ID from the channel API (Gmail, WhatsApp). Used for deduplication and delivery tracking.';
COMMENT ON COLUMN messages.tool_calls IS 'JSON array of tool calls made by the agent for this response. E.g., [{tool: "search_knowledge_base", args: {query: "..."}, result: "..."}]';

-- ── 5. Tickets ──────────────────────────────────────────────────────────────
-- Support tickets linked to conversations. A conversation may have multiple
-- tickets if it spans multiple issues (future: multi-issue decomposition).

CREATE TABLE IF NOT EXISTS tickets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_ref          VARCHAR(50) NOT NULL UNIQUE,   -- human-readable: TF-YYYYMMDD-XXXX
    conversation_id     UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    customer_id         UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    source_channel      VARCHAR(20) NOT NULL
                        CHECK (source_channel IN ('email', 'whatsapp', 'web_form')),
    subject             VARCHAR(500),
    category            VARCHAR(50),                   -- billing, technical, how-to, etc.
    priority            VARCHAR(10) NOT NULL DEFAULT 'medium'
                        CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    status              VARCHAR(20) NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'in_progress', 'resolved', 'escalated', 'closed')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ,
    resolution_notes    TEXT,
    assigned_to         VARCHAR(255),                  -- human agent name (if escalated)
    assigned_to_email   VARCHAR(255)
);

COMMENT ON TABLE tickets IS 'Support tickets linked to conversations. ticket_ref is the human-readable ID shown to customers (TF-YYYYMMDD-XXXX).';

-- ── 6. Knowledge Base ───────────────────────────────────────────────────────
-- Product documentation with vector embeddings for semantic search.
-- Replaces: KnowledgeBase class (TF-IDF, in-memory) from prototype.py
-- Loaded by: load_knowledge_base.py

CREATE TABLE IF NOT EXISTS knowledge_base (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title               VARCHAR(500) NOT NULL,         -- section heading from product-docs.md
    content             TEXT NOT NULL,                  -- section body text
    category            VARCHAR(100),                  -- top-level category (getting_started, etc.)
    embedding           vector(1536),                  -- OpenAI text-embedding-3-small dimension
    source              VARCHAR(255),                  -- source file and section reference
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata            JSONB DEFAULT '{}'::jsonb       -- word_count, parent_section, etc.
);

COMMENT ON TABLE knowledge_base IS 'Product documentation sections with vector embeddings. Replaces TF-IDF KnowledgeBase from incubation. Loaded from product-docs.md.';
COMMENT ON COLUMN knowledge_base.embedding IS 'OpenAI text-embedding-3-small vector (1536 dimensions). Used for cosine similarity search.';

-- ── 7. Channel Configs ──────────────────────────────────────────────────────
-- Per-channel configuration including API credentials, templates, and limits.

CREATE TABLE IF NOT EXISTS channel_configs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel             VARCHAR(20) NOT NULL UNIQUE
                        CHECK (channel IN ('email', 'whatsapp', 'web_form')),
    enabled             BOOLEAN NOT NULL DEFAULT true,
    config              JSONB NOT NULL DEFAULT '{}'::jsonb,  -- API keys, webhook URLs (encrypted at rest)
    response_template   TEXT,                          -- channel-specific response template
    max_response_length INTEGER NOT NULL DEFAULT 1000, -- character limit for responses
    tone                VARCHAR(20) DEFAULT 'professional',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE channel_configs IS 'Per-channel settings. API credentials should be encrypted or stored in a secret manager — the config JSONB is for non-sensitive settings in development.';

-- ── 8. Agent Metrics ────────────────────────────────────────────────────────
-- Observability metrics for monitoring dashboards and alerting.
-- See: performance-baseline.md for metric definitions and alert thresholds.

CREATE TABLE IF NOT EXISTS agent_metrics (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_name         VARCHAR(100) NOT NULL,         -- e.g., 'escalation_rate', 'response_latency'
    metric_value        DECIMAL(12,4) NOT NULL,
    channel             VARCHAR(20),                   -- nullable: metric may be global
    dimensions          JSONB DEFAULT '{}'::jsonb,      -- extra dimensions (category, plan, etc.)
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE agent_metrics IS 'Observability metrics. Query with time-series aggregations for Grafana dashboards.';

-- ── Indexes ─────────────────────────────────────────────────────────────────
-- Performance-critical indexes based on expected query patterns.

-- Customers: lookup by email (most common) and phone (WhatsApp resolution)
CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone) WHERE phone IS NOT NULL;

-- Customer identifiers: resolve any identifier to customer
CREATE INDEX IF NOT EXISTS idx_cust_ident_value ON customer_identifiers(identifier_value);
CREATE INDEX IF NOT EXISTS idx_cust_ident_customer ON customer_identifiers(customer_id);

-- Conversations: find active conversations for a customer (the hot path)
CREATE INDEX IF NOT EXISTS idx_conv_customer_status ON conversations(customer_id, status);
CREATE INDEX IF NOT EXISTS idx_conv_status ON conversations(status);
CREATE INDEX IF NOT EXISTS idx_conv_last_message ON conversations(last_message_at DESC);

-- Messages: load conversation history (ordered by time)
CREATE INDEX IF NOT EXISTS idx_msg_conversation_created ON messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_msg_channel_id ON messages(channel_message_id) WHERE channel_message_id IS NOT NULL;

-- Tickets: dashboard queries (filter by status + priority)
CREATE INDEX IF NOT EXISTS idx_tickets_status_priority ON tickets(status, priority);
CREATE INDEX IF NOT EXISTS idx_tickets_customer ON tickets(customer_id);
CREATE INDEX IF NOT EXISTS idx_tickets_conversation ON tickets(conversation_id);
CREATE INDEX IF NOT EXISTS idx_tickets_ref ON tickets(ticket_ref);

-- Knowledge base: vector similarity search (IVFFlat for approximate nearest neighbor)
-- NOTE: IVFFlat requires the table to have data before creating the index.
-- Run this AFTER load_knowledge_base.py populates the table:
--   CREATE INDEX idx_kb_embedding ON knowledge_base
--     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);
-- For small datasets (< 1000 rows), exact search without index is fine.

-- Agent metrics: time-series queries
CREATE INDEX IF NOT EXISTS idx_metrics_name_time ON agent_metrics(metric_name, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_recorded ON agent_metrics(recorded_at DESC);

-- ── Trigger: auto-update updated_at ─────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tickets_updated_at
    BEFORE UPDATE ON tickets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_channel_configs_updated_at
    BEFORE UPDATE ON channel_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_knowledge_base_updated_at
    BEFORE UPDATE ON knowledge_base
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ── 9. Message Queue ────────────────────────────────────────────────────────
-- PostgreSQL-based message queue that replaces Kafka for Render.com deployment.
-- The API publishes events here; the worker polls and processes them.
--
-- Design notes:
--   - processed=false → pending messages waiting to be consumed
--   - processed=true  → already handled (kept for audit trail)
--   - FOR UPDATE SKIP LOCKED in consume_messages() prevents double-processing
--     when multiple worker instances run concurrently
--   - Purge processed rows older than 24h via database.queue.purge_processed_messages()

CREATE TABLE IF NOT EXISTS message_queue (
    id              BIGSERIAL    PRIMARY KEY,
    topic           VARCHAR(100) NOT NULL,         -- logical topic (e.g. fte.tickets.incoming)
    payload         JSONB        NOT NULL,          -- the full event payload
    processed       BOOLEAN      NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    processed_at    TIMESTAMPTZ                    -- set when consumed by the worker
);

COMMENT ON TABLE message_queue IS 'PostgreSQL-based message queue replacing Kafka for Render.com. Workers poll this table every 2 seconds using FOR UPDATE SKIP LOCKED.';
COMMENT ON COLUMN message_queue.topic IS 'Logical topic name — mirrors Kafka topic names (fte.tickets.incoming, etc.) for easy future migration.';
COMMENT ON COLUMN message_queue.processed IS 'False = waiting to be consumed. True = already processed. Rows are retained for audit; purge periodically.';

-- Index: worker polling (hot path — always queries by topic + processed)
CREATE INDEX IF NOT EXISTS idx_mq_topic_pending
    ON message_queue (topic, id ASC)
    WHERE processed = false;

-- Index: purge job (delete old processed rows)
CREATE INDEX IF NOT EXISTS idx_mq_processed_at
    ON message_queue (processed_at)
    WHERE processed = true;
