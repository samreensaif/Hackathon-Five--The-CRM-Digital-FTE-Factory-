-- ============================================================================
-- Migration 001: Initial Schema + Seed Data
-- ============================================================================
-- Customer Success Digital FTE — Production Database
--
-- This migration creates all tables, indexes, triggers, and seeds initial
-- channel configuration data. Safe to run multiple times (IF NOT EXISTS).
--
-- Run: psql -d customer_success -f 001_initial_schema.sql
-- Rollback: See DROP statements at bottom (commented out)
-- ============================================================================

BEGIN;

-- ── Extensions ──────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";  -- pgvector for semantic search

-- ── 1. Customers ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS customers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email               VARCHAR(255) UNIQUE,
    phone               VARCHAR(50),
    name                VARCHAR(255),
    plan                VARCHAR(20) DEFAULT 'free'
                        CHECK (plan IN ('free', 'pro', 'enterprise')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_contact_at     TIMESTAMPTZ,
    total_conversations INTEGER NOT NULL DEFAULT 0,
    metadata            JSONB DEFAULT '{}'::jsonb
);

-- ── 2. Customer Identifiers ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS customer_identifiers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id         UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    identifier_type     VARCHAR(20) NOT NULL
                        CHECK (identifier_type IN ('email', 'phone', 'whatsapp')),
    identifier_value    VARCHAR(255) NOT NULL,
    verified            BOOLEAN NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (identifier_type, identifier_value)
);

-- ── 3. Conversations ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS conversations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id         UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    initial_channel     VARCHAR(20) NOT NULL
                        CHECK (initial_channel IN ('email', 'whatsapp', 'web_form')),
    current_channel     VARCHAR(20)
                        CHECK (current_channel IN ('email', 'whatsapp', 'web_form')),
    channels_used       TEXT[] NOT NULL DEFAULT '{}',
    status              VARCHAR(20) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'resolved', 'escalated')),
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at            TIMESTAMPTZ,
    sentiment_score     DECIMAL(4,2),
    sentiment_trend     VARCHAR(20) DEFAULT 'stable'
                        CHECK (sentiment_trend IN ('improving', 'stable', 'declining', 'unknown')),
    topics              TEXT[] DEFAULT '{}',
    escalation_reason   TEXT,
    escalated_to        VARCHAR(255),
    escalated_to_email  VARCHAR(255),
    escalation_id       VARCHAR(50),
    resolution_notes    TEXT,
    metadata            JSONB DEFAULT '{}'::jsonb
);

-- ── 4. Messages ─────────────────────────────────────────────────────────

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
    sentiment_score     DECIMAL(4,2),
    intent              VARCHAR(50),
    tokens_used         INTEGER,
    latency_ms          INTEGER,
    tool_calls          JSONB,
    channel_message_id  VARCHAR(255),
    delivery_status     VARCHAR(20) DEFAULT 'pending'
                        CHECK (delivery_status IN ('pending', 'sent', 'delivered', 'failed', 'read'))
);

-- ── 5. Tickets ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS tickets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_ref          VARCHAR(50) NOT NULL UNIQUE,
    conversation_id     UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    customer_id         UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    source_channel      VARCHAR(20) NOT NULL
                        CHECK (source_channel IN ('email', 'whatsapp', 'web_form')),
    subject             VARCHAR(500),
    category            VARCHAR(50),
    priority            VARCHAR(10) NOT NULL DEFAULT 'medium'
                        CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    status              VARCHAR(20) NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'in_progress', 'resolved', 'escalated', 'closed')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ,
    resolution_notes    TEXT,
    assigned_to         VARCHAR(255),
    assigned_to_email   VARCHAR(255)
);

-- ── 6. Knowledge Base ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS knowledge_base (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title               VARCHAR(500) NOT NULL,
    content             TEXT NOT NULL,
    category            VARCHAR(100),
    embedding           vector(1536),
    source              VARCHAR(255),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata            JSONB DEFAULT '{}'::jsonb
);

-- ── 7. Channel Configs ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS channel_configs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel             VARCHAR(20) NOT NULL UNIQUE
                        CHECK (channel IN ('email', 'whatsapp', 'web_form')),
    enabled             BOOLEAN NOT NULL DEFAULT true,
    config              JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_template   TEXT,
    max_response_length INTEGER NOT NULL DEFAULT 1000,
    tone                VARCHAR(20) DEFAULT 'professional',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 8. Agent Metrics ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_metrics (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_name         VARCHAR(100) NOT NULL,
    metric_value        DECIMAL(12,4) NOT NULL,
    channel             VARCHAR(20),
    dimensions          JSONB DEFAULT '{}'::jsonb,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Indexes ─────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone) WHERE phone IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_cust_ident_value ON customer_identifiers(identifier_value);
CREATE INDEX IF NOT EXISTS idx_cust_ident_customer ON customer_identifiers(customer_id);

CREATE INDEX IF NOT EXISTS idx_conv_customer_status ON conversations(customer_id, status);
CREATE INDEX IF NOT EXISTS idx_conv_status ON conversations(status);
CREATE INDEX IF NOT EXISTS idx_conv_last_message ON conversations(last_message_at DESC);

CREATE INDEX IF NOT EXISTS idx_msg_conversation_created ON messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_msg_channel_id ON messages(channel_message_id) WHERE channel_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tickets_status_priority ON tickets(status, priority);
CREATE INDEX IF NOT EXISTS idx_tickets_customer ON tickets(customer_id);
CREATE INDEX IF NOT EXISTS idx_tickets_conversation ON tickets(conversation_id);
CREATE INDEX IF NOT EXISTS idx_tickets_ref ON tickets(ticket_ref);

CREATE INDEX IF NOT EXISTS idx_metrics_name_time ON agent_metrics(metric_name, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_recorded ON agent_metrics(recorded_at DESC);

-- ── Triggers ────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_tickets_updated_at') THEN
        CREATE TRIGGER trg_tickets_updated_at
            BEFORE UPDATE ON tickets
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_channel_configs_updated_at') THEN
        CREATE TRIGGER trg_channel_configs_updated_at
            BEFORE UPDATE ON channel_configs
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_knowledge_base_updated_at') THEN
        CREATE TRIGGER trg_knowledge_base_updated_at
            BEFORE UPDATE ON knowledge_base
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- ============================================================================
-- SEED DATA: Channel Configurations
-- ============================================================================
-- Default channel settings based on brand-voice.md guidelines.
-- API credentials should be set via environment variables, not stored here.

INSERT INTO channel_configs (channel, enabled, config, response_template, max_response_length, tone)
VALUES
    (
        'email',
        true,
        '{
            "provider": "gmail_api",
            "from_address": "support@techcorp.io",
            "from_name": "TaskFlow Support Team",
            "subject_prefix": "[TaskFlow Support]",
            "include_ticket_ref_in_subject": true,
            "signature": "Best regards,\nTaskFlow Support Team\nsupport@techcorp.io"
        }'::jsonb,
        E'Dear {{customer_name}},\n\n{{acknowledgment}}\n\n{{solution}}\n\n{{additional_context}}\n\n{{closing}}\n\nBest regards,\nTaskFlow Support Team\nsupport@techcorp.io',
        2000,  -- ~400 words at ~5 chars/word
        'professional'
    ),
    (
        'whatsapp',
        true,
        '{
            "provider": "whatsapp_business_api",
            "phone_number_id": "",
            "display_name": "TaskFlow Support",
            "max_messages_per_response": 3,
            "approved_emojis": ["✅", "👉", "👋", "🔧", "💡"]
        }'::jsonb,
        E'Hi {{customer_name}}! 👋\n\n{{message}}\n\n{{follow_up}}',
        300,   -- WhatsApp: short messages per brand voice
        'friendly'
    ),
    (
        'web_form',
        true,
        '{
            "provider": "internal_api",
            "auto_acknowledge": true,
            "include_ticket_id": true,
            "follow_up_email": "support@techcorp.io"
        }'::jsonb,
        E'Hi {{customer_name}},\n\nThank you for contacting TaskFlow Support. We''ve received your request.\n\n**Ticket ID:** {{ticket_id}}\n\n{{acknowledgment}}\n\n{{solution}}\n\n{{timeline}}\n\nIf you need further assistance, you can reply to this message or reach us at support@techcorp.io.\n\n— TaskFlow Support Team',
        1500,  -- ~300 words
        'semi-formal'
    )
ON CONFLICT (channel) DO NOTHING;

-- ============================================================================
-- SEED DATA: Escalation Routing Reference
-- ============================================================================
-- Stored as a comment for reference. Actual routing is in the agent config.
-- See: 1-Incubation-Phase/context/escalation-rules.md
--
-- billing   → Lisa Tanaka    <billing@techcorp.io>            Tier 1
-- legal     → Rachel Foster  <legal@techcorp.io>              Tier 1
-- security  → James Okafor   <security@techcorp.io>           Tier 1
-- account   → Sarah Chen     <cs-lead@techcorp.io>            Tier 1
-- technical → Priya Patel    <engineering-support@techcorp.io> Tier 1
-- churn     → Marcus Rivera  <cs-lead@techcorp.io>            Tier 1
-- general   → Marcus Rivera  <cs-lead@techcorp.io>            Tier 1
--
-- SLA by plan: enterprise=1hr, pro=4hr, free=24hr

COMMIT;

-- ============================================================================
-- ROLLBACK (uncomment to drop all objects — USE WITH CAUTION)
-- ============================================================================
-- DROP TABLE IF EXISTS agent_metrics CASCADE;
-- DROP TABLE IF EXISTS channel_configs CASCADE;
-- DROP TABLE IF EXISTS knowledge_base CASCADE;
-- DROP TABLE IF EXISTS tickets CASCADE;
-- DROP TABLE IF EXISTS messages CASCADE;
-- DROP TABLE IF EXISTS conversations CASCADE;
-- DROP TABLE IF EXISTS customer_identifiers CASCADE;
-- DROP TABLE IF EXISTS customers CASCADE;
-- DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;
-- DROP EXTENSION IF EXISTS vector;
-- DROP EXTENSION IF EXISTS "uuid-ossp";
