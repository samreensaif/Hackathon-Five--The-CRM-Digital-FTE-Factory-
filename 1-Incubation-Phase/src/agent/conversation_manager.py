"""
Conversation Manager — Stateful multi-turn, cross-channel conversation tracking.
=================================================================================
Tracks conversations per customer across channels, maintains history, detects
sentiment trends, and enables cross-channel continuity.

Storage: In-memory dict (incubation phase). Phase 3 will use PostgreSQL.
"""

import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field


# ── Data classes ───────────────────────────────────────────────────────────

@dataclass
class Message:
    role: str              # "customer" or "agent"
    content: str
    channel: str
    timestamp: str = ""
    sentiment: float = 0.0
    intent: str = ""
    ticket_id: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "channel": self.channel,
            "timestamp": self.timestamp,
            "sentiment": self.sentiment,
            "intent": self.intent,
            "ticket_id": self.ticket_id,
        }


@dataclass
class Conversation:
    conversation_id: str
    customer_id: str              # email (primary) or phone
    channel: str                  # initial channel
    started_at: str
    last_message_at: str
    status: str = "active"        # active | resolved | escalated
    messages: list = field(default_factory=list)
    topics_discussed: list = field(default_factory=list)
    sentiment_history: list = field(default_factory=list)
    resolution_status: str = "pending"   # pending | solved | escalated
    escalation_id: str = ""
    escalation_reason: str = ""
    channels_used: list = field(default_factory=list)
    customer_name: str = ""
    customer_plan: str = ""

    def to_dict(self) -> dict:
        return {
            "conversation_id": self.conversation_id,
            "customer_id": self.customer_id,
            "channel": self.channel,
            "started_at": self.started_at,
            "last_message_at": self.last_message_at,
            "status": self.status,
            "messages": [m.to_dict() if isinstance(m, Message) else m
                         for m in self.messages],
            "topics_discussed": self.topics_discussed,
            "sentiment_history": self.sentiment_history,
            "resolution_status": self.resolution_status,
            "escalation_id": self.escalation_id,
            "escalation_reason": self.escalation_reason,
            "channels_used": self.channels_used,
            "customer_name": self.customer_name,
            "customer_plan": self.customer_plan,
        }


# ── Conversation Manager ──────────────────────────────────────────────────

class ConversationManager:
    """In-memory conversation store with cross-channel linking."""

    # Thresholds for sentiment-based auto-escalation
    SENTIMENT_DROP_THRESHOLD = -0.4   # drop from first to current
    CONSECUTIVE_NEGATIVE_LIMIT = 3    # auto-escalate after N negative msgs
    NEGATIVE_SENTIMENT_CUTOFF = -0.2  # what counts as "negative"

    def __init__(self):
        # conversation_id -> Conversation
        self._conversations: dict[str, Conversation] = {}
        # customer_id -> list of conversation_ids (most recent last)
        self._customer_index: dict[str, list[str]] = {}
        # email -> set of alt identifiers (phone numbers, other emails)
        self._identity_links: dict[str, set[str]] = {}

    # ── Identity linking ──────────────────────────────────────────────

    def link_identity(self, primary_email: str, alt_id: str):
        """Link an alternative identifier (phone, secondary email) to a primary email."""
        primary = primary_email.lower().strip()
        alt = alt_id.lower().strip()
        if primary not in self._identity_links:
            self._identity_links[primary] = set()
        self._identity_links[primary].add(alt)
        # Also create reverse lookup
        if alt not in self._identity_links:
            self._identity_links[alt] = set()
        self._identity_links[alt].add(primary)

    def resolve_customer_id(self, identifier: str) -> str:
        """Resolve any identifier to the canonical customer ID (primary email)."""
        identifier = identifier.lower().strip()

        # Direct match in customer index
        if identifier in self._customer_index:
            return identifier

        # Check identity links
        if identifier in self._identity_links:
            for linked in self._identity_links[identifier]:
                if linked in self._customer_index:
                    return linked

        # Not found — use as-is
        return identifier

    # ── Conversation CRUD ─────────────────────────────────────────────

    def start_conversation(self, customer_id: str, channel: str,
                           customer_name: str = "",
                           customer_plan: str = "") -> Conversation:
        """Start a new conversation for a customer."""
        cid = customer_id.lower().strip()
        now = datetime.now(timezone.utc).isoformat()

        conv = Conversation(
            conversation_id=str(uuid.uuid4()),
            customer_id=cid,
            channel=channel,
            started_at=now,
            last_message_at=now,
            channels_used=[channel],
            customer_name=customer_name,
            customer_plan=customer_plan,
        )

        self._conversations[conv.conversation_id] = conv
        if cid not in self._customer_index:
            self._customer_index[cid] = []
        self._customer_index[cid].append(conv.conversation_id)

        return conv

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        return self._conversations.get(conversation_id)

    def get_active_conversation(self, customer_id: str,
                                channel: str = "",
                                include_escalated: bool = False) -> Conversation | None:
        """Get the most recent active conversation for a customer, optionally filtered by channel."""
        cid = self.resolve_customer_id(customer_id)
        conv_ids = self._customer_index.get(cid, [])

        allowed_statuses = {"active"}
        if include_escalated:
            allowed_statuses.add("escalated")

        for conv_id in reversed(conv_ids):
            conv = self._conversations.get(conv_id)
            if conv and conv.status in allowed_statuses:
                if not channel or channel in conv.channels_used or channel == conv.channel:
                    return conv

        return None

    def get_latest_conversation(self, customer_id: str) -> Conversation | None:
        """Get the most recent conversation regardless of status."""
        cid = self.resolve_customer_id(customer_id)
        conv_ids = self._customer_index.get(cid, [])
        for conv_id in reversed(conv_ids):
            conv = self._conversations.get(conv_id)
            if conv:
                return conv
        return None

    def get_or_create_conversation(self, customer_id: str, channel: str,
                                   customer_name: str = "",
                                   customer_plan: str = "") -> Conversation:
        """Get existing active/escalated conversation or start a new one."""
        conv = self.get_active_conversation(customer_id, "", include_escalated=True)
        if conv:
            # Track channel switch
            if channel not in conv.channels_used:
                conv.channels_used.append(channel)
            if customer_name and not conv.customer_name:
                conv.customer_name = customer_name
            if customer_plan and not conv.customer_plan:
                conv.customer_plan = customer_plan
            return conv

        return self.start_conversation(
            customer_id, channel, customer_name, customer_plan
        )

    # ── Message handling ──────────────────────────────────────────────

    def add_message(self, conversation_id: str, role: str, content: str,
                    channel: str, sentiment: float = 0.0,
                    intent: str = "", ticket_id: str = "") -> Message:
        """Add a message to a conversation and update state."""
        conv = self._conversations.get(conversation_id)
        if not conv:
            raise ValueError(f"Conversation {conversation_id} not found")

        msg = Message(
            role=role,
            content=content,
            channel=channel,
            sentiment=sentiment,
            intent=intent,
            ticket_id=ticket_id,
        )

        conv.messages.append(msg)
        conv.last_message_at = msg.timestamp

        # Track channel usage
        if channel not in conv.channels_used:
            conv.channels_used.append(channel)

        # Track sentiment history for customer messages
        if role == "customer":
            conv.sentiment_history.append({
                "score": sentiment,
                "timestamp": msg.timestamp,
                "message_index": len(conv.messages) - 1,
            })

        # Track topics from intent
        if intent and intent not in ("greeting", "unclear", "spam",
                                     "general_inquiry"):
            if intent not in conv.topics_discussed:
                conv.topics_discussed.append(intent)

        return msg

    # ── Sentiment trending ────────────────────────────────────────────

    def check_sentiment_trend(self, conversation_id: str) -> dict:
        """Analyze sentiment trend and return escalation recommendation."""
        conv = self._conversations.get(conversation_id)
        if not conv or not conv.sentiment_history:
            return {"should_escalate": False, "reason": "", "trend": "neutral"}

        scores = [s["score"] for s in conv.sentiment_history]

        # Check consecutive negative messages
        consecutive_negative = 0
        for score in reversed(scores):
            if score < self.NEGATIVE_SENTIMENT_CUTOFF:
                consecutive_negative += 1
            else:
                break

        if consecutive_negative >= self.CONSECUTIVE_NEGATIVE_LIMIT:
            return {
                "should_escalate": True,
                "reason": (f"Customer sent {consecutive_negative} consecutive "
                           f"negative messages (sentiment trending down)"),
                "trend": "declining",
                "consecutive_negative": consecutive_negative,
            }

        # Check significant sentiment drop from first to latest
        if len(scores) >= 2:
            first_score = scores[0]
            latest_score = scores[-1]
            drop = latest_score - first_score

            if drop <= self.SENTIMENT_DROP_THRESHOLD:
                return {
                    "should_escalate": True,
                    "reason": (f"Sentiment dropped significantly: "
                               f"{first_score:+.2f} → {latest_score:+.2f} "
                               f"(Δ={drop:+.2f})"),
                    "trend": "declining",
                    "drop": drop,
                }

        # Determine overall trend
        if len(scores) >= 2:
            avg_first_half = sum(scores[:len(scores)//2]) / max(len(scores)//2, 1)
            avg_second_half = sum(scores[len(scores)//2:]) / max(len(scores) - len(scores)//2, 1)
            if avg_second_half < avg_first_half - 0.2:
                trend = "declining"
            elif avg_second_half > avg_first_half + 0.2:
                trend = "improving"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        return {
            "should_escalate": False,
            "reason": "",
            "trend": trend,
        }

    # ── Cross-channel context ─────────────────────────────────────────

    def get_cross_channel_context(self, customer_id: str,
                                  current_channel: str) -> str | None:
        """If customer previously contacted on a different channel, return context string."""
        cid = self.resolve_customer_id(customer_id)
        conv = self.get_active_conversation(cid, include_escalated=True)

        if not conv or not conv.messages:
            return None

        # Check if there are messages from a different channel
        other_channel_msgs = [
            m for m in conv.messages
            if (isinstance(m, Message) and m.channel != current_channel
                and m.role == "customer")
        ]

        if not other_channel_msgs:
            return None

        # Build context reference
        prev_channel = other_channel_msgs[-1].channel
        topics = conv.topics_discussed

        if topics:
            topic_str = ", ".join(t.replace("_", " ") for t in topics[:3])
            return (f"I see you contacted us earlier via {prev_channel} "
                    f"about {topic_str}. Let me help you further.")

        return (f"I see you contacted us earlier via {prev_channel}. "
                f"Let me continue helping you.")

    # ── Customer history ──────────────────────────────────────────────

    def get_customer_history(self, customer_id: str) -> dict:
        """Get full history for a customer across all channels."""
        cid = self.resolve_customer_id(customer_id)
        conv_ids = self._customer_index.get(cid, [])

        if not conv_ids:
            return {
                "customer_id": cid,
                "conversation_count": 0,
                "conversations": [],
                "all_topics": [],
                "all_channels": [],
                "sentiment_trend": [],
                "last_contact": None,
            }

        conversations = []
        all_topics = []
        all_channels = set()
        all_sentiments = []
        last_contact = None

        for conv_id in conv_ids:
            conv = self._conversations.get(conv_id)
            if not conv:
                continue

            conversations.append({
                "conversation_id": conv.conversation_id,
                "channel": conv.channel,
                "channels_used": conv.channels_used,
                "started_at": conv.started_at,
                "last_message_at": conv.last_message_at,
                "status": conv.status,
                "resolution_status": conv.resolution_status,
                "message_count": len(conv.messages),
                "topics": conv.topics_discussed,
            })

            all_topics.extend(conv.topics_discussed)
            all_channels.update(conv.channels_used)
            all_sentiments.extend(conv.sentiment_history)

            if not last_contact or conv.last_message_at > last_contact:
                last_contact = conv.last_message_at

        # Deduplicate topics preserving order
        seen = set()
        unique_topics = []
        for t in all_topics:
            if t not in seen:
                seen.add(t)
                unique_topics.append(t)

        return {
            "customer_id": cid,
            "conversation_count": len(conversations),
            "conversations": conversations,
            "all_topics": unique_topics,
            "all_channels": sorted(all_channels),
            "sentiment_trend": [
                {"score": s["score"], "timestamp": s["timestamp"]}
                for s in sorted(all_sentiments, key=lambda x: x["timestamp"])
            ],
            "last_contact": last_contact,
        }

    # ── Conversation state updates ────────────────────────────────────

    def resolve_conversation(self, conversation_id: str):
        conv = self._conversations.get(conversation_id)
        if conv:
            conv.status = "resolved"
            conv.resolution_status = "solved"

    def escalate_conversation(self, conversation_id: str, reason: str,
                              escalation_id: str = "") -> str:
        conv = self._conversations.get(conversation_id)
        if not conv:
            raise ValueError(f"Conversation {conversation_id} not found")

        esc_id = escalation_id or f"ESC-{uuid.uuid4().hex[:8].upper()}"
        conv.status = "escalated"
        conv.resolution_status = "escalated"
        conv.escalation_id = esc_id
        conv.escalation_reason = reason
        return esc_id

    # ── Utility ───────────────────────────────────────────────────────

    def get_conversation_summary(self, conversation_id: str) -> str:
        """Generate a human-readable summary of a conversation."""
        conv = self._conversations.get(conversation_id)
        if not conv:
            return "Conversation not found."

        msg_count = len(conv.messages)
        customer_msgs = sum(1 for m in conv.messages
                            if (isinstance(m, Message) and m.role == "customer"))
        agent_msgs = msg_count - customer_msgs

        lines = [
            f"Conversation {conv.conversation_id[:8]}...",
            f"  Customer: {conv.customer_name or conv.customer_id}",
            f"  Plan: {conv.customer_plan or 'unknown'}",
            f"  Channels: {', '.join(conv.channels_used)}",
            f"  Status: {conv.status} ({conv.resolution_status})",
            f"  Messages: {customer_msgs} customer, {agent_msgs} agent",
            f"  Topics: {', '.join(conv.topics_discussed) or 'none'}",
        ]

        if conv.sentiment_history:
            scores = [s["score"] for s in conv.sentiment_history]
            lines.append(
                f"  Sentiment: {scores[0]:+.2f} → {scores[-1]:+.2f} "
                f"(avg: {sum(scores)/len(scores):+.2f})"
            )

        if conv.escalation_id:
            lines.append(f"  Escalation: {conv.escalation_id} ({conv.escalation_reason})")

        return "\n".join(lines)

    @property
    def stats(self) -> dict:
        total = len(self._conversations)
        active = sum(1 for c in self._conversations.values() if c.status == "active")
        escalated = sum(1 for c in self._conversations.values() if c.status == "escalated")
        resolved = sum(1 for c in self._conversations.values() if c.status == "resolved")
        return {
            "total_conversations": total,
            "active": active,
            "escalated": escalated,
            "resolved": resolved,
            "unique_customers": len(self._customer_index),
        }
