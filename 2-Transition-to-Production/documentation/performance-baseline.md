# Performance Baseline — Customer Success Digital FTE

**Purpose:** Record actual performance metrics from Phase 1 (Incubation) as benchmarks, define production targets for Phase 3, and document scalability requirements.

**Source:** Test results from `prototype.py --all` (62 tickets), `test_conversation_flow.py` (61 tests), and incubation observations.

---

## 1. Incubation Metrics (Actual Measurements)

### Escalation Accuracy

| Metric | v0.1 | v0.2 (Final) | Delta |
|--------|------|-------------|-------|
| **Overall accuracy** | 92% (57/62) | **98% (61/62)** | +6% |
| **False positives** | 1 (TF-0020) | **0** | -1 |
| **False negatives** | 4 | **1** (TF-0015) | -3 |
| **True positives** (correctly escalated) | 17/21 | **20/21** | +3 |
| **True negatives** (correctly not escalated) | 40/41 | **41/41** | +1 |
| **Precision** | 17/18 = 94% | **20/20 = 100%** | +6% |
| **Recall** | 17/21 = 81% | **20/21 = 95%** | +14% |

### Escalation Accuracy by Category

| Category | Tickets | Correct | Accuracy | Notes |
|----------|---------|---------|----------|-------|
| Billing & financial | 5 | 5 | **100%** | All billing disputes correctly escalated |
| Legal & compliance | 3 | 3 | **100%** | GDPR, SOC 2, DPA all caught |
| Security | 2 | 2 | **100%** | Data breach, permission bypass |
| Account management | 5 | 5 | **100%** | Workspace deletion, ownership transfer, 2FA lockout |
| Angry / churn risk | 3 | 3 | **100%** | ALL CAPS, competitor mentions |
| Data loss | 4 | 4 | **100%** | Added in v0.2 |
| Performance / infrastructure | 2 | 1 | **50%** | TF-0015 missed (regex proximity limit) |
| Non-escalation (how-to, feature-request, etc.) | 41 | 41 | **100%** | Zero false positives |

### Sentiment Analysis

| Metric | Value |
|--------|-------|
| **Direction accuracy** (pos/neg/neutral agreement) | ~75% |
| **Mean absolute error** (vs ground truth 0-1 scale) | 0.43 |
| **Extreme negative detection** | 100% (ALL CAPS, profanity always < -0.5) |
| **Score range** | -1.00 to +1.00 |
| **Lexicon size** | 34 positive words, 38 negative words |

### Document Retrieval

| Metric | Value |
|--------|-------|
| **Top-1 correct section** (estimated) | ~80% for how-to queries |
| **Technique** | TF-IDF with IDF weights, title match 3x boost |
| **Doc sections indexed** | ~50 sections from product-docs.md (605 lines) |
| **Known failure** | TF-0022: "recurring tasks" returns general Task Management instead of FAQ Q20 |

### Test Suite

| Test Group | Tests | Status |
|-----------|-------|--------|
| Multi-turn email conversation | 8 | 8/8 pass |
| Cross-channel continuity | 8 | 8/8 pass |
| Sentiment trending & auto-escalation | 8 | 8/8 pass |
| ConversationManager unit tests | 16 | 16/16 pass |
| MCP tool direct invocation | 15 | 15/15 pass |
| Conversation summary & stats | 6 | 6/6 pass |
| **Total** | **61** | **61/61 pass** |

### Response Processing (Incubation — Not Real Latency)

Incubation runs as a single-threaded Python script processing tickets from JSON. These numbers reflect CPU processing time only, not real-world latency:

| Operation | Estimated Time | Notes |
|-----------|---------------|-------|
| Sentiment analysis (keyword) | < 1ms | In-memory word lookup |
| Intent detection (regex) | < 1ms | ~40 regex patterns |
| Escalation check (regex) | < 2ms | ~60 regex patterns |
| TF-IDF doc search | < 5ms | ~50 sections, in-memory |
| Response formatting | < 1ms | String template assembly |
| **Full pipeline per ticket** | **< 10ms** | No network calls |

These numbers will NOT carry over to production. Production latency will be dominated by LLM API calls (~1-3 seconds) and database queries (~10-50ms).

### Channel Distribution

| Channel | Tickets | Escalation Rate | Avg Message Length |
|---------|---------|----------------|--------------------|
| Gmail | 25 (40%) | 40% (10/25) | 648 chars / 107 words |
| WhatsApp | 20 (32%) | 20% (4/20) | 43 chars / 9 words |
| Web Form | 17 (27%) | 41% (7/17) | 328 chars / 56 words |

### Category Distribution

| Category | Count | % | Escalation Rate |
|----------|-------|---|-----------------|
| how-to | 17 | 27% | 0% (0/17) |
| bug-report | 12 | 19% | 50% (6/12) |
| billing | 9 | 15% | 56% (5/9) |
| technical | 8 | 13% | 13% (1/8) |
| account | 7 | 11% | 71% (5/7) |
| complaint | 3 | 5% | 100% (3/3) |
| feature-request | 3 | 5% | 0% (0/3) |
| feedback | 3 | 5% | 33% (1/3) |

---

## 2. Production Targets

### Escalation Accuracy Targets

| Metric | Incubation Baseline | Production Target | Rationale |
|--------|--------------------|--------------------|-----------|
| Overall accuracy | 98% (61/62) | **>= 99%** | LLM judgment handles TF-0015-type cases regex can't |
| False positive rate | 0% (0/62) | **<= 1%** | Zero false positives is ideal; 1% allows for edge cases |
| False negative rate | 1.6% (1/62) | **<= 0.5%** | Critical that billing/legal/security issues are never missed |
| Billing/legal/security recall | 100% | **100%** | Non-negotiable — these must always escalate |

### Response Quality Targets

| Metric | Incubation Baseline | Production Target | Rationale |
|--------|--------------------|--------------------|-----------|
| Doc retrieval accuracy (top-1) | ~80% | **>= 95%** | Vector embeddings + RAG will significantly improve |
| Sentiment direction accuracy | ~75% | **>= 90%** | LLM-based sentiment replaces keyword approach |
| Sentiment mean absolute error | 0.43 | **<= 0.15** | LLM provides much finer-grained sentiment |
| First-contact resolution rate | Not measured | **>= 80%** | For non-escalation tickets |
| Customer satisfaction (CSAT) | Not measured | **>= 4.0/5.0** | Post-interaction survey |
| Brand voice compliance | Reasonable | **>= 95%** | Automated compliance checks in CI |

### Latency Targets

| Metric | Incubation Baseline | Production Target | Rationale |
|--------|--------------------|--------------------|-----------|
| First acknowledgment (P50) | < 10ms (local) | **< 5 seconds** | Customer-facing SLA |
| Full response (P50) | < 10ms (local) | **< 10 seconds** | Including LLM generation |
| Full response (P95) | < 10ms (local) | **< 15 seconds** | Allowing for complex tickets |
| Full response (P99) | < 10ms (local) | **< 30 seconds** | Worst case with retries |
| Escalation handoff | Instant | **< 5 seconds** | Notify human agent rapidly |

### Availability Targets

| Metric | Production Target | Rationale |
|--------|-------------------|-----------|
| Uptime | **99.9%** (< 8.7 hours/year downtime) | SaaS standard for customer-facing service |
| Error rate | **< 1%** of requests | Errors result in failed responses |
| Recovery time (MTTR) | **< 15 minutes** | Auto-scaling + health checks |

### Token Usage Estimates (Production)

| Interaction Type | Est. Input Tokens | Est. Output Tokens | Est. Cost per Interaction |
|------------------|-------------------|-------------------|--------------------------|
| Simple FAQ / how-to | ~1,500 (system prompt + message + docs) | ~200 | ~$0.005 |
| Bug report | ~1,800 (+ troubleshooting docs) | ~300 | ~$0.007 |
| Billing inquiry | ~1,500 (+ escalation) | ~150 | ~$0.005 |
| Escalation handoff | ~1,300 (no doc search needed) | ~100 | ~$0.004 |
| Multi-turn (3 messages) | ~2,500 (+ conversation history) | ~250 | ~$0.009 |
| **Average** | **~1,700** | **~200** | **~$0.006** |

*Note: Estimates based on Claude Sonnet / GPT-4o-mini pricing. Actual costs depend on model choice.*

---

## 3. Scalability Requirements

### Current Scale (TechCorp)

| Metric | Value | Source |
|--------|-------|--------|
| Total customers | 12,000 | Company profile |
| Tickets per week | ~200 | CS team estimate |
| Tickets per day (avg) | ~29 | 200 / 7 |
| Peak tickets per hour (estimated) | ~15 | 2x average, business hours |
| Support channels | 3 (Gmail, WhatsApp, Web Form) | Requirements |
| CS team size | 6 people | Company profile |

### Production Scale Targets

| Metric | Target | Rationale |
|--------|--------|-----------|
| Concurrent ticket processing | **50** | 2x peak + buffer for growth |
| Tickets per hour (sustained) | **100** | 5x current peak for headroom |
| Tickets per day | **500** | 2.5x growth over current baseline |
| Conversations in DB | **100,000** | ~1 year of conversation history |
| Messages in DB | **500,000** | ~5 messages per conversation avg |
| Doc sections indexed | **200** | Growth as product documentation expands |
| API response time (P99) | **< 30 seconds** | Including LLM generation |

### Infrastructure Sizing (Estimated)

| Component | Configuration | Notes |
|-----------|--------------|-------|
| FastAPI pods | 2-4 pods, 1 vCPU / 512MB each | Auto-scale on CPU > 70% |
| PostgreSQL | 1 instance, 2 vCPU / 4GB RAM, 50GB disk | Managed (Cloud SQL / RDS) |
| Vector store | pgvector extension OR FAISS in-memory | ~200 sections = tiny index |
| Redis (optional) | 1 instance, 1GB | Rate limiting + session cache |
| LLM API | Rate limit: 100 RPM | Standard tier sufficient |

### Scaling Triggers

| Trigger | Action |
|---------|--------|
| CPU > 70% on FastAPI pods | Auto-scale up (max 8 pods) |
| CPU < 30% on FastAPI pods | Auto-scale down (min 2 pods) |
| DB connections > 80% pool | Alert + increase pool size |
| LLM API rate limit > 80% | Alert + queue overflow tickets |
| Error rate > 5% | Alert + investigate |
| P99 latency > 30s | Alert + investigate |

---

## 4. Monitoring & Alerting Plan

### Key Metrics to Track

| Metric | Type | Alert Threshold |
|--------|------|----------------|
| `ticket_processing_duration_seconds` | Histogram | P99 > 30s |
| `escalation_rate` | Gauge | > 50% (may indicate system issue) |
| `escalation_accuracy` (sampled) | Gauge | < 95% |
| `confidence_score_distribution` | Histogram | Mean < 0.4 (agent uncertain) |
| `llm_api_latency_seconds` | Histogram | P99 > 10s |
| `llm_api_error_rate` | Counter | > 5% |
| `db_query_duration_seconds` | Histogram | P99 > 500ms |
| `channel_response_count` | Counter (by channel) | Monitoring only |
| `sentiment_score_distribution` | Histogram | Mean < -0.3 (customers unhappy) |
| `conversation_resolution_rate` | Gauge | < 70% |

### Dashboards (Grafana)

| Dashboard | Panels |
|-----------|--------|
| **Agent Overview** | Tickets/hour, escalation rate, avg confidence, channel split |
| **Response Quality** | Sentiment trends, resolution rate, CSAT (when available) |
| **Infrastructure** | Pod CPU/memory, DB connections, LLM API latency/errors |
| **Escalation Breakdown** | Escalation by category, routing distribution, SLA compliance |
