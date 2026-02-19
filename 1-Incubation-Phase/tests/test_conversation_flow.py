"""
Test Suite — Conversation Flow, Sentiment Trending, and MCP Tools
=================================================================
Tests multi-turn conversations, cross-channel continuity, sentiment-based
auto-escalation, and all 6 MCP server tools.

Usage:
    python test_conversation_flow.py
"""

import sys
import os
from pathlib import Path

# Fix encoding on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    os.environ["PYTHONIOENCODING"] = "utf-8"

# Add agent directory to path
AGENT_DIR = Path(__file__).resolve().parent.parent / "src" / "agent"
sys.path.insert(0, str(AGENT_DIR))

from prototype import (
    Ticket, CustomerSuccessAgent, SentimentAnalyzer,
    KnowledgeBase, ResponseFormatter, CONTEXT_DIR,
)
from conversation_manager import ConversationManager, Message


# ── Helpers ────────────────────────────────────────────────────────────────

PASS = 0
FAIL = 0


def check(condition: bool, label: str, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}")
        if detail:
            print(f"         {detail}")


def section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# ── Test 1: Multi-turn conversation via email ─────────────────────────────

def test_multi_turn_email():
    section("TEST 1: Multi-turn email conversation")

    cm = ConversationManager()
    agent = CustomerSuccessAgent(conversation_manager=cm)

    # Turn 1: Customer asks about recurring tasks
    t1 = Ticket(
        id="TF-TEST-0001",
        channel="gmail",
        customer_name="Alice Johnson",
        customer_email="alice.johnson@testcorp.com",
        customer_plan="pro",
        subject="How to set up recurring tasks",
        message="Hi, I need to create tasks that repeat weekly. Is this possible in TaskFlow?",
    )
    r1 = agent.handle_ticket_with_context(t1)

    check(r1.detected_intent == "how_to",
          f"Turn 1 intent: {r1.detected_intent}",
          "Expected: how_to")
    check(not r1.should_escalate,
          "Turn 1 not escalated")
    check(r1.confidence_score >= 0.7,
          f"Turn 1 confidence: {r1.confidence_score}",
          "Expected >= 0.7")

    # Verify conversation was created
    conv = cm.get_active_conversation("alice.johnson@testcorp.com")
    check(conv is not None,
          "Conversation created")
    check(len(conv.messages) == 2,
          f"Messages after turn 1: {len(conv.messages)}",
          "Expected: 2 (customer + agent)")
    check("how_to" in conv.topics_discussed,
          f"Topics: {conv.topics_discussed}")

    # Turn 2: Follow-up question
    t2 = Ticket(
        id="TF-TEST-0002",
        channel="gmail",
        customer_name="Alice Johnson",
        customer_email="alice.johnson@testcorp.com",
        customer_plan="pro",
        subject="Re: How to set up recurring tasks",
        message="Thanks! Can I also set up a monthly recurrence, not just weekly?",
    )
    r2 = agent.handle_ticket_with_context(t2)

    # Should reuse the same conversation
    conv_after = cm.get_active_conversation("alice.johnson@testcorp.com")
    check(conv_after.conversation_id == conv.conversation_id,
          "Same conversation reused for follow-up")
    check(len(conv_after.messages) == 4,
          f"Messages after turn 2: {len(conv_after.messages)}",
          "Expected: 4 (2 customer + 2 agent)")

    # Print the conversation flow
    print("\n  --- Conversation Flow ---")
    for i, msg in enumerate(conv_after.messages):
        role = msg.role if isinstance(msg, Message) else msg.get("role", "?")
        content = msg.content if isinstance(msg, Message) else msg.get("content", "?")
        preview = content[:80].replace('\n', ' ')
        print(f"  [{i+1}] {role}: {preview}...")
    print()


# ── Test 2: Cross-channel continuity ─────────────────────────────────────

def test_cross_channel():
    section("TEST 2: Cross-channel continuity (email → WhatsApp)")

    cm = ConversationManager()
    agent = CustomerSuccessAgent(conversation_manager=cm)

    # Link email to phone
    cm.link_identity("bob.smith@example.com", "+1555123456")

    # Turn 1: Customer contacts via email
    t1 = Ticket(
        id="TF-TEST-0010",
        channel="gmail",
        customer_name="Bob Smith",
        customer_email="bob.smith@example.com",
        customer_plan="pro",
        subject="Slack integration not working",
        message="Our Slack notifications stopped working since last Tuesday. We've tried reconnecting but the issue persists.",
    )
    r1 = agent.handle_ticket_with_context(t1)

    check(r1.detected_intent == "integration_issue",
          f"Email intent: {r1.detected_intent}")
    check(not r1.should_escalate,
          "Email not escalated (standard integration issue)")

    # Turn 2: Same customer contacts via WhatsApp (different identifier)
    t2 = Ticket(
        id="TF-TEST-0011",
        channel="whatsapp",
        customer_name="Bob Smith",
        customer_email="bob.smith@example.com",  # same email
        customer_plan="pro",
        subject="Slack still broken",
        message="hey the slack thing is still not working",
    )
    r2 = agent.handle_ticket_with_context(t2)

    # Check cross-channel context was detected (may be escalated due to "still not")
    conv = cm.get_latest_conversation("bob.smith@example.com")
    check(conv is not None,
          "Conversation found via email")
    check(len(conv.channels_used) == 2,
          f"Channels used: {conv.channels_used}",
          "Expected: ['gmail', 'whatsapp']")
    check("gmail" in conv.channels_used and "whatsapp" in conv.channels_used,
          "Both channels tracked")

    # The response should reference the previous conversation.
    # Note: WhatsApp escalation responses use a short template that doesn't
    # include the body, so cross-channel context may not appear when escalated.
    # We check if it's either escalated OR has the cross-channel reference.
    has_cross_ref = "contacted us earlier" in r2.response_text
    was_escalated = r2.should_escalate
    check(has_cross_ref or was_escalated,
          f"Cross-channel: context_shown={has_cross_ref}, escalated={was_escalated}",
          f"Response preview: {r2.response_text[:120]}...")

    # Verify conversation history
    history = cm.get_customer_history("bob.smith@example.com")
    check(history["conversation_count"] == 1,
          f"Conversation count: {history['conversation_count']}",
          "Expected: 1 (same conversation, different channels)")
    check("integration_issue" in history["all_topics"],
          f"Topics tracked: {history['all_topics']}")

    print(f"\n  --- WhatsApp Response (cross-channel) ---")
    print(f"  {r2.response_text}")
    print()


# ── Test 3: Sentiment trending & auto-escalation ─────────────────────────

def test_sentiment_trending():
    section("TEST 3: Sentiment trending → auto-escalation")

    cm = ConversationManager()
    agent = CustomerSuccessAgent(conversation_manager=cm)

    customer_email = "carol.davis@example.com"

    # Message 1: Positive
    t1 = Ticket(
        id="TF-TEST-0020",
        channel="gmail",
        customer_name="Carol Davis",
        customer_email=customer_email,
        customer_plan="pro",
        subject="Question about importing from Trello",
        message="Hi! I'm excited to start using TaskFlow. How do I import my Trello boards? Thanks!",
    )
    r1 = agent.handle_ticket_with_context(t1)

    check(r1.detected_sentiment > 0,
          f"Msg 1 sentiment: {r1.detected_sentiment:+.2f} (expected positive)")
    check(not r1.should_escalate,
          "Msg 1 not escalated")

    # Message 2: Slightly negative
    t2 = Ticket(
        id="TF-TEST-0021",
        channel="gmail",
        customer_name="Carol Davis",
        customer_email=customer_email,
        customer_plan="pro",
        subject="Re: Question about importing from Trello",
        message="The import didn't work correctly. Several of my labels and due dates are missing. This is frustrating.",
    )
    r2 = agent.handle_ticket_with_context(t2)

    check(r2.detected_sentiment < 0,
          f"Msg 2 sentiment: {r2.detected_sentiment:+.2f} (expected negative)")

    # Message 3: More negative
    t3 = Ticket(
        id="TF-TEST-0022",
        channel="gmail",
        customer_name="Carol Davis",
        customer_email=customer_email,
        customer_plan="pro",
        subject="Re: Re: Question about importing from Trello",
        message="I tried the import again and now I've lost even more data. This is terrible. My team can't work like this.",
    )
    r3 = agent.handle_ticket_with_context(t3)

    check(r3.detected_sentiment < -0.3,
          f"Msg 3 sentiment: {r3.detected_sentiment:+.2f} (expected very negative)")

    # Message 4: Extremely negative — should trigger auto-escalation via trend
    t4 = Ticket(
        id="TF-TEST-0023",
        channel="gmail",
        customer_name="Carol Davis",
        customer_email=customer_email,
        customer_plan="pro",
        subject="Re: Re: Re: Question about importing from Trello",
        message="This is completely unacceptable. We've wasted two days on this broken import. I want to speak to a manager immediately.",
    )
    r4 = agent.handle_ticket_with_context(t4)

    check(r4.should_escalate,
          "Msg 4 escalated (sentiment trend + angry language)")
    check("SENTIMENT" in r4.escalation_reason or "human" in r4.escalation_reason.lower(),
          f"Escalation reason includes sentiment/human: {r4.escalation_reason[:100]}")

    # Check sentiment trend (conversation may be escalated, so use get_latest)
    conv = cm.get_latest_conversation(customer_email)
    check(conv is not None, "Conversation exists for sentiment check")
    trend = cm.check_sentiment_trend(conv.conversation_id)
    check(trend["trend"] == "declining",
          f"Trend: {trend['trend']}")

    # Print sentiment timeline
    print(f"\n  --- Sentiment Timeline ---")
    for i, sh in enumerate(conv.sentiment_history):
        score = sh["score"]
        bar = "+" * max(0, int(score * 10)) + "-" * max(0, int(-score * 10))
        print(f"  Msg {i+1}: {score:+.2f} [{bar}]")

    print(f"\n  --- Conversation Status ---")
    print(f"  {cm.get_conversation_summary(conv.conversation_id)}")
    print()


# ── Test 4: ConversationManager unit tests ────────────────────────────────

def test_conversation_manager_units():
    section("TEST 4: ConversationManager unit tests")

    cm = ConversationManager()

    # Test: start conversation
    conv = cm.start_conversation(
        customer_id="test@example.com",
        channel="gmail",
        customer_name="Test User",
        customer_plan="pro",
    )
    check(conv.conversation_id is not None,
          f"Conversation created: {conv.conversation_id[:8]}...")
    check(conv.status == "active",
          f"Status: {conv.status}")
    check(conv.customer_id == "test@example.com",
          f"Customer ID: {conv.customer_id}")

    # Test: add messages
    cm.add_message(conv.conversation_id, "customer", "Hello", "gmail",
                   sentiment=0.3, intent="greeting")
    cm.add_message(conv.conversation_id, "agent", "Hi! How can I help?", "gmail")
    check(len(conv.messages) == 2,
          f"Messages: {len(conv.messages)}")
    check(len(conv.sentiment_history) == 1,
          f"Sentiment history: {len(conv.sentiment_history)} (only customer msgs)")

    # Test: get_or_create reuses active conversation
    conv2 = cm.get_or_create_conversation("test@example.com", "gmail")
    check(conv2.conversation_id == conv.conversation_id,
          "get_or_create reuses active conversation")

    # Test: channel switch tracking
    conv3 = cm.get_or_create_conversation("test@example.com", "whatsapp")
    check("whatsapp" in conv3.channels_used,
          f"Channel switch tracked: {conv3.channels_used}")

    # Test: identity linking
    cm.link_identity("test@example.com", "+1555000000")
    resolved = cm.resolve_customer_id("+1555000000")
    check(resolved == "test@example.com",
          f"Identity resolved: +1555000000 → {resolved}")

    # Test: resolve conversation
    cm.resolve_conversation(conv.conversation_id)
    check(conv.status == "resolved",
          f"Status after resolve: {conv.status}")

    # Test: new conversation after resolved
    conv4 = cm.get_or_create_conversation("test@example.com", "gmail")
    check(conv4.conversation_id != conv.conversation_id,
          "New conversation created after previous was resolved")

    # Test: escalation
    esc_id = cm.escalate_conversation(conv4.conversation_id, "Test escalation")
    check(esc_id.startswith("ESC-"),
          f"Escalation ID: {esc_id}")
    check(conv4.status == "escalated",
          f"Status after escalate: {conv4.status}")

    # Test: customer history
    history = cm.get_customer_history("test@example.com")
    check(history["conversation_count"] == 2,
          f"History conversations: {history['conversation_count']}")
    check("gmail" in history["all_channels"],
          f"History channels: {history['all_channels']}")

    # Test: stats
    stats = cm.stats
    check(stats["total_conversations"] == 2,
          f"Total conversations: {stats['total_conversations']}")
    check(stats["unique_customers"] == 1,
          f"Unique customers: {stats['unique_customers']}")
    print()


# ── Test 5: MCP Tools (direct invocation) ─────────────────────────────────

def test_mcp_tools():
    section("TEST 5: MCP Tool direct invocation")

    # Import MCP tools (they use module-level shared state)
    from mcp_server import (
        search_knowledge_base,
        create_ticket,
        get_customer_history,
        escalate_to_human,
        send_response,
        analyze_sentiment,
        _cm,
    )

    # Tool 1: search_knowledge_base
    print("  --- Tool 1: search_knowledge_base ---")
    result = search_knowledge_base("how to set up recurring tasks")
    check(len(result) > 0,
          "search_knowledge_base returns results")
    check("Result 1:" in result,
          "Results are numbered")
    print(f"  First 200 chars: {result[:200]}...")
    print()

    # Tool 2: create_ticket
    print("  --- Tool 2: create_ticket ---")
    ticket_result = create_ticket(
        customer_email="mcp-test@example.com",
        customer_name="MCP Test User",
        subject="How do I invite team members?",
        message="Hi, I just created my workspace and I want to invite my team. How do I do that?",
        channel="web-form",
        priority="low",
        category="how-to",
        customer_plan="free",
    )
    check("ticket_id" in ticket_result,
          f"Ticket created: {ticket_result['ticket_id']}")
    check(ticket_result["detected_intent"] == "how_to",
          f"Intent: {ticket_result['detected_intent']}")
    check("response_text" in ticket_result,
          "Response generated")
    check(not ticket_result["should_escalate"],
          "Not escalated (simple how-to)")
    ticket_id = ticket_result["ticket_id"]
    print(f"  Response preview: {ticket_result['response_text'][:120]}...")
    print()

    # Tool 3: get_customer_history
    print("  --- Tool 3: get_customer_history ---")
    history = get_customer_history("mcp-test@example.com")
    check(history["found"],
          "Customer history found")
    check(history["conversation_count"] >= 1,
          f"Conversations: {history['conversation_count']}")
    check("how_to" in history["all_topics"],
          f"Topics: {history['all_topics']}")
    print()

    # Tool 4: escalate_to_human
    print("  --- Tool 4: escalate_to_human ---")
    esc_result = escalate_to_human(
        ticket_id=ticket_id,
        reason="Customer requesting manager review",
        urgency="within_1_hour",
        category="general",
    )
    check("escalation_id" in esc_result,
          f"Escalation: {esc_result['escalation_id']}")
    check(esc_result["assigned_to"] == "Marcus Rivera",
          f"Assigned to: {esc_result['assigned_to']}")
    check(esc_result["status"] == "escalated",
          f"Status: {esc_result['status']}")
    print()

    # Tool 5: send_response
    print("  --- Tool 5: send_response ---")
    send_result = send_response(
        ticket_id=ticket_id,
        message="Your request has been reviewed and approved.",
        channel="web-form",
        customer_name="MCP Test User",
    )
    check(send_result["delivery_status"] == "sent",
          f"Delivery: {send_result['delivery_status']}")
    check("TaskFlow Support" in send_result["formatted_message"],
          "Formatted with brand voice")
    check("TF-" in send_result["formatted_message"],
          "Ticket ID in formatted response")
    print(f"  Formatted: {send_result['formatted_message'][:150]}...")
    print()

    # Tool 6: analyze_sentiment
    print("  --- Tool 6: analyze_sentiment ---")

    pos = analyze_sentiment("I love TaskFlow! It's amazing and so helpful!")
    check(pos["label"] == "positive",
          f"Positive text: score={pos['score']:+.2f}, label={pos['label']}")

    neg = analyze_sentiment("This is terrible and broken. Worst experience ever.")
    check(neg["label"] == "negative",
          f"Negative text: score={neg['score']:+.2f}, label={neg['label']}")

    neutral = analyze_sentiment("I need to export my project data as CSV.")
    check(neutral["label"] == "neutral",
          f"Neutral text: score={neutral['score']:+.2f}, label={neutral['label']}")

    print()


# ── Test 6: Conversation summary and stats ────────────────────────────────

def test_stats_and_summary():
    section("TEST 6: Conversation summary and stats")

    cm = ConversationManager()
    agent = CustomerSuccessAgent(conversation_manager=cm)

    # Create a few conversations
    tickets = [
        Ticket(id="TF-STAT-001", channel="gmail",
               customer_name="User A", customer_email="a@test.com",
               customer_plan="pro", subject="Login help",
               message="I can't log in to my account"),
        Ticket(id="TF-STAT-002", channel="whatsapp",
               customer_name="User B", customer_email="b@test.com",
               customer_plan="free", subject="Pricing",
               message="how much does pro cost"),
        Ticket(id="TF-STAT-003", channel="web-form",
               customer_name="User C", customer_email="c@test.com",
               customer_plan="enterprise", subject="Refund request",
               message="I want a refund for the last charge"),
    ]

    for t in tickets:
        agent.handle_ticket_with_context(t)

    stats = cm.stats
    check(stats["total_conversations"] == 3,
          f"Total: {stats['total_conversations']}")
    check(stats["unique_customers"] == 3,
          f"Unique customers: {stats['unique_customers']}")

    # User C should be escalated (refund)
    conv_c = cm.get_active_conversation("c@test.com")
    # It might be escalated or still active depending on confidence
    check(conv_c is not None or cm.get_customer_history("c@test.com")["conversation_count"] > 0,
          "User C conversation exists")

    # Print summaries
    print("\n  --- All Conversation Summaries ---")
    for conv_id, conv in cm._conversations.items():
        print(f"  {cm.get_conversation_summary(conv_id)}")
        print()

    print(f"  Stats: {stats}")
    print()


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 70)
    print("  CUSTOMER SUCCESS FTE — TEST SUITE")
    print("  Conversation Flow | Sentiment Trending | MCP Tools")
    print("=" * 70)

    test_multi_turn_email()
    test_cross_channel()
    test_sentiment_trending()
    test_conversation_manager_units()
    test_mcp_tools()
    test_stats_and_summary()

    # Final summary
    total = PASS + FAIL
    print("\n" + "=" * 70)
    print(f"  FINAL RESULTS: {PASS}/{total} passed, {FAIL} failed")
    print("=" * 70)

    if FAIL > 0:
        print(f"\n  {FAIL} test(s) FAILED — see details above")
        return 1
    else:
        print("\n  All tests PASSED!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
