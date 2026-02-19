# Edge Cases — Customer Success Digital FTE

**Purpose:** Catalog all edge cases discovered during Phase 1 (Incubation) and anticipate new edge cases for Phase 3 (Production).

**Source:** Discovery log entries 1-5, test results from 62-ticket dataset, and test_conversation_flow.py (61 tests).

---

## 1. Successfully Handled Edge Cases

These 10 edge cases were discovered and resolved during incubation. Each has a tested solution.

### EC-001: "Legal Entity" False Positive
- **ID:** EC-001
- **Channel:** Gmail
- **Ticket:** TF-0020
- **Description:** Customer message contained "legal entity" in the context of a business question, triggering the `\blegal\b` escalation regex pattern.
- **Example Input:** "What API rate limits apply per legal entity in our organization?"
- **Expected Behavior:** No escalation — this is a how-to question about API usage.
- **Previous Behavior:** Escalated incorrectly (false positive).
- **Resolution:** Replaced `\blegal\b` with context-specific patterns: `legal action/threat/team/department/counsel/dispute/proceeding/notice`, plus standalone `lawyer`, `attorney`, `sue`, `subpoena`. Compliance keywords (GDPR, SOC 2, CCPA, DPA) remain standalone triggers.
- **Test Result:** Fixed in v0.2. No longer escalates.

### EC-002: 2FA Lockout Not Detected
- **ID:** EC-002
- **Channel:** Gmail
- **Ticket:** TF-0002
- **Description:** Enterprise admin locked out after 2FA phone was lost. No escalation pattern matched because "2FA lockout" wasn't a recognized trigger.
- **Example Input:** "I've been locked out of my admin account after losing my phone with the authenticator app. My recovery codes aren't working either."
- **Expected Behavior:** Escalate — enterprise admin lockout is a critical account issue.
- **Previous Behavior:** Not escalated (false negative).
- **Resolution:** Added `account_lockout` escalation category with patterns: `locked out + admin/workspace/enterprise`, `2fa + lost/locked/cannot`, `authenticator + lost/broken/stolen`, `recovery codes + lost/missing`.
- **Test Result:** Fixed in v0.2. Correctly escalates.

### EC-003: Enterprise Critical Bug Missed
- **ID:** EC-003
- **Channel:** Gmail
- **Ticket:** TF-0005
- **Description:** Enterprise customer reported Gantt view was completely non-functional for their team. No compound rule existed for "enterprise + critical + affects team."
- **Example Input:** "The Gantt view has been completely unusable for our team of 50. It just shows a spinner and never loads."
- **Expected Behavior:** Escalate — enterprise customer with a feature-breaking bug affecting all users.
- **Previous Behavior:** Not escalated (false negative).
- **Resolution:** Added `critical_enterprise_bug` category: `(feature|view|page|board|dashboard).{0,30}(not load|stuck on spinner|timeout|unusable).{0,40}(team|organization|users|workspace)` + `(entire|whole) (team|organization) + (block|impact|affect)`.
- **Test Result:** Fixed in v0.2. Correctly escalates.

### EC-004: Data Loss Not Detected
- **ID:** EC-004
- **Channel:** WhatsApp
- **Ticket:** TF-0052
- **Description:** Offline sync was causing data loss (tasks disappeared). The existing `data breach` pattern was too specific — needed broader "data loss" detection.
- **Example Input:** "offline sync losing tasks"
- **Expected Behavior:** Escalate — data loss is a critical issue.
- **Previous Behavior:** Not escalated (false negative).
- **Resolution:** Added `data_loss` category: `data loss`, `lost (work|data|tasks|files|changes)`, `(tasks|data|files) (disappeared|vanished|gone|missing|deleted)`, standalone `disappeared`/`vanished`.
- **Test Result:** Fixed in v0.2. Correctly escalates.

### EC-005: Stuck Export Not Detected
- **ID:** EC-005
- **Channel:** Web Form
- **Ticket:** TF-0059
- **Description:** Data export stuck for 3+ days, showing "Processing" status. No pattern matched stuck operations with time indicators.
- **Example Input:** "Data export has been showing as 'Processing' for more than 24 hours now."
- **Expected Behavior:** Escalate — stuck operation for extended time indicates a system issue.
- **Previous Behavior:** Not escalated (false negative).
- **Resolution:** Added `stuck_operations` category with widened proximity (`.{0,60}`) and patterns: `still (show|display|say) + (processing|pending|waiting|queued)`, `more than \d+ (hour|day)`, `(stuck|hanging|frozen) for \d+ (hour|day)`.
- **Test Result:** Fixed in v0.2. Correctly escalates.

### EC-006: Unauthorized Charge Missed
- **ID:** EC-006
- **Channel:** WhatsApp
- **Ticket:** TF-0031
- **Description:** Customer on free plan was charged $12 but never upgraded. Existing billing patterns required "charged twice/incorrectly/wrong" but customer said "charged" + "never upgraded."
- **Example Input:** "I was charged $12 but im on free plan?? i never upgraded"
- **Expected Behavior:** Escalate — billing dispute (unauthorized charge).
- **Previous Behavior:** Not escalated (false negative).
- **Resolution:** Added billing patterns: `charged.{0,40}(never (upgraded|signed|agreed|authorized))` and `(unauthorized|unexpected|surprise) (charge|billing|payment)`.
- **Test Result:** Fixed in v0.2. Correctly escalates.

### EC-007: WhatsApp Numbered-List Truncation
- **ID:** EC-007
- **Channel:** WhatsApp
- **Ticket:** TF-0029
- **Description:** WhatsApp response with numbered steps was truncated after "4." because the sentence-boundary regex `(?<=[.!?])\s+` treated "4." as a sentence ending.
- **Example Input:** Agent response with steps "1. Do this  2. Do that  3. Then this  4. Finally..."
- **Expected Behavior:** Truncate at a full sentence boundary, not mid-list.
- **Previous Behavior:** "4." left dangling with no content after it.
- **Resolution:** Changed regex to `(?<=[.!?])(?<!\d\.)(?<!\d\d\.)\s+` (negative lookbehind for `\d.`). Added newline-based chunking for list items as separate units.
- **Test Result:** Fixed in v0.2. Clean truncation at list item boundaries.

### EC-008: Greeting-Only Messages
- **ID:** EC-008
- **Channel:** WhatsApp
- **Ticket:** TF-0038
- **Description:** Customer sent just "hi" with no actionable content. Agent needs to greet and prompt for details.
- **Example Input:** "hi"
- **Expected Behavior:** Respond with a friendly greeting and prompt for details.
- **Resolution:** Greeting intent detection with expanded patterns + channel-specific responses. WhatsApp gets wave emoji; Gmail gets "How can I help you today?"
- **Test Result:** Working since v0.1. Correctly handled.

### EC-009: Emoji-Only Messages
- **ID:** EC-009
- **Channel:** WhatsApp
- **Ticket:** TF-0039
- **Description:** Customer sent only "👍" — ambiguous (could mean "thanks" or "ok"). Agent needs graceful handling.
- **Example Input:** "👍"
- **Expected Behavior:** Treat as acknowledgment, respond gracefully.
- **Resolution:** `unclear` intent catches messages with <= 4 chars or no alphabetic characters. Response: "Is there anything I can help you with today?"
- **Test Result:** Working since v0.2. Correctly handled.

### EC-010: Spam / Nonsensical Input
- **ID:** EC-010
- **Channel:** Web Form
- **Ticket:** TF-0061
- **Description:** Spam submission with "buy cheap" / "click now" / "guaranteed returns" language.
- **Example Input:** "Buy cheap VPN guaranteed returns click now www dot bestdeal dot biz"
- **Expected Behavior:** Detect as spam, auto-close, send no substantive response.
- **Resolution:** Added `spam` intent with keyword patterns. When spam is detected: `[SPAM DETECTED — No response sent. Ticket auto-closed.]`
- **Test Result:** Working since v0.2. Correctly detected and rejected.

---

## 2. Edge Cases That Need Production Attention

These edge cases were identified during incubation but not fully resolved. They require production-level solutions.

### EC-011: Enterprise Dashboard Performance (OPEN — False Negative)
- **ID:** EC-011
- **Channel:** Gmail
- **Ticket:** TF-0015
- **Severity:** Medium — 1 of 62 tickets incorrectly handled
- **Description:** Enterprise customer reported dashboard "nearly unusable" with "affects all users in our workspace" — but these phrases are ~100 characters apart, exceeding the regex proximity matching window (`.{0,40}`).
- **Example Input:** "Our enterprise dashboard has become nearly unusable with 150 projects and 12,000 tasks. The page takes over 30 seconds to load and affects all users in our workspace."
- **Expected Behavior:** Escalate — enterprise + performance degradation + affects entire team.
- **Current Behavior:** Not escalated (false negative). Regex proximity matching can't bridge the gap.
- **Production Resolution:** LLM-based escalation judgment will handle this naturally. The system prompt includes "Enterprise customer + severity + affects team → escalate" as a LIKELY_ESCALATE rule. Alternatively, add a compound regex rule that checks for each signal independently (enterprise plan + "unusable"/"degraded" anywhere + "all users"/"entire workspace" anywhere).

### EC-012: Duplicate Empathy in Escalation Responses
- **ID:** EC-012
- **Channel:** Gmail
- **Ticket:** TF-0005
- **Severity:** Low — cosmetic issue
- **Description:** When a ticket triggers both escalation AND has negative sentiment, the empathy phrase appears twice: once from the sentiment-driven empathy opener and once from the escalation response body.
- **Example Output:** "Dear Sarah,\n\nI completely understand your frustration... I completely understand your frustration..."
- **Production Resolution:** Deduplicate by checking if the empathy phrase already appears in the response body before prepending the empathy opener. Or use a single empathy source (let the LLM handle it naturally).

### EC-013: Doc Retrieval for Recurring Tasks
- **ID:** EC-013
- **Channel:** Gmail
- **Ticket:** TF-0022
- **Severity:** Medium — wrong documentation returned
- **Description:** Customer asks "How do I set up recurring tasks?" but TF-IDF returns the general Task Management section instead of FAQ Q20 ("Can I create recurring tasks?"). The word "recurring" has low IDF because it appears in few sections, and the phrase "recurring tasks" isn't matched as a unit.
- **Production Resolution:** Vector embeddings will solve this — the semantic similarity between "set up recurring tasks" and "Can I create recurring tasks?" is high even though keyword overlap is low. Use FAISS or pgvector for embedding-based search.

### EC-014: Multi-Issue Decomposition
- **ID:** EC-014
- **Channel:** Gmail
- **Ticket:** TF-0025
- **Severity:** Medium — partial response
- **Description:** Customer reported 3 issues in one email: can't log in, sync isn't working, and tasks are missing. Agent detects the strongest intent (password_reset) and addresses only that one.
- **Current Behavior:** Responds only to the login issue.
- **Production Resolution:** LLM can naturally decompose multi-issue messages. System prompt instruction: "If the customer raises multiple issues in one message, address each one separately in your response. Number each issue."

### EC-015: Missing Attachment Reference
- **ID:** EC-015
- **Channel:** WhatsApp
- **Ticket:** TF-0032
- **Severity:** Low — graceful degradation
- **Description:** Customer says "getting this error see screenshot" but no screenshot is attached. Agent cannot see the referenced attachment.
- **Current Behavior:** Ignores the screenshot reference, responds based on text alone.
- **Production Resolution:** Detect phrases like "see screenshot", "attached image", "see attached" and respond: "I'd love to help! I wasn't able to see a screenshot in your message. Could you describe the error you're seeing, or try re-sending the screenshot?"

### EC-016: WhatsApp Cross-Channel Context Lost on Escalation
- **ID:** EC-016
- **Channel:** WhatsApp
- **Severity:** Low — functional but loses context
- **Description:** When a cross-channel follow-up triggers escalation on WhatsApp, the short escalation template (hardcoded in `_format_whatsapp()`) ignores the body parameter, so cross-channel context ("I see you contacted us earlier via gmail...") is lost.
- **Current Behavior:** WhatsApp escalation shows generic escalation message without cross-channel reference.
- **Production Resolution:** For WhatsApp escalations, include a brief cross-channel reference in the escalation template itself: "Hi {name}, I see you contacted us about this before. I'm connecting you with our team right now."

---

## 3. New Edge Cases for Production

These are edge cases that don't exist in the incubation environment but will arise in production with real users, real APIs, and real infrastructure.

### EC-017: Database Connection Failure
- **ID:** EC-017
- **Channel:** All
- **Severity:** Critical
- **Description:** PostgreSQL is unreachable (connection pool exhausted, network issue, DB crash).
- **Expected Behavior:** Return a graceful error to the customer: "We're experiencing a temporary issue. Please try again in a few minutes." Do NOT expose internal error details. Alert the ops team immediately.
- **Production Resolution:** Circuit breaker pattern (e.g., `tenacity` retry with exponential backoff). Fallback response that doesn't require DB. Health check endpoint for Kubernetes liveness probe.

### EC-018: LLM API Timeout or Rate Limit
- **ID:** EC-018
- **Channel:** All
- **Severity:** High
- **Description:** OpenAI API returns 429 (rate limit), 500 (server error), or request times out.
- **Expected Behavior:** Retry with backoff. If all retries fail, send a "We received your message and are processing it. You'll hear from us within [SLA]." Meanwhile, queue the ticket for retry.
- **Production Resolution:** Implement retry with exponential backoff (max 3 retries). Background job queue (Celery or asyncio task queue) for deferred processing. Alert if failure rate exceeds 5%.

### EC-019: Gmail API Token Expiry
- **ID:** EC-019
- **Channel:** Gmail
- **Severity:** High
- **Description:** OAuth 2.0 refresh token expires or is revoked. Agent can't read new emails or send responses.
- **Expected Behavior:** Detect auth failure, alert admin, queue incoming emails for processing once reauthorized.
- **Production Resolution:** Implement OAuth token refresh with monitoring. Alert ops team on 401 errors. Store tokens securely (not in code).

### EC-020: WhatsApp API Rate Limiting
- **ID:** EC-020
- **Channel:** WhatsApp
- **Severity:** Medium
- **Description:** WhatsApp Business API has rate limits on message sending. High-volume periods could trigger throttling.
- **Expected Behavior:** Queue outgoing messages and send in order. Never drop a response.
- **Production Resolution:** Message queue with rate-aware sender. Respect WhatsApp's per-phone-number limits. Implement backpressure.

### EC-021: Race Condition — Concurrent Messages from Same Customer
- **ID:** EC-021
- **Channel:** All
- **Severity:** Medium
- **Description:** Customer sends 2 messages rapidly before the first is processed. Both try to create/update the same conversation simultaneously.
- **Expected Behavior:** Both messages are recorded in order. No duplicate conversations. No lost messages.
- **Production Resolution:** Use database row-level locking (`SELECT ... FOR UPDATE`) on the conversation row. Process messages sequentially per customer (per-customer queue or distributed lock).

### EC-022: Webhook Replay / Duplicate Delivery
- **ID:** EC-022
- **Channel:** Gmail, WhatsApp
- **Severity:** Medium
- **Description:** Channel webhooks may deliver the same message twice (retry on timeout). Agent should not create duplicate tickets or send duplicate responses.
- **Expected Behavior:** Idempotent processing. Second delivery of the same message is a no-op.
- **Production Resolution:** Store message IDs (Gmail message ID, WhatsApp message ID) in a deduplication table. Check before processing. TTL-based cleanup of old message IDs.

### EC-023: Customer Sends Message During Escalation Processing
- **ID:** EC-023
- **Channel:** All
- **Severity:** Low
- **Description:** After a ticket is escalated, the customer sends a follow-up before the human agent responds. The AI agent needs to acknowledge without overriding the escalation.
- **Expected Behavior:** "Your request has been escalated to {team member}. They'll be in touch within {SLA}. I've added your latest message to the ticket so they can see it."
- **Production Resolution:** Check conversation status before generating a response. If status == "escalated", acknowledge and append to the escalated conversation rather than generating a new AI response.

### EC-024: Very Long Messages (> 10,000 characters)
- **ID:** EC-024
- **Channel:** Gmail, Web Form
- **Severity:** Low
- **Description:** Customer sends an extremely long email (e.g., pasting logs, stack traces, long complaint). This could exceed LLM context limits or inflate costs.
- **Expected Behavior:** Process the full message but truncate intelligently for LLM input. Preserve the first 2,000 chars (customer's description) and last 1,000 chars (often contains the specific ask).
- **Production Resolution:** Input sanitization with intelligent truncation. Store full message in DB but send summarized version to LLM. Flag very long messages for human review.

### EC-025: Non-English Messages
- **ID:** EC-025
- **Channel:** All
- **Severity:** Medium
- **Description:** Customer writes in a non-English language. Product docs and brand voice are English-only.
- **Example Input:** "No puedo acceder a mi cuenta" (Spanish: "I can't access my account")
- **Expected Behavior:** Detect language, attempt to respond in same language, or acknowledge and escalate with context.
- **Production Resolution:** Language detection (e.g., `langdetect` library or LLM identification). If supported language → LLM responds in that language. If unsupported → "We received your message. Let me connect you with a team member who can assist you in your language."

### EC-026: HTML/Markdown Injection in User Input
- **ID:** EC-026
- **Channel:** Web Form
- **Severity:** High (security)
- **Description:** Customer includes HTML tags, markdown, or script tags in their message that could be rendered unsafely in the support dashboard or responses.
- **Example Input:** `<script>alert('xss')</script>My tasks are missing`
- **Expected Behavior:** Sanitize all user input. Never render raw HTML from customer messages.
- **Production Resolution:** HTML sanitization on all input fields. Escape user content before storing and rendering. Content Security Policy headers on web dashboard.

### EC-027: PII in Logs
- **ID:** EC-027
- **Channel:** All
- **Severity:** High (compliance)
- **Description:** Customer messages may contain passwords, credit card numbers, or other PII. These must not appear in application logs.
- **Expected Behavior:** Redact PII from logs. Store full messages only in the encrypted database.
- **Production Resolution:** PII detection and redaction in logging pipeline. Use structured logging with separate fields for message content (excluded from log aggregation) and metadata (included). Encrypt messages at rest in PostgreSQL.

### EC-028: Conversation Timeout / Stale Conversations
- **ID:** EC-028
- **Channel:** All
- **Severity:** Low
- **Description:** Customer starts a conversation but never follows up. The conversation stays "active" indefinitely.
- **Expected Behavior:** Auto-resolve conversations after 72 hours of inactivity with a message: "I'm closing this ticket since I haven't heard back. Feel free to reach out anytime if you need further help!"
- **Production Resolution:** Background job that scans for conversations with `last_message_at` > 72 hours ago and status == "active". Auto-resolve with notification.
