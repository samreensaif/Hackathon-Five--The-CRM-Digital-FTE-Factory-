# Customer Success Digital FTE — Specification

**Version:** 0.2.0
**Date:** 2026-02-16
**Phase:** 1 — Incubation (Claude Code)
**Status:** Incubation complete, ready for Phase 2 transition

---

## Executive Summary

The Customer Success Digital FTE is a 24/7 AI-powered customer support agent for **TaskFlow**, a project management SaaS product by TechCorp (Series B, 12K customers). It handles incoming support inquiries across Gmail, WhatsApp, and Web Forms — triaging tickets, generating doc-grounded responses, detecting escalation-worthy issues, and maintaining conversation continuity across channels.

During Phase 1 (Incubation), the agent was built as a rule-based prototype using keyword matching, TF-IDF document retrieval, and regex-based escalation detection. It was tested against a dataset of 62 real-world sample tickets and achieved:

- **98% escalation accuracy** (61/62 tickets correctly classified)
- **61/61 integration tests** passing across multi-turn, cross-channel, and sentiment scenarios
- **6 core skills** identified, tested, and documented
- **6 MCP tools** exposed for LLM-client integration

The agent is designed to resolve the majority of common inquiries (how-to questions, feature requests, standard bug reports) autonomously, while reliably escalating sensitive issues (billing disputes, legal/security concerns, data loss, angry customers) to the correct human team member.

---

## Purpose

### Problem Statement

TechCorp's 6-person customer success team handles ~200 tickets/week across email, WhatsApp, and web forms. Response times average 4-8 hours, and the team spends ~60% of time on repetitive how-to questions that could be answered from existing product documentation.

### Solution

A Digital FTE that:

1. **Answers routine questions instantly** — grounded in product-docs.md (605 lines of comprehensive documentation)
2. **Escalates sensitive issues reliably** — billing, legal, security, and data-loss tickets are routed to the right specialist within SLA
3. **Maintains context across channels** — a customer who emails about an issue and follows up on WhatsApp gets a continuous conversation, not a cold start
4. **Adapts tone per channel** — formal emails, casual WhatsApp messages, structured web form acknowledgments

### Target Outcome

- Resolve 80%+ of how-to and standard inquiries without human intervention
- Reduce average response time from hours to seconds
- Ensure 0% of billing/legal/security issues are incorrectly auto-resolved

---

## Supported Channels

| Channel | Protocol | Avg Message Length | Escalation Rate | Tone | Max Response Length |
|---------|----------|-------------------|-----------------|------|-------------------|
| **Gmail** | Gmail API / IMAP | 648 chars (107 words) | 40% (10/25) | Formal — Dear/Hi greeting, Best regards closing | ~500 words |
| **WhatsApp** | WhatsApp Business API | 43 chars (9 words) | 20% (4/20) | Conversational — short, emoji-friendly | 300 characters |
| **Web Form** | HTTP POST | 328 chars (56 words) | 41% (7/17) | Semi-formal — ticket ID reference, structured | Medium length |

**Channel-Specific Behaviors:**
- **Gmail:** Rich context from customers. Agent can usually resolve in a single response. Includes greeting, body, ticket reference, and professional closing.
- **WhatsApp:** Minimal context. Agent must handle greetings ("hi"), emoji-only messages ("👍"), and sparse bug reports ("cant login help"). Truncation uses sentence boundaries with numbered-list awareness.
- **Web Form:** Semi-structured input. Always includes ticket ID in response. Falls between Gmail and WhatsApp in formality.

---

## Scope

### In Scope (Phase 1 — Implemented)

| Capability | Status | Evidence |
|-----------|--------|----------|
| Ticket triage (intent + category detection) | Done | 13 intent types, 8 category types |
| Doc-grounded response generation | Done | TF-IDF over product-docs.md (~50 sections) |
| Rule-based escalation detection | Done | 98% accuracy, 12 escalation categories |
| Keyword-based sentiment analysis | Done | -1.0 to +1.0 scale, ~75% direction accuracy |
| Channel-specific response formatting | Done | Gmail/WhatsApp/Web Form templates |
| Multi-turn conversation tracking | Done | Per-customer, per-channel state management |
| Cross-channel conversation continuity | Done | Identity linking (email ↔ phone), conversation reuse |
| Sentiment trend monitoring | Done | Auto-escalation on 3+ negative or >0.4 drop |
| MCP server with 6 tools | Done | FastMCP, stdio/SSE transport |
| Spam detection | Done | Keyword-based spam intent classification |
| Greeting/edge-case handling | Done | "hi", emoji-only, minimal-context messages |

### Out of Scope (Phase 2/3)

| Capability | Phase | Notes |
|-----------|-------|-------|
| LLM-based response generation (RAG) | Phase 2 | Replace TF-IDF with embedding retrieval + LLM generation |
| Persistent storage (PostgreSQL) | Phase 3 | Replace in-memory dicts |
| Real channel integrations | Phase 3 | Gmail API, WhatsApp Business API, webhook endpoints |
| Attachment/screenshot handling | Phase 2 | Detect "see screenshot" references, request re-send |
| Multi-issue decomposition | Phase 2 | Split compound tickets into separate sub-responses |
| Non-English language support | Phase 3 | Language detection + routing |
| De-escalation flow | Phase 3 | Return escalated conversations to AI after resolution |
| Rate limiting / abuse prevention | Phase 3 | Prevent spam customers from creating excessive conversations |
| A/B testing of responses | Phase 3 | Compare response quality across approaches |

---

## Tools & Skills

### 6 Agent Skills

| # | Skill | Implementation | MCP Tool | Key Metric |
|---|-------|---------------|----------|------------|
| 1 | **Knowledge Retrieval** | `KnowledgeBase` (TF-IDF, title 3x boost) | `search_knowledge_base` | ~80% correct top-1 section |
| 2 | **Sentiment Analysis** | `SentimentAnalyzer` (keyword, negation-aware) | `analyze_sentiment` | ~75% direction accuracy |
| 3 | **Escalation Decision** | `EscalationEngine` (12 categories, ~60 regex) | `escalate_to_human` | 98% accuracy (61/62) |
| 4 | **Channel Adaptation** | `ResponseFormatter` (3 channel templates) | `send_response` | Clean truncation, brand-voice compliant |
| 5 | **Customer Identification** | `ConversationManager` (identity linking) | `get_customer_history` | 100% resolution for linked IDs |
| 6 | **Conversation Continuity** | `ConversationManager` (state machine) | `get_customer_history` | 61/61 tests passing |

### 6 MCP Tools

| Tool | Description | Inputs | Key Output |
|------|-------------|--------|------------|
| `search_knowledge_base` | TF-IDF search over product docs | query, max_results | Ranked doc sections |
| `create_ticket` | Create + process a ticket through the full pipeline | email, name, subject, message, channel, plan | ticket_id, intent, sentiment, response, escalation |
| `get_customer_history` | Cross-channel history for a customer | customer_id | conversations, topics, channels, sentiment trend |
| `escalate_to_human` | Route ticket to correct human specialist | ticket_id, reason, urgency, category | escalation_id, assigned_to, SLA |
| `send_response` | Format and deliver channel-appropriate response | ticket_id, message, channel, name | formatted_message, delivery_status |
| `analyze_sentiment` | Standalone sentiment analysis | text | score, label, confidence |

### 4 MCP Resources

| Resource URI | Description |
|-------------|-------------|
| `docs://product-docs` | Full TaskFlow product documentation (605 lines) |
| `docs://escalation-rules` | Escalation rules and routing table (226 lines) |
| `docs://brand-voice` | Brand voice and channel formatting guidelines |
| `stats://conversations` | Live conversation manager statistics |

---

## Performance Requirements

All metrics are from actual test runs against the 62-ticket sample dataset.

### Escalation Accuracy

| Metric | Target | Actual (v0.2) |
|--------|--------|---------------|
| Overall accuracy | >= 95% | **98% (61/62)** |
| False positives | 0 | **0** |
| False negatives | <= 2 | **1** (TF-0015) |
| Billing/legal/security escalation | 100% | **100%** |

### Escalation Accuracy by Category

| Category | Expected Escalations | Correctly Escalated | Accuracy |
|----------|---------------------|-------------------|----------|
| Billing & financial | 5 | 5 | 100% |
| Legal & compliance | 3 | 3 | 100% |
| Security | 2 | 2 | 100% |
| Account management | 5 | 5 | 100% |
| Angry / churn risk | 3 | 3 | 100% |
| Data loss | 4 | 4 | 100% |
| Performance / infrastructure | 2 | 1 | 50% (TF-0015 missed) |

### Sentiment Analysis

| Metric | Target | Actual |
|--------|--------|--------|
| Direction accuracy (pos/neg/neutral) | >= 70% | **~75%** |
| Mean absolute error (vs ground truth) | <= 0.5 | **0.43** |
| Extreme negative detection | 100% | **100%** (ALL CAPS, profanity always < -0.5) |

### Test Suite

| Test Group | Tests | Status |
|-----------|-------|--------|
| Multi-turn email conversation | 8 | All pass |
| Cross-channel continuity | 8 | All pass |
| Sentiment trending & auto-escalation | 8 | All pass |
| ConversationManager unit tests | 16 | All pass |
| MCP tool direct invocation | 15 | All pass |
| Conversation summary & stats | 6 | All pass |
| **Total** | **61** | **61/61 passing** |

---

## Guardrails

### NEVER Rules (Hard Constraints)

The agent must NEVER:

1. **Process refunds or modify billing** — All billing disputes, refund requests, and pricing negotiations must be escalated to Lisa Tanaka (billing@techcorp.io)
2. **Handle legal requests autonomously** — GDPR deletions, DPA requests, legal threats, and compliance questions go to Rachel Foster (legal@techcorp.io)
3. **Dismiss security concerns** — Suspected breaches, vulnerability reports, and suspicious activity go to James Okafor (security@techcorp.io)
4. **Delete accounts or workspaces** — Permanent destructive actions require human authorization via Sarah Chen (cs-lead@techcorp.io)
5. **Make promises about SLA or compensation** — Only human agents can offer credits, discounts, or SLA guarantees
6. **Fabricate product capabilities** — Responses must be grounded in product-docs.md; if no doc match is found, say "I don't have specific documentation for that"
7. **Ignore explicit human-agent requests** — "I want to talk to a real person" always escalates immediately
8. **Auto-resolve tickets with confidence < 0.4** — Low-confidence tickets must be escalated, not answered with uncertain information
9. **Respond to spam with substantive content** — Spam/nonsensical messages are auto-closed without engagement
10. **Share customer data across conversations** — Each customer's data is isolated to their own conversation history

### ALWAYS Rules (Required Behaviors)

The agent must ALWAYS:

1. **Acknowledge receipt within the SLA window** — Enterprise: 1 hour, Pro: 4 hours, Free: 24 hours
2. **Include ticket ID in all responses** — Every response references the ticket for tracking
3. **Match channel tone** — Formal for Gmail, conversational for WhatsApp, semi-formal for Web Form
4. **Check escalation rules before generating a response** — Escalation decision happens first in the pipeline
5. **Provide the escalation team member's name** — When escalating, tell the customer who will handle their case
6. **Track conversation state** — Every message updates the conversation's message history, sentiment history, and topic list
7. **Detect cross-channel continuity** — When a known customer contacts via a new channel, reference their existing conversation
8. **Use empathetic language for negative-sentiment tickets** — Sentiment score drives empathy opener selection
9. **Preserve numbered list integrity in WhatsApp** — Truncation must not break mid-list-item
10. **Log escalation reason** — Every escalation includes a human-readable reason string

---

## Response Quality Standards

### Tone Guidelines (from brand-voice.md)

| Channel | Voice | Example Greeting | Example Closing |
|---------|-------|-----------------|-----------------|
| Gmail | Professional, warm, thorough | "Dear Sarah," or "Hi Sarah," | "Best regards, TaskFlow Support Team" |
| WhatsApp | Friendly, concise, emoji-ok | "Hey! 👋" | "Need more help? Just reply!" |
| Web Form | Balanced, structured, ticket-aware | "Hi there," | "Ref: TF-20260216-XXXX" |

### Response Structure

**Standard response (non-escalation):**
1. Greeting (channel-appropriate)
2. Empathy opener (if sentiment < -0.2)
3. Cross-channel context (if applicable: "I see you contacted us earlier via...")
4. Doc-grounded answer body
5. Follow-up offer
6. Closing (channel-appropriate)
7. Ticket reference

**Escalation response:**
1. Greeting
2. Empathy opener
3. Acknowledgment of the issue
4. Escalation notice with assigned team member name
5. SLA expectation (based on customer plan)
6. Reassurance
7. Closing

### Confidence Scoring

| Score Range | Meaning | Action |
|------------|---------|--------|
| >= 0.7 | High confidence | Auto-respond |
| 0.4 - 0.7 | Medium confidence | Auto-respond with follow-up offer |
| < 0.4 | Low confidence | Escalate to human |

Confidence is calculated as:
- Base: 0.50
- Doc matches found: +0.20
- Clear intent detected: +0.15
- Easy category (how-to, feature-request): +0.10
- Short message (< 20 chars): -0.15
- Negative sentiment (< -0.3): -0.10
- Escalation pattern detected: overrides to force escalation

---

## Edge Cases Handled

| Edge Case | Ticket Example | Behavior |
|-----------|---------------|----------|
| Greeting only ("hi") | TF-0038 | Detect as greeting intent, respond with channel-appropriate prompt for details |
| Emoji only ("👍") | TF-0039 | Treat as acknowledgment, respond gracefully |
| Minimal context ("cant login help") | TF-0026 | Detect intent, provide best-match doc, offer to ask clarifying questions |
| Missing attachment ("see screenshot") | TF-0032 | Acknowledge reference, ask customer to describe the issue or re-send |
| ALL CAPS angry rant | TF-0045 | Detect extreme negative sentiment, escalate with empathetic response |
| Spam / nonsensical input | TF-0061 | Detect spam intent, auto-close, no substantive response |
| Multi-issue single ticket | TF-0025 | Address the primary detected intent (full decomposition in Phase 2) |
| Repeat contact (3rd time) | TF-0016 | Detect repeat_contact pattern, escalate with context about prior interactions |
| Cross-channel follow-up | Test scenario | Reuse conversation, reference prior channel, add to channels_used list |
| Sentiment decline over turns | Test scenario | Track per-message sentiment, auto-escalate after 3+ negative or >0.4 drop |
| Enterprise + critical severity | TF-0005 | Compound rule: enterprise plan + critical keywords = always escalate |
| Unauthorized billing | TF-0031 | Pattern: "charged" + "never upgraded/authorized" = billing escalation |

---

## Known Limitations

### Addressed in Phase 2

| Limitation | Impact | Mitigation Plan |
|-----------|--------|----------------|
| **TF-IDF doc retrieval returns wrong section for some queries** | TF-0022 gets Task Management instead of FAQ Q20 about recurring tasks | Replace with embedding-based RAG (retrieval-augmented generation) |
| **Sentiment analyzer gives extreme scores** | Mean absolute error of 0.43; technical words score negative even when factual | Replace with LLM-based sentiment analysis |
| **TF-0015 false negative** | Enterprise dashboard performance issue not escalated — "unusable" and "affects all users" are too far apart for regex | Compound NLP rule or LLM classification |
| **Duplicate empathy in escalation + negative sentiment** | "I completely understand..." appears twice when both conditions trigger | Dedup logic in response generation |
| **No attachment handling** | 3 tickets reference screenshots that don't exist | Detect attachment references, ask for re-send |

### Addressed in Phase 3

| Limitation | Impact | Mitigation Plan |
|-----------|--------|----------------|
| **In-memory storage** | All conversation state lost on restart | PostgreSQL for persistent storage |
| **No real channel integrations** | Currently processes tickets from JSON, not live APIs | Gmail API, WhatsApp Business API, webhook endpoints |
| **No language detection** | Cannot handle non-English messages | Language detection + routing to appropriate team |
| **No de-escalation flow** | Escalated conversations can't return to AI | State machine update: escalated → active |
| **No rate limiting** | Spam customers could create excessive conversations | Per-customer rate limits |

### Fundamental Constraints

| Constraint | Description |
|-----------|-------------|
| **Rule-based, not generative** | Responses are template-based with doc insertion, not LLM-generated natural language. Phase 2 will add LLM generation. |
| **Single-turn response focus** | Agent answers one message at a time. It doesn't proactively ask clarifying questions or drive multi-step troubleshooting workflows. |
| **No learning from outcomes** | Agent doesn't improve from resolved/escalated ticket outcomes. Phase 3 will add feedback loops. |

---

## Deployment Readiness

### Phase 1 Deliverables (Complete)

| Deliverable | File | Status |
|------------|------|--------|
| Agent prototype (v0.2) | `src/agent/prototype.py` | Done — 98% accuracy |
| Conversation manager | `src/agent/conversation_manager.py` | Done — stateful, cross-channel |
| MCP server | `src/agent/mcp_server.py` | Done — 6 tools, 4 resources |
| Integration tests | `tests/test_conversation_flow.py` | Done — 61/61 passing |
| Agent skills definition | `specs/agent-skills.yaml` | Done — 6 skills documented |
| Discovery log | `specs/discovery-log.md` | Done — 5 entries |
| Product documentation | `context/product-docs.md` | Done — 605 lines |
| Escalation rules | `context/escalation-rules.md` | Done — 226 lines |
| Brand voice guidelines | `context/brand-voice.md` | Done |
| Company profile | `context/company-profile.md` | Done |
| Sample tickets | `context/sample-tickets.json` | Done — 62 tickets |
| FTE specification | `specs/customer-success-fte-spec.md` | This document |

### Phase 2 Transition Checklist

- [ ] Replace TF-IDF with embedding-based retrieval (FAISS or Chroma)
- [ ] Add LLM-based response generation (RAG pipeline)
- [ ] Replace keyword sentiment with LLM sentiment analysis
- [ ] Add NLP-based escalation for TF-0015-type edge cases
- [ ] Implement attachment detection and handling
- [ ] Add multi-issue decomposition
- [ ] Fix duplicate empathy in escalation responses
- [ ] Add persistent storage (SQLite for Phase 2, PostgreSQL for Phase 3)

### Phase 3 Production Checklist

- [ ] Deploy MCP server with SSE transport on production infrastructure
- [ ] Integrate Gmail API for real email processing
- [ ] Integrate WhatsApp Business API for real chat processing
- [ ] Set up webhook endpoints for web form submissions
- [ ] Migrate to PostgreSQL for conversation storage
- [ ] Add language detection and non-English routing
- [ ] Implement de-escalation flow (escalated → active)
- [ ] Add per-customer rate limiting
- [ ] Set up observability (logging, metrics, alerting)
- [ ] Implement A/B testing framework for response quality
- [ ] Deploy on Kubernetes with auto-scaling

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                       MCP Server                             │
│                  (mcp_server.py — FastMCP)                    │
├─────────────────────────────────────────────────────────────┤
│  Tools:                          Resources:                  │
│  ├── search_knowledge_base       ├── docs://product-docs     │
│  ├── create_ticket ──────┐       ├── docs://escalation-rules │
│  ├── get_customer_history │       ├── docs://brand-voice      │
│  ├── escalate_to_human    │       └── stats://conversations   │
│  ├── send_response        │                                   │
│  └── analyze_sentiment    │                                   │
└───────────────────────────┼──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│                 CustomerSuccessAgent                          │
│                    (prototype.py)                             │
├─────────────────────────────────────────────────────────────┤
│  Pipeline: intent → escalation → search → confidence →       │
│            response → format → deliver                       │
│                                                              │
│  ├── SentimentAnalyzer  — keyword-based, -1.0 to +1.0       │
│  ├── IntentDetector     — 13 intent types                    │
│  ├── EscalationEngine   — 12 categories, ~60 regex patterns  │
│  ├── KnowledgeBase      — TF-IDF over product-docs.md        │
│  └── ResponseFormatter  — 3 channel templates                │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│                ConversationManager                            │
│              (conversation_manager.py)                        │
├─────────────────────────────────────────────────────────────┤
│  ├── Per-customer conversation store (in-memory)             │
│  ├── Cross-channel identity linking (email ↔ phone)          │
│  ├── Sentiment trend tracking (auto-escalation)              │
│  ├── Topic tracking and deduplication                        │
│  └── Conversation state machine (active/resolved/escalated)  │
└─────────────────────────────────────────────────────────────┘
```

---

## Appendix: Test Dataset Summary

**62 sample tickets** across 3 channels:

| Dimension | Breakdown |
|-----------|-----------|
| **Channels** | Gmail: 25, WhatsApp: 20, Web Form: 17 |
| **Categories** | how-to: 17, bug-report: 12, billing: 9, technical: 8, account: 7, complaint: 3, feature-request: 3, feedback: 3 |
| **Escalation split** | 21 escalate (34%), 41 do not (66%) |
| **Plan distribution** | Free, Pro, and Enterprise tiers represented |
| **Sentiment range** | 0.0 (angry) to 1.0 (happy), avg 0.50 |
| **Edge cases** | Greeting only, emoji only, minimal context, ALL CAPS, spam, multi-issue, repeat contact, missing attachment |
