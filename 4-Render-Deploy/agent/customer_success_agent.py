"""
Customer Success Digital FTE — Core Agent
==========================================
Production implementation using OpenAI Agents SDK for orchestration.

The agent processes incoming customer messages through a 6-step workflow:
  1. Identify customer (get_customer_history)
  2. Analyze sentiment (analyze_sentiment)
  3. Check escalation rules (encoded in system prompt)
  4. Search knowledge base (search_knowledge_base)
  5. Generate response (LLM reasoning)
  6. Format and send (send_response)

Usage:
    from agent.customer_success_agent import run_agent

    result = await run_agent(
        customer_message="How do I set up Slack integration?",
        customer_email="alice@example.com",
        customer_name="Alice",
        channel="email",
    )
    print(result["formatted_response"])

Architecture:
    FastAPI → run_agent() → Agent (GPT-4o) → tools → database
                                            → formatters
                                            → prompts
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from agents import Agent, Runner
from openai import AsyncOpenAI

from .prompts import (
    CUSTOMER_SUCCESS_SYSTEM_PROMPT,
    SLA_BY_PLAN,
    build_system_prompt,
)
from .tools import (
    analyze_sentiment,
    create_ticket,
    escalate_to_human,
    get_customer_history,
    search_knowledge_base,
    send_response,
    set_db_pool,
)

logger = logging.getLogger("agent.core")

# ── OpenAI Client ────────────────────────────────────────────────────────

client = AsyncOpenAI()

# ── Agent Definition ─────────────────────────────────────────────────────
# The Agent is a stateless definition. Each run_agent() call creates a
# fresh run with conversation context injected as messages.

customer_success_agent = Agent(
    name="Customer Success FTE",
    model="gpt-4o",
    instructions=CUSTOMER_SUCCESS_SYSTEM_PROMPT,
    tools=[
        search_knowledge_base,
        create_ticket,
        get_customer_history,
        escalate_to_human,
        send_response,
        analyze_sentiment,
    ],
)


# ── Agent Runner ─────────────────────────────────────────────────────────


async def run_agent(
    customer_message: str,
    customer_email: str,
    channel: str,
    customer_name: str = "Customer",
    customer_plan: str = "free",
    customer_id: Optional[str] = None,
    ticket_subject: str = "Support Request",
    conversation_history: Optional[list[dict]] = None,
) -> dict:
    """Run the agent with full context for a single customer interaction.

    This is the main entry point called by the FastAPI endpoint.

    Args:
        customer_message: The customer's message text
        customer_email: Customer email (primary identifier)
        channel: Contact channel ('email', 'whatsapp', 'web_form')
        customer_name: Customer display name
        customer_plan: Subscription tier ('free', 'pro', 'enterprise')
        customer_id: Customer UUID (if known from prior lookup)
        ticket_subject: Subject line for the ticket
        conversation_history: Prior messages in [{role, content}] format

    Returns:
        dict with:
          - response_text: Raw agent response
          - formatted_response: Channel-formatted response
          - ticket_id: Created ticket reference
          - escalated: Whether the ticket was escalated
          - escalation_details: Escalation info (if escalated)
          - sentiment_score: Detected sentiment
          - tools_used: List of tools called
          - tokens_used: Total token consumption
          - latency_ms: End-to-end processing time
    """
    start_time = time.time()

    # Build channel-specific system prompt
    system_prompt = build_system_prompt(channel)

    # Inject context variables into the prompt
    sla = SLA_BY_PLAN.get(customer_plan, "24 hours")
    context_block = (
        f"\n\n## Current Ticket Context\n"
        f"- customer_name: {customer_name}\n"
        f"- customer_email: {customer_email}\n"
        f"- customer_plan: {customer_plan}\n"
        f"- channel: {channel}\n"
        f"- subject: {ticket_subject}\n"
        f"- customer_id: {customer_id or 'to be resolved'}\n"
        f"- SLA response time: {sla}\n"
    )

    # Add cross-channel context if conversation history exists
    if conversation_history:
        history_text = "\n".join(
            f"  [{m.get('role', '?')}] {m.get('content', '')[:200]}"
            for m in conversation_history[-10:]  # Last 10 messages
        )
        context_block += f"\n- conversation_history:\n{history_text}\n"

    full_instructions = system_prompt + context_block

    # Create a channel-specific agent instance for this run
    run_agent_instance = Agent(
        name="Customer Success FTE",
        model="gpt-4o",
        instructions=full_instructions,
        tools=[
            search_knowledge_base,
            create_ticket,
            get_customer_history,
            escalate_to_human,
            send_response,
            analyze_sentiment,
        ],
    )

    # Build the messages array
    messages = []

    # Include conversation history as prior turns
    if conversation_history:
        for msg in conversation_history[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("customer", "user"):
                messages.append({"role": "user", "content": content})
            elif role in ("agent", "assistant"):
                messages.append({"role": "assistant", "content": content})

    # Add the current customer message
    user_message = (
        f"New {channel} message from {customer_name} ({customer_email}, "
        f"{customer_plan} plan):\n\n"
        f"Subject: {ticket_subject}\n\n"
        f"{customer_message}"
    )
    messages.append({"role": "user", "content": user_message})

    # Run the agent
    try:
        result = await Runner.run(
            run_agent_instance,
            input=messages,
        )

        # Extract response and metadata
        response_text = result.final_output or ""

        # Track tools used from the run
        tools_used = []
        escalated = False
        escalation_details = None
        ticket_id = None
        sentiment_score = 0.0

        # Parse tool calls from the run result
        for item in result.new_items:
            item_type = getattr(item, "type", "")

            if item_type == "tool_call_item":
                tool_name = getattr(item, "name", "unknown")
                tools_used.append(tool_name)

            elif item_type == "tool_call_output_item":
                output = getattr(item, "output", "")

                # Extract ticket ID from create_ticket output
                if "Ticket ID:" in output and "TF-" in output:
                    import re
                    match = re.search(r"TF-\d{8}-[A-Z0-9]{4}", output)
                    if match:
                        ticket_id = match.group()

                # Detect escalation from escalate_to_human output
                if "Escalation Confirmed" in output:
                    escalated = True
                    escalation_details = output

                # Extract sentiment from analyze_sentiment output
                if "Score:" in output:
                    import re
                    match = re.search(r"Score:\s*([-\d.]+)", output)
                    if match:
                        try:
                            sentiment_score = float(match.group(1))
                        except ValueError:
                            pass

        latency_ms = int((time.time() - start_time) * 1000)

        # Record metrics
        try:
            from database.queries import record_metric
            from .tools import _get_pool

            pool = _get_pool()
            await record_metric(pool, "response_latency_ms", latency_ms, channel)
            await record_metric(pool, "sentiment_score", sentiment_score, channel)
            await record_metric(
                pool, "escalation_rate", 1.0 if escalated else 0.0, channel
            )
        except Exception:
            pass  # Metrics are best-effort

        return {
            "response_text": response_text,
            "formatted_response": response_text,  # Already formatted by send_response tool
            "ticket_id": ticket_id,
            "escalated": escalated,
            "escalation_details": escalation_details,
            "sentiment_score": sentiment_score,
            "tools_used": tools_used,
            "tokens_used": getattr(result, "usage", {}).get("total_tokens", 0)
            if hasattr(result, "usage")
            else 0,
            "latency_ms": latency_ms,
        }

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Agent run failed: {e}", exc_info=True)

        return {
            "response_text": (
                "I apologize for the inconvenience. I'm experiencing a temporary "
                "issue. Please try again in a moment, or reach out to us at "
                "support@techcorp.io for immediate assistance."
            ),
            "formatted_response": None,
            "ticket_id": None,
            "escalated": False,
            "escalation_details": None,
            "sentiment_score": 0.0,
            "tools_used": [],
            "tokens_used": 0,
            "latency_ms": latency_ms,
            "error": str(e),
        }
