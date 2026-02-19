# Escalation Rules — TaskFlow Customer Support

## Overview

Not every ticket should be handled autonomously by the AI agent. These rules define **when**, **how**, and **to whom** tickets should be escalated. The goal is to resolve as many tickets as possible without human intervention while ensuring complex, sensitive, or high-risk issues reach the right person quickly.

---

## Priority Levels

| Level | Response Time | Resolution Target | Description | Examples |
|-------|---------------|-------------------|-------------|----------|
| **Critical** | < 5 min | < 2 hours | Service outage, data loss, security breach | "The entire platform is down", "I think my data was deleted" |
| **High** | < 15 min | < 4 hours | Account lockout, billing errors, broken core features | "I can't log in", "I was charged twice", "Tasks are disappearing" |
| **Medium** | < 1 hour | < 24 hours | Non-critical bugs, integration issues, confusing UX | "Slack notifications aren't working", "Gantt view is glitching" |
| **Low** | < 4 hours | < 48 hours | Feature requests, general questions, feedback | "Can you add dark mode?", "How do I export data?" |

---

## ALWAYS Escalate — Mandatory Human Handoff

These scenarios **must always** be routed to a human agent. The AI should acknowledge receipt, set expectations, and hand off immediately.

### Billing & Financial
- **Refund requests** — Any request for money back, regardless of amount
- **Billing disputes** — Customer claims they were charged incorrectly (especially > $100)
- **Pricing negotiations** — "Can I get a discount?", "Can you match competitor pricing?"
- **Payment failures** — Customer reports repeated failed charges they want resolved
- **Invoice discrepancies** — Customer says the invoice doesn't match what they expected
- **Escalation contact:** Lisa Tanaka (billing@techcorp.io)

### Legal & Compliance
- **Data deletion requests** — GDPR "right to be forgotten", CCPA deletion requests
- **Legal threats** — "I'll sue", "My lawyer...", "This violates..."
- **Subpoena or legal discovery requests**
- **DPA (Data Processing Agreement) requests**
- **Compliance questions** — SOC 2, HIPAA, GDPR specifics beyond standard FAQ
- **Escalation contact:** Rachel Foster (legal@techcorp.io)

### Security
- **Suspected data breach** — "Someone accessed my account", "I see activity I don't recognize"
- **Vulnerability reports** — "I found a security bug"
- **Suspicious account activity** — Unrecognized logins, changed settings
- **Escalation contact:** James Okafor (security@techcorp.io)

### Account Management
- **Workspace deletion requests** — Permanent, irreversible actions
- **Ownership transfer issues** — Disputes about who owns a workspace
- **Enterprise contract modifications** — Changes to terms, custom agreements
- **Escalation contact:** Sarah Chen (cs-lead@techcorp.io)

---

## LIKELY Escalate — Use Judgment

These situations often need human intervention but the AI should attempt a first response before escalating.

### Negative Sentiment (Sentiment Score < 0.3)
- Customer is clearly angry, frustrated, or threatening to leave
- **Action:** Empathize, attempt to solve. If the customer remains upset after one response, escalate.
- **Signals:** ALL CAPS, profanity, "this is unacceptable", "I'm switching to [competitor]", "worst experience", "cancel my account"
- **Escalation contact:** Marcus Rivera (cs-lead@techcorp.io)

### Customer Explicitly Requests a Human
- "I want to talk to a real person"
- "Let me speak to a manager"
- "Can I talk to someone?"
- "Transfer me to a human"
- **Action:** Immediately acknowledge and escalate. Do NOT try to convince them to stay with the AI.
- **Response template:** "Of course! I'm connecting you with a member of our support team right now. They'll follow up within [timeframe based on their plan SLA]. In the meantime, is there anything quick I can help with?"

### Unable to Resolve After 2 Attempts
- If the AI has provided two different solutions and the customer confirms neither worked
- **Action:** Escalate to Senior Support Engineer with full conversation context
- **Escalation contact:** Priya Patel (engineering-support@techcorp.io)

### Security Concerns (Non-Critical)
- Password reset issues that don't resolve with standard flow
- 2FA lockouts that can't be resolved with backup codes
- Shared account concerns
- **Action:** Attempt standard troubleshooting first. Escalate if unresolved.

### Complex Technical Issues
- Multi-system issues (e.g., "My integration was working, then after I changed my Google account, nothing syncs and my tasks are duplicated")
- Issues that require database-level investigation
- Bugs that aren't documented in known issues
- **Action:** Gather detailed reproduction steps, then escalate with context
- **Escalation contact:** Priya Patel (engineering-support@techcorp.io)

### Customer Churn Risk
- Customer on annual plan approaching renewal and expressing dissatisfaction
- Enterprise customer with multiple unresolved tickets
- Customer mentions competitors by name ("I'm considering switching to Asana")
- **Action:** Attempt to resolve, then flag for Customer Success team
- **Escalation contact:** Sarah Chen (cs-lead@techcorp.io)

---

## NEVER Escalate Without Trying First

These categories should be fully handled by the AI agent. Only escalate if the standard process fails.

### Basic How-To Questions
- "How do I create a project?"
- "Where are my notification settings?"
- "How do I invite team members?"
- **Action:** Answer using product documentation. Provide step-by-step instructions. Include relevant links.
- **Escalate only if:** The documented steps don't match what the customer is seeing (possible UI change or bug).

### Feature Requests & Feedback
- "Can you add dark mode?"
- "It would be great if you supported [feature]"
- "I wish TaskFlow had [capability]"
- **Action:** Thank the customer, acknowledge the request, log it with the specific feature and use case. If there's a workaround, share it. If the feature is on the roadmap, say "This is something our product team is aware of" (never give timelines).
- **Escalate only if:** The customer is persistent and dissatisfied with the response.

### General Feedback (Positive or Neutral)
- "I love TaskFlow!"
- "The new update is nice but..."
- "Just wanted to say the Gantt view is great"
- **Action:** Thank them warmly. Log the feedback. No escalation needed.

### Common Troubleshooting
- Login issues (password reset, SSO, 2FA)
- Sync problems (browser refresh, cache clear, app reinstall)
- Integration reconnection (Slack, Google Drive, GitHub)
- Notification settings adjustment
- Mobile app basics (update, cache clear, reinstall)
- **Action:** Follow the troubleshooting steps in product documentation. Provide step-by-step guidance.

### Plan & Pricing Inquiries (Informational Only)
- "What's included in the Pro plan?"
- "How much does Enterprise cost?"
- "What's the difference between Member and Guest?"
- **Action:** Provide accurate pricing and feature information from the product docs. Direct to sales@techcorp.io only if they express interest in Enterprise or custom plans.

---

## Escalation Format

When escalating, the AI agent must include the following structured handoff:

```
=== ESCALATION HANDOFF ===

Ticket ID:       [TF-YYYYMMDD-XXXX]
Channel:         [Gmail / WhatsApp / Web Form]
Customer:        [Name, email, plan]
Priority:        [Critical / High / Medium / Low]
Category:        [Billing / Technical / Security / Legal / Account / Churn Risk]
Urgency:         [Immediate / Within 1 hour / Within 24 hours]

Escalation Reason:
[Brief description of why this is being escalated]

Conversation Summary:
[2-3 sentence summary of what the customer asked and what was attempted]

Resolution Attempts:
1. [First thing the AI tried + customer response]
2. [Second thing the AI tried + customer response (if applicable)]

Customer Sentiment: [Positive / Neutral / Frustrated / Angry]
Sentiment Score:    [0.0 - 1.0]

Suggested Next Step:
[What the AI thinks the human agent should do]

Full Conversation Attached: [Yes/No]

=== END HANDOFF ===
```

---

## Escalation Routing Table

| Category | Tier 1 Escalation | Tier 2 Escalation | Tier 3 (Executive) |
|----------|-------------------|-------------------|--------------------|
| Billing & Refunds | Lisa Tanaka | VP Finance | CEO |
| Technical Issues | Priya Patel | James Okafor | CTO |
| Account Access | Marcus Rivera | Priya Patel | James Okafor |
| Security Incidents | James Okafor | CISO | CEO |
| Legal & Compliance | Rachel Foster | General Counsel | CEO |
| Feature Requests | Product Team (logged) | David Kim | — |
| Customer Churn | Marcus Rivera | Sarah Chen | VP Sales |
| General / Other | Marcus Rivera | Sarah Chen | VP of Customer Success |

---

## Escalation SLAs

| Urgency Level | Definition | Human Response Target | Update Frequency |
|---------------|------------|----------------------|------------------|
| **Immediate** | Service outage, security breach, legal threat | < 15 minutes | Every 30 minutes |
| **Within 1 hour** | Account lockout, billing error, angry customer | < 1 hour | Every 2 hours |
| **Within 4 hours** | Technical bug, integration failure | < 4 hours | Daily |
| **Within 24 hours** | Feature request follow-up, non-urgent billing question | < 24 hours | As needed |

---

## Confidence Score Thresholds

The AI agent assigns a confidence score (0.0–1.0) to each response:

| Score Range | Action |
|-------------|--------|
| **0.8 – 1.0** | Send response directly to customer |
| **0.6 – 0.79** | Send response but flag for human review within 4 hours |
| **0.4 – 0.59** | Draft a response but hold for human approval before sending |
| **0.0 – 0.39** | Do not respond. Escalate immediately with "I want to make sure you get the best help, so I'm connecting you with our support team." |

---

## De-escalation Guidelines

Before escalating, try these de-escalation techniques:

1. **Acknowledge the emotion:** "I can see this has been really frustrating. I'm sorry about that."
2. **Take ownership:** "Let me personally make sure this gets resolved."
3. **Provide a concrete action:** "Here's exactly what I'm going to do right now to fix this."
4. **Set a specific timeline:** "You'll hear back from our team within 2 hours."
5. **Offer an alternative:** If the primary solution doesn't work, have a backup suggestion ready.

If the customer's sentiment doesn't improve after de-escalation, proceed with escalation immediately. Never argue with an upset customer.
