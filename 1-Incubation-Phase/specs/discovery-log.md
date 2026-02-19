# Discovery Log

Track findings, experiments, and insights during the incubation phase.

---

## Entry 1 — Sample Ticket Analysis (62 tickets)

- **Date:** 2026-02-16
- **Experiment:** Statistical analysis of all 62 sample tickets to discover channel patterns, escalation triggers, common issues, and edge cases.
- **Method:** Parsed sample-tickets.json. Computed per-channel stats (message length, sentiment, escalation rate, category mix). Identified keywords and edge cases programmatically.

### Channel Patterns

| Metric | Gmail (25) | WhatsApp (20) | Web Form (17) |
|--------|-----------|---------------|---------------|
| Avg message length (chars) | 648 | 43 | 328 |
| Avg message length (words) | 107 | 9 | 56 |
| Min / Max words | 79 / 201 | 1 / 22 | 38 / 80 |
| Avg sentiment | 0.51 | 0.44 | 0.53 |
| Escalation rate | 40% (10/25) | 20% (4/20) | 41% (7/17) |

**Key Observations:**
- Gmail messages are **15x longer** than WhatsApp messages on average (648 vs 43 chars)
- Gmail customers provide rich context: names, workspace IDs, ticket history, repro steps
- WhatsApp customers give **minimal context** — many messages are 1-2 sentences with no error details
- Web Form falls cleanly in between, with semi-structured, medium-length messages
- WhatsApp has the **lowest average sentiment** (0.44) — frustrated users want fast fixes
- Gmail and Web Form have nearly identical escalation rates (~40%), while WhatsApp is only 20%

**Implication for Agent Design:**
- The agent needs **channel-specific response strategies**: detailed email replies, short chat replies, structured web-form acknowledgments
- For WhatsApp, the agent must be aggressive about **asking clarifying questions** since input is sparse
- For Gmail, the agent can usually resolve in a single response because context is sufficient

### Category Distribution (All Channels)

| Category | Count | % | Typical Escalation? |
|----------|-------|---|---------------------|
| how-to | 17 | 27% | Rarely (0/17) |
| bug-report | 12 | 19% | Sometimes (6/12) |
| billing | 9 | 15% | Usually (5/9) |
| technical | 8 | 13% | Rarely (1/8) |
| account | 7 | 11% | Often (5/7) |
| complaint | 3 | 5% | Always (3/3) |
| feature-request | 3 | 5% | Never (0/3) |
| feedback | 3 | 5% | Rarely (1/3) |

**Key Observations:**
- **how-to questions** are the largest category (27%) and NEVER need escalation — these are the AI's bread and butter
- **billing** tickets escalate 56% of the time — refunds, disputes, pricing all need humans
- **complaints** always escalate — angry customers need human empathy
- **bug-report** is split: common bugs (sync, cache) are handleable; data loss and security bugs escalate
- **account** issues escalate 71% of the time — 2FA lockouts, GDPR, ownership transfers are sensitive

**Implication for Agent Design:**
- The agent should be **highly confident** on how-to and feature-request categories
- Billing should trigger **mandatory escalation checks** (refund? dispute? negotiation?)
- Complaints need **sentiment analysis** before response generation

### Sentiment Distribution

| Bucket | Count | Description |
|--------|-------|-------------|
| Angry (0.0-0.2) | 8 (13%) | ALL CAPS, profanity, threats to leave, refund demands |
| Frustrated (0.2-0.4) | 16 (26%) | Repeated issues, sync problems, lost work |
| Neutral (0.4-0.6) | 25 (40%) | Standard questions, bug reports, factual tone |
| Positive (0.6-0.8) | 12 (19%) | Polite how-to questions, genuine curiosity |
| Happy (0.8-1.0) | 1 (2%) | Positive feedback, love-the-product messages |

**Key finding:** Escalated tickets have avg sentiment of **0.36** vs **0.56** for non-escalated. Sentiment < 0.3 is a strong escalation signal.

### Escalation Analysis

**Overall:** 21/62 tickets (34%) need escalation

**Escalation Triggers Found:**
1. **Billing disputes / refunds** — 5 tickets (always escalate)
2. **Data loss / integrity** — 4 tickets (missing tasks, sync failures losing data)
3. **Legal / compliance** — 3 tickets (GDPR deletion, SOC 2 reports, data residency + DPA)
4. **Security concerns** — 2 tickets (permission bypass, 2FA lockout for admin)
5. **Angry / churn risk** — 3 tickets (ALL CAPS, competitor mentions, repeat complaints)
6. **Account management** — 2 tickets (ownership transfer, custom invoicing)
7. **Human requested** — 1 ticket (explicit "talk to a real person")
8. **Performance / infrastructure** — 2 tickets (Gantt view, dashboard degradation)

**Implication:** The agent needs at minimum 8 distinct escalation detection rules, not just sentiment-based.

### Edge Cases Identified

| ID | Channel | Edge Case Type | Challenge |
|----|---------|---------------|-----------|
| TF-0038 | WhatsApp | Just "hi" — greeting only | No actionable content. Agent must greet and prompt. |
| TF-0039 | WhatsApp | Just "👍" — emoji only | Ambiguous. Could mean "thanks" or "ok". Need graceful handling. |
| TF-0026 | WhatsApp | "cant login help" — 3 words | Minimal context. Must ask clarifying questions. |
| TF-0032 | WhatsApp | "getting this error see screenshot" | References attachment that doesn't exist. Must ask for re-send. |
| TF-0045 | WhatsApp | ALL CAPS angry rant | Extreme negative sentiment. No specific issue stated. |
| TF-0061 | Web Form | Spam/nonsensical | Must detect and reject spam without engaging. |
| TF-0025 | Gmail | Multi-issue (login + sync + missing tasks) | Single ticket with 3+ distinct problems. Agent must address each. |
| TF-0016 | Gmail | Repeat contact (3rd time) | Historical context needed. Agent shouldn't re-suggest failed solutions. |
| TF-0020 | Gmail | Multi-part question (4 sub-questions) | Must answer each sub-question individually. |

**Implication:** The agent needs:
- A "clarification" flow for minimal-context messages
- A spam/noise detector
- Multi-issue decomposition for complex tickets
- Historical awareness (or at least a flag for repeat contacts)

### Top Keywords / Topics

The most frequently referenced product areas across all tickets:
1. **taskflow / tasks / task** (91 mentions) — Core product references
2. **workspace** (21) — Account-level operations
3. **sync** (10) — Web↔mobile sync is a pain point
4. **integration / slack** (19) — Integration issues are common
5. **pro / plan** (24) — Plan-related inquiries
6. **time** (14) — Time tracking questions

### Open Questions

1. **Multi-turn conversations:** WhatsApp inherently requires back-and-forth. How many turns should the agent support before escalating?
2. **Repeat customer detection:** How do we identify that ticket TF-0016 is a 3rd contact about the same issue?
3. **Confidence calibration:** What threshold should we use? Our escalation rules say < 0.6 flags for review, < 0.4 escalates immediately.
4. **Spam detection:** Should we use a keyword blocklist, or something more sophisticated?
5. **Multi-issue decomposition:** When a customer reports 3 issues in one email, should we create separate tickets or handle all in one response?
6. **Attachment handling:** 3 tickets reference screenshots. The agent needs to gracefully handle "I attached a screenshot" when none exists.
7. **Non-English messages:** Not present in sample data, but product-docs mention EU/India customers. Need a language detection strategy.

---

## Entry 2 — Prototype v0.1 (Keyword Matching Agent)

- **Date:** 2026-02-16
- **Experiment:** Build a minimal agent using keyword matching against product-docs.md to generate responses, with rule-based escalation detection.
- **Approach:** Simple text search over product docs, channel-aware response formatting, keyword-based escalation triggers.
- **See:** `src/agent/prototype.py`

### Architecture

The prototype consists of 5 components:

| Component | Technique | Role |
|-----------|-----------|------|
| `KnowledgeBase` | Keyword search over product-docs.md sections (H2/H3 split, title matches weighted 3x) | Finds relevant documentation |
| `EscalationEngine` | Regex pattern matching across 8 categories + sentiment thresholds + ALL CAPS detection | Decides if a ticket needs human review |
| `IntentDetector` | Keyword-based classification into 12 intent types | Determines what the customer is asking about |
| `ResponseFormatter` | Channel-specific templates (Gmail/WhatsApp/Web Form) matching brand-voice.md | Formats output per channel |
| `CustomerSuccessAgent` | Orchestrator: intent → escalation → search → confidence → response → format | Main pipeline |

### Test Results — 5 Selected Tickets

| Ticket | Channel | Category | Intent Detected | Confidence | Escalation | Match? |
|--------|---------|----------|-----------------|------------|------------|--------|
| TF-0022 | Gmail | how-to | how_to | 0.75 | no (expected: no) | CORRECT |
| TF-0029 | WhatsApp | bug-report | mobile_issue | 0.50 | no (expected: no) | CORRECT |
| TF-0006 | Gmail | billing | billing_inquiry | 0.45 | YES (expected: YES) | CORRECT |
| TF-0045 | WhatsApp | complaint | general_inquiry | 0.20 | YES (expected: YES) | CORRECT |
| TF-0038 | WhatsApp | edge-case | greeting | 0.50 | no (expected: no) | CORRECT |

**Selected test accuracy:** 5/5 (100%)
**Average confidence:** 0.48

### Test Results — Full Dataset (62 Tickets)

**Escalation accuracy:** 57/62 (92%)

#### False Positive (1 ticket — agent escalated but shouldn't have)

| Ticket | Channel | Issue | Root Cause |
|--------|---------|-------|------------|
| TF-0020 | Gmail | API rate limits question | Message contained the word "legal" in context of "legal entity," triggering the legal escalation regex pattern |

**Fix needed:** The `\blegal\b` pattern is too broad. Should require legal *action* context (e.g., `legal\s*(action|team|department|counsel)` or co-occurrence with lawsuit/GDPR/compliance keywords).

#### False Negatives (4 tickets — agent should have escalated but didn't)

| Ticket | Channel | Issue | Why Missed |
|--------|---------|-------|------------|
| TF-0002 | Gmail | 2FA lockout for enterprise admin | No escalation pattern for "2FA lockout" combined with enterprise plan. The `\blocked\s*out\b` pattern exists in IntentDetector but not in EscalationEngine. |
| TF-0005 | Gmail | Gantt view critical bug (enterprise) | No pattern to detect enterprise + critical severity + feature-breaking bugs. The word "critical" alone isn't in any escalation rule. |
| TF-0052 | WhatsApp | Offline sync causing data loss (recurring) | "Data loss" isn't an explicit escalation pattern. The existing `data\s*breach` is too specific. Need a broader `data\s*loss` or `missing\s*(tasks|data|files)` pattern. |
| TF-0059 | Web Form | Data export stuck for 3 days | "Stuck" and "export" aren't escalation triggers. Need to detect prolonged unresolved issues (time-based signals like "3 days," "a week," "still waiting"). |

### Response Quality Observations

| Area | Finding | Severity |
|------|---------|----------|
| **Doc relevance** | TF-0022 (recurring tasks how-to) returned FAQ about "Board vs List view" instead of the actual recurring tasks section. Keyword overlap was insufficient. | Medium — wrong answer served |
| **WhatsApp truncation** | TF-0029 (mobile crash) response was truncated to "1." with no content after it. The 280-char limit + sentence-based splitting cut too aggressively. | High — broken response |
| **Greeting handling** | TF-0038 ("hi") correctly detected as greeting, responded with "How can I help you today?" — appropriate for WhatsApp. | Good |
| **Escalation responses** | TF-0006 (refund) and TF-0045 (angry) both generated appropriate escalation acknowledgments with correct SLA based on plan tier. | Good |
| **Confidence calibration** | Confidence scores ranged 0.20–0.75 across the 5 test tickets. Escalated tickets correctly had lower confidence. Non-escalated easy tickets had higher confidence. | Acceptable |

### Key Takeaways

1. **Keyword search is surprisingly effective for escalation** — 92% accuracy with simple regex patterns is a strong baseline.
2. **Keyword search is mediocre for response generation** — The doc retrieval often returns tangentially related sections rather than the best match. A semantic/embedding search would significantly improve this.
3. **Channel formatting works well** — Gmail responses are structured with greeting/closing, WhatsApp is short, Web Form includes ticket IDs. Brand voice compliance is reasonable.
4. **Biggest gaps are in escalation edge cases** — Enterprise severity, data loss signals, and time-based frustration indicators all need additional rules.
5. **WhatsApp truncation logic is fragile** — Sentence splitting on ". " is naive and can produce broken responses. Needs smarter truncation.

### Next Steps (if continuing prototype iteration)

1. Add escalation patterns: `2fa.*lockout`, `data\s*loss`, `critical.*bug`, `\d+\s*days.*waiting`
2. Narrow the `\blegal\b` pattern to avoid false positives
3. Replace keyword search with TF-IDF or embedding-based search for doc retrieval
4. Fix WhatsApp truncation to never cut mid-sentence or produce empty numbered lists
5. Add multi-issue decomposition for complex tickets like TF-0025 (3 issues in one email)

---

## Entry 3 — Prototype v0.2 (TF-IDF + Enhanced Escalation + Sentiment Analysis)

- **Date:** 2026-02-16
- **Experiment:** Iterate on prototype v0.1 by fixing all 5 identified issues and adding sentiment analysis.
- **See:** `src/agent/prototype.py`

### What Changed (v0.1 → v0.2)

| Area | v0.1 | v0.2 |
|------|------|------|
| **Doc retrieval** | Naive keyword count | TF-IDF scoring with IDF weights and title boost |
| **Escalation patterns** | 4 ALWAYS + 3 LIKELY categories | 4 ALWAYS + 8 LIKELY categories (added data_loss, account_lockout, stuck_operations, critical_enterprise_bug, repeat_contact) |
| **"legal" pattern** | `\blegal\b` (too broad) | Requires legal *action* context: `lawyer`, `attorney`, `sue`, `legal action/threat/dispute`, or compliance keywords (GDPR, SOC 2, CCPA) |
| **Billing patterns** | Required `charged + twice/incorrectly/wrong` | Added `charged + never upgraded/authorized` and `unauthorized/unexpected charge` |
| **Sentiment** | Used ground-truth `ticket.sentiment` field | New `SentimentAnalyzer` class: keyword-based, negation-aware, intensifier-aware, ALL CAPS detection, -1.0 to +1.0 scale |
| **WhatsApp truncation** | Split on `(?<=[.!?])\s+` (broke on numbered lists) | Newline-aware splitting + negative lookbehind for `\d\.` to preserve numbered list items |
| **Greeting/edge cases** | Basic regex `^(hi|hello|hey)$` | Expanded patterns + emoji-only handling + channel-specific responses (wave emoji on WhatsApp) |
| **Spam detection** | None | New `spam` intent with pattern matching for buy/click/guaranteed keywords |
| **Channel formatting** | Basic greeting + body + closing | Sentiment-driven empathy selection, ticket reference in emails, improved structure |

### Test Results — Full Dataset (62 Tickets)

**Escalation accuracy: 61/62 (98%)** — up from 57/62 (92%) in v0.1

| Metric | v0.1 | v0.2 | Delta |
|--------|------|------|-------|
| Correct escalation decisions | 57/62 (92%) | 61/62 (98%) | +6% |
| False positives | 1 (TF-0020) | 0 | Fixed |
| False negatives | 4 | 1 | Fixed 3/4 + new fix for TF-0031 |

### Previously-Failing Tickets — Now Fixed

| Ticket | Issue in v0.1 | v0.2 Fix | Result |
|--------|--------------|----------|--------|
| TF-0020 | "legal" keyword false positive | `\blegal\b` replaced with legal-action-context patterns | CORRECT (no longer escalates) |
| TF-0002 | 2FA lockout not detected | Added `account_lockout` category with 2FA/authenticator/recovery-code patterns | CORRECT (now escalates) |
| TF-0005 | Enterprise critical bug missed | Added `enterprise + critical priority` contextual rule + sentiment-based escalation | CORRECT (now escalates) |
| TF-0052 | Data loss not detected | Added `data_loss` category with lost/disappeared/vanished/missing patterns | CORRECT (now escalates) |
| TF-0059 | Stuck export not detected | Added `stuck_operations` with widened range and "still showing as Processing" pattern | CORRECT (now escalates) |
| TF-0031 | Unexpected charge on free plan | Added `charged + never upgraded` and `unauthorized charge` billing patterns | CORRECT (now escalates) |

### Remaining Issue (1 false negative)

| Ticket | Channel | Issue | Why Missed |
|--------|---------|-------|------------|
| TF-0015 | Gmail | Enterprise dashboard performance degradation (150 projects, 12K tasks) | Message describes dashboard as "nearly unusable" and "affects all users in our workspace" but these phrases are ~100 characters apart — too far for regex `.{0,30}` proximity matching. Requires full-context NLP or a compound rule like "enterprise + performance keywords + affects-all-users anywhere in message". |

### Sentiment Analysis Results

| Metric | Value |
|--------|-------|
| Mean absolute error (vs ground truth) | 0.43 |
| Detected range | -1.00 to +1.00 |
| Direction accuracy (pos/neg/neutral agreement) | ~75% |

**Observations:**
- The keyword-based sentiment analyzer tends toward extreme values (-1.0 or +1.0) because a single strong word dominates the score. Ground truth uses a more nuanced 0-1 scale.
- Negative sentiment detection is stronger than positive (negative words have higher weights and ALL CAPS detection adds a large penalty).
- Messages with technical language but neutral tone get scored as negative because words like "error," "stuck," "crash" are in the negative lexicon — these are factual descriptors, not emotional signals.
- Sentiment correctly drives escalation in cases like TF-0005 and TF-0045 where pattern matching alone wasn't sufficient.

### Response Quality Observations

| Area | v0.1 | v0.2 |
|------|------|------|
| **WhatsApp truncation** | Broke on numbered lists ("4." dangling) | Clean truncation at list item boundaries (steps 1-3 shown, "Want me to explain more?" appended) |
| **Doc relevance for TF-0022** | Returned FAQ about Board vs List view | Returns Task Management section (closer, but still general — not the recurring tasks FAQ Q20 specifically) |
| **Empathy in negative-sentiment tickets** | Same empathy for all tickets | Sentiment-driven: frustrated customers get "I completely understand your frustration" while positive ones get "Thanks for reaching out!" |
| **TF-0005 escalation response** | No escalation (false negative) | Correctly escalates with "connecting you with a senior member" and 1-hour SLA (enterprise) |
| **Spam handling (TF-0061)** | Treated as normal ticket | Detected as spam, auto-closed, no response sent |
| **Duplicate empathy (TF-0005)** | N/A | When escalation + negative sentiment combine, the empathy phrase is duplicated ("I completely understand..." appears twice). Needs dedup logic. |

### Key Takeaways

1. **TF-IDF is a clear improvement over naive keyword counting** — better section ranking with IDF weighting, though still doesn't achieve semantic understanding.
2. **The expanded escalation rules handled all previously-missed cases** — contextual rules (enterprise + critical, sentiment thresholds) catch cases that single-pattern matching misses.
3. **Sentiment analysis is useful as an escalation signal** but the keyword approach has too coarse a granularity for nuanced scoring. Words like "error" and "bug" shouldn't carry the same negative weight as "garbage" and "useless."
4. **98% escalation accuracy is a strong baseline** — the remaining 2% (TF-0015) requires context-level understanding that regex can't provide.
5. **Response generation is the weakest link** — Escalation decisions are now excellent, but the actual response content sometimes pulls wrong doc sections. This will be addressed in Phase 2 with LLM-based response generation.

### Known Issues to Fix in Next Iteration

1. **Duplicate empathy in escalation responses** — TF-0005 has "I completely understand your frustration" appearing twice (once from formatter, once from escalation response generator). Need to deduplicate.
2. **Doc retrieval for recurring tasks** — TF-0022 asks about recurring tasks but TF-IDF returns the Task Management section instead of FAQ Q20 ("Can I create recurring tasks?"). The word "recurring" has low IDF because it appears in few sections — need phrase-level matching.
3. **Sentiment granularity** — The -1 to +1 analyzer gives too many extreme scores. Need calibrated confidence bands or a more balanced scoring function.
4. **TF-0015 false negative** — Enterprise + "unusable" + "affects all users" should escalate. Needs a compound rule that checks for enterprise plan + performance-related keywords + scope indicators (all users, entire workspace) anywhere in the message.

---

## Entry 4 — Conversation Memory, State Tracking, and MCP Server

- **Date:** 2026-02-16
- **Experiment:** Add stateful multi-turn conversation tracking, cross-channel continuity, sentiment trending, and expose the agent as an MCP server with 6 tools.
- **See:** `src/agent/conversation_manager.py`, `src/agent/mcp_server.py`, `tests/test_conversation_flow.py`

### What Was Built

#### 1. ConversationManager (`conversation_manager.py`)

| Feature | Implementation |
|---------|---------------|
| **Per-customer tracking** | Email as primary ID, in-memory dict storage, UUID conversation IDs |
| **Conversation state** | Fields: conversation_id, customer_id, channel, started_at, last_message_at, status (active/resolved/escalated), messages[], topics_discussed[], sentiment_history[], resolution_status |
| **Cross-channel continuity** | Identity linking (email ↔ phone), `resolve_customer_id()` resolves any identifier to canonical email, `get_or_create_conversation()` reuses existing conversations across channels |
| **Sentiment trending** | Tracks per-message sentiment scores, detects consecutive negative messages (threshold: 3+), detects significant sentiment drops (threshold: -0.4 from first to current) |
| **Auto-escalation** | When 3+ consecutive messages are negative (< -0.2) or sentiment drops > 0.4 from first message, the system auto-escalates with reason |

#### 2. Prototype Integration

- `CustomerSuccessAgent` now accepts an optional `ConversationManager` in constructor
- New `handle_ticket_with_context()` method: creates/reuses conversations, records messages, checks sentiment trends, detects cross-channel context, and updates state after response
- `_generate_full_response()` prepends cross-channel context ("I see you contacted us earlier via gmail about integration issue...")
- Existing `handle_ticket()` remains functional for stateless/test use (backward compatible)

#### 3. MCP Server (`mcp_server.py`)

Built on MCP SDK v1.25.0 (`mcp.server.fastmcp.FastMCP`).

| Tool | Description | Key Behavior |
|------|-------------|-------------|
| `search_knowledge_base(query, max_results)` | TF-IDF search over product-docs.md | Returns ranked sections with relevance, truncated to 500 chars |
| `create_ticket(customer_email, name, subject, message, ...)` | Create + process a ticket | Runs full agent pipeline (intent, sentiment, escalation, response), stores in ConversationManager |
| `get_customer_history(customer_id)` | Cross-channel history lookup | Returns all conversations, topics, channels, sentiment trend, last contact date |
| `escalate_to_human(ticket_id, reason, urgency, category)` | Manual escalation with routing | Routes to correct team member from escalation-rules.md, updates conversation state |
| `send_response(ticket_id, message, channel)` | Channel-formatted response | Applies brand-voice formatting per channel, records in conversation history |
| `analyze_sentiment(text)` | Standalone sentiment analysis | Returns score (-1 to +1), label (positive/neutral/negative), confidence level |

Also exposes 4 MCP resources:
- `docs://product-docs` — Full product documentation
- `docs://escalation-rules` — Escalation rules and routing
- `docs://brand-voice` — Brand voice guidelines
- `stats://conversations` — Live conversation statistics

### Test Results

**61/61 tests passed** across 6 test groups:

| Test Group | Tests | Result |
|-----------|-------|--------|
| Multi-turn email conversation | 8 | All pass — conversation reuse, message history, topic tracking |
| Cross-channel continuity | 8 | All pass — channel switching detected, conversation linked, topics preserved |
| Sentiment trending & auto-escalation | 8 | All pass — sentiment declines from +1.0 to -1.0 over 4 messages, auto-escalation triggers |
| ConversationManager unit tests | 16 | All pass — CRUD, identity linking, channel switching, resolution, escalation |
| MCP Tool direct invocation | 15 | All pass — all 6 tools produce correct outputs |
| Conversation summary & stats | 6 | All pass — multi-customer stats, escalation routing |

**Escalation accuracy preserved:** 61/62 (98%) on the 62-ticket dataset (unchanged from v0.2).

### Key Insights

1. **Cross-channel escalation interaction:** When a customer follows up on a different channel, the "repeat contact" escalation patterns often fire (e.g., "still not working"), which is actually correct behavior — a customer switching channels usually indicates frustration.

2. **Conversation reuse vs. new conversations:** The `get_or_create_conversation` method reuses conversations in `active` or `escalated` status. Only `resolved` conversations trigger a new one. This correctly models real support workflows where escalated issues still need follow-up.

3. **WhatsApp escalation format constraint:** When a cross-channel follow-up triggers escalation on WhatsApp, the short escalation template overrides the cross-channel context. This is acceptable because the WhatsApp 300-char limit doesn't allow both — and the escalation acknowledgment is more important than the context reference.

4. **Sentiment trending is coarse but effective:** The keyword-based sentiment analyzer gives extreme scores (-1.0 or +1.0), making the "consecutive negative" threshold easy to hit. With an LLM-based sentiment analyzer in Phase 3, this would be more nuanced.

5. **MCP server as integration layer:** The MCP tools provide a clean abstraction over the agent internals. An LLM client can use `create_ticket` → `get_customer_history` → `escalate_to_human` as a natural workflow without knowing about the underlying pattern matching or TF-IDF scoring.

### Architecture Diagram

```
                    ┌─────────────────────────────────────┐
                    │          MCP Server                  │
                    │  (mcp_server.py — FastMCP)           │
                    ├─────────────────────────────────────┤
                    │  Tools:                              │
                    │  ├── search_knowledge_base           │
                    │  ├── create_ticket ─────────┐        │
                    │  ├── get_customer_history    │        │
                    │  ├── escalate_to_human       │        │
                    │  ├── send_response           │        │
                    │  └── analyze_sentiment       │        │
                    └────────────────────────────┼────────┘
                                                 │
                    ┌────────────────────────────▼────────┐
                    │     CustomerSuccessAgent             │
                    │     (prototype.py)                   │
                    ├─────────────────────────────────────┤
                    │  ├── SentimentAnalyzer               │
                    │  ├── IntentDetector                  │
                    │  ├── EscalationEngine                │
                    │  ├── KnowledgeBase (TF-IDF)          │
                    │  └── ResponseFormatter               │
                    └────────────────────────────┬────────┘
                                                 │
                    ┌────────────────────────────▼────────┐
                    │     ConversationManager              │
                    │     (conversation_manager.py)        │
                    ├─────────────────────────────────────┤
                    │  ├── Per-customer conversation store  │
                    │  ├── Cross-channel identity linking   │
                    │  ├── Sentiment trend tracking         │
                    │  └── Auto-escalation logic            │
                    └─────────────────────────────────────┘
```

### Remaining Work for Phase 2

1. **Persistent storage** — Replace in-memory dicts with SQLite (or PostgreSQL in Phase 3) for conversation state
2. **LLM-based response generation** — Replace keyword/TF-IDF doc retrieval with RAG (retrieval-augmented generation) for more natural responses
3. **Multi-turn context in responses** — Use conversation history to inform follow-up answers (e.g., don't repeat troubleshooting steps already tried)
4. **Attachment handling** — Detect and gracefully handle "see screenshot" references
5. **De-escalation flow** — Allow escalated conversations to return to the AI agent if the issue is resolved
6. **Rate limiting** — Prevent spam customers from creating excessive conversations

---

## Entry 5 — Phase 1 Complete: Incubation Summary

- **Date:** 2026-02-16
- **Status:** Phase 1 (Incubation) complete. Ready for Phase 2 transition.
- **See:** `specs/agent-skills.yaml`, `specs/customer-success-fte-spec.md`

### What Was Built

Over 4 iterations during Phase 1, we built a complete rule-based Customer Success Digital FTE:

| Iteration | Focus | Key Outcome |
|-----------|-------|-------------|
| Entry 1 | Ticket dataset analysis (62 tickets) | Identified 8 escalation trigger categories, channel patterns, edge cases |
| Entry 2 | Prototype v0.1 (keyword matching) | 92% escalation accuracy (57/62), 1 false positive, 4 false negatives |
| Entry 3 | Prototype v0.2 (TF-IDF + enhanced rules) | 98% accuracy (61/62), 0 false positives, 1 false negative |
| Entry 4 | Conversation memory + MCP server | Stateful multi-turn tracking, 6 MCP tools, 61/61 tests passing |

### Final Metrics

| Metric | Value |
|--------|-------|
| **Escalation accuracy** | 98% (61/62 tickets) |
| **False positives** | 0 |
| **False negatives** | 1 (TF-0015 — enterprise dashboard performance, requires NLP) |
| **Sentiment direction accuracy** | ~75% |
| **Integration tests** | 61/61 passing |
| **Skills identified** | 6 (knowledge retrieval, sentiment analysis, escalation decision, channel adaptation, customer identification, conversation continuity) |
| **MCP tools** | 6 (search_knowledge_base, create_ticket, get_customer_history, escalate_to_human, send_response, analyze_sentiment) |
| **MCP resources** | 4 (product-docs, escalation-rules, brand-voice, conversation stats) |
| **Escalation categories** | 12 (4 ALWAYS + 8 LIKELY) |
| **Regex patterns** | ~60 across all categories |
| **Intent types** | 13 |
| **Channels supported** | 3 (Gmail, WhatsApp, Web Form) |

### Key Discoveries

1. **Keyword/regex escalation is surprisingly effective** — 98% accuracy with ~60 regex patterns is a strong baseline. The rule-based approach correctly handles billing, legal, security, account, data loss, 2FA lockout, churn risk, and angry customer detection. Only 1 ticket (TF-0015) needs NLP-level understanding.

2. **TF-IDF is adequate for doc retrieval but not great** — Works well when the query keywords overlap with section titles (e.g., "Slack integration" → Integrations section). Fails when the relevant doc uses different terminology (e.g., "recurring tasks" → FAQ Q20, but TF-IDF returns the general Task Management section). Embeddings will fix this in Phase 2.

3. **Keyword sentiment has coarse granularity** — The -1.0 to +1.0 analyzer gives extreme scores because a single strong word dominates. Technical words ("error", "bug", "crash") score negative even when used factually. Direction accuracy is ~75% but mean absolute error is 0.43. LLM sentiment will provide much better calibration.

4. **Cross-channel continuity is critical** — Customers who switch channels mid-conversation (email → WhatsApp) are often frustrated, and the "repeat contact" escalation pattern correctly fires. The identity linking system (email ↔ phone) enables seamless conversation reuse.

5. **WhatsApp is the hardest channel** — Messages average only 43 characters (9 words), giving the agent minimal context. Truncation logic must be sentence-boundary-aware to avoid broken responses. Numbered list items need special handling (negative lookbehind for `\d.`).

6. **Escalation routing is straightforward** — The routing table from escalation-rules.md maps cleanly to 7 categories with named contacts. SLA varies by plan (enterprise: 1hr, pro: 4hr, free: 24hr).

7. **Conversation state machine needs "escalated + active" hybrid** — When a conversation is escalated, follow-up messages should still be captured in the same conversation. The `get_or_create_conversation()` method correctly reuses escalated conversations rather than creating new ones.

8. **MCP provides a clean integration layer** — The 6 MCP tools abstract away all agent internals. An LLM client can use `create_ticket` → `get_customer_history` → `escalate_to_human` as a natural workflow without understanding TF-IDF, regex patterns, or conversation state machines.

### Edge Cases Documented

| # | Edge Case | Ticket | Resolution |
|---|-----------|--------|------------|
| 1 | "legal entity" false positive | TF-0020 | Narrowed `\blegal\b` to require legal-action context |
| 2 | 2FA lockout not detected | TF-0002 | Added `account_lockout` escalation category |
| 3 | Enterprise critical bug missed | TF-0005 | Added `critical_enterprise_bug` with plan+severity compound rule |
| 4 | Data loss not detected | TF-0052 | Added `data_loss` category with lost/disappeared/vanished patterns |
| 5 | Stuck export not detected | TF-0059 | Added `stuck_operations` with widened proximity and "still showing" pattern |
| 6 | Unauthorized charge missed | TF-0031 | Added "charged + never upgraded" and "unauthorized charge" billing patterns |
| 7 | WhatsApp numbered-list truncation | TF-0029 | Sentence-boundary regex with negative lookbehind for `\d.` |
| 8 | Greeting-only messages | TF-0038 | Expanded greeting patterns + channel-specific responses |
| 9 | Emoji-only messages | TF-0039 | Graceful acknowledgment handling |
| 10 | Spam/nonsensical input | TF-0061 | Spam intent detection + auto-close |
| 11 | Enterprise dashboard perf (OPEN) | TF-0015 | Requires NLP — "unusable" and "affects all users" too far apart for regex |

### Phase 1 Deliverables

| Deliverable | File | Lines |
|------------|------|-------|
| Agent prototype v0.2 | `src/agent/prototype.py` | ~1200 |
| Conversation manager | `src/agent/conversation_manager.py` | ~350 |
| MCP server | `src/agent/mcp_server.py` | ~300 |
| Integration tests | `tests/test_conversation_flow.py` | ~560 |
| Agent skills definition | `specs/agent-skills.yaml` | ~575 |
| FTE specification | `specs/customer-success-fte-spec.md` | ~415 |
| Discovery log | `specs/discovery-log.md` | This file |
| Product documentation | `context/product-docs.md` | 605 |
| Escalation rules | `context/escalation-rules.md` | 226 |
| Brand voice guidelines | `context/brand-voice.md` | ~100 |
| Company profile | `context/company-profile.md` | ~80 |
| Sample tickets | `context/sample-tickets.json` | 62 tickets |

### Ready for Phase 2 Transition

**What works well (keep as-is):**
- Escalation engine (98% accuracy) — enhance with NLP for the remaining 2%
- Conversation state machine — add persistent storage
- MCP tool interface — add more tools as capabilities grow
- Channel formatting templates — refine with real user feedback

**What needs replacement in Phase 2:**
- TF-IDF → embedding-based RAG for doc retrieval
- Keyword sentiment → LLM-based sentiment analysis
- Template responses → LLM-generated natural language responses
- In-memory storage → SQLite (then PostgreSQL in Phase 3)

**New capabilities for Phase 2:**
- Attachment detection and handling
- Multi-issue decomposition
- Clarifying question generation for sparse WhatsApp messages
- Duplicate empathy deduplication in escalation responses
- NLP compound rule for TF-0015-type edge cases
