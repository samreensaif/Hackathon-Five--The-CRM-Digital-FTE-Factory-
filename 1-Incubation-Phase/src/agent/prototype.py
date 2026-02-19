"""
Customer Success Digital FTE — Prototype v0.2
==============================================
Incubation-phase prototype with improved doc retrieval (TF-IDF scoring),
enhanced escalation rules, sentiment analysis, and better channel formatting.

Improvements over v0.1:
  - Fixed "legal" false positive (requires legal *action* context)
  - Added escalation patterns: 2FA lockout, critical enterprise bugs, data loss, stuck ops
  - TF-IDF-based doc retrieval replaces naive keyword matching
  - Fixed WhatsApp truncation (sentence-boundary-aware)
  - Keyword-based sentiment analysis with score-driven tone adjustment
  - Better greeting/edge-case handling

Usage:
    python prototype.py                     # run 5 built-in test tickets
    python prototype.py --ticket-id TF-...  # run a specific ticket from sample-tickets.json
    python prototype.py --all               # run all 62 tickets
"""

import json
import math
import re
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from collections import Counter

# ── Paths ──────────────────────────────────────────────────────────────────

CONTEXT_DIR = Path(__file__).resolve().parent.parent.parent / "context"


# ── Data classes ───────────────────────────────────────────────────────────

@dataclass
class Ticket:
    id: str
    channel: str
    customer_name: str
    customer_email: str
    customer_plan: str
    subject: str
    message: str
    category: str = ""
    priority: str = ""
    sentiment: float = 0.5
    expected_action: str = ""
    should_escalate: bool = False
    escalation_reason: str = ""


@dataclass
class AgentResponse:
    ticket_id: str
    response_text: str
    should_escalate: bool
    escalation_reason: str
    confidence_score: float
    detected_sentiment: float = 0.5
    matched_docs: list = field(default_factory=list)
    detected_intent: str = ""


# ── Sentiment Analyzer ────────────────────────────────────────────────────

class SentimentAnalyzer:
    """Keyword-based sentiment scoring from -1 (very negative) to 1 (very positive)."""

    POSITIVE_WORDS = {
        # strong positive (weight 2)
        'love': 2, 'amazing': 2, 'excellent': 2, 'fantastic': 2, 'perfect': 2,
        'outstanding': 2, 'incredible': 2, 'wonderful': 2, 'brilliant': 2,
        # moderate positive (weight 1)
        'great': 1, 'good': 1, 'nice': 1, 'helpful': 1, 'thanks': 1, 'thank': 1,
        'appreciate': 1, 'happy': 1, 'pleased': 1, 'enjoy': 1, 'glad': 1,
        'awesome': 1, 'impressive': 1, 'smooth': 1, 'easy': 1, 'convenient': 1,
        'improved': 1, 'fast': 1, 'reliable': 1, 'intuitive': 1, 'clean': 1,
        'productive': 1, 'efficient': 1, 'solid': 1, 'useful': 1,
    }

    NEGATIVE_WORDS = {
        # strong negative (weight 3)
        'terrible': 3, 'worst': 3, 'garbage': 3, 'useless': 3, 'unacceptable': 3,
        'awful': 3, 'horrible': 3, 'disgusting': 3, 'pathetic': 3, 'hate': 3,
        'scam': 3,
        # moderate negative (weight 2)
        'broken': 2, 'frustrated': 2, 'frustrating': 2, 'angry': 2, 'annoying': 2,
        'furious': 2, 'ridiculous': 2, 'disappointed': 2, 'unresponsive': 2,
        'unusable': 2, 'failing': 2, 'disaster': 2, 'outraged': 2, 'ruined': 2,
        'wasted': 2,
        # mild negative (weight 1)
        'issue': 1, 'problem': 1, 'bug': 1, 'error': 1, 'stuck': 1,
        'slow': 1, 'confusing': 1, 'difficult': 1, 'crash': 1, 'crashing': 1,
        'missing': 1, 'lost': 1, 'fail': 1, 'failed': 1, 'wrong': 1,
        'concern': 1, 'worried': 1, 'trouble': 1, 'unfortunately': 1,
        'worse': 1, 'lag': 1, 'delay': 1, 'glitch': 1,
    }

    NEGATION_WORDS = {'not', "n't", 'no', 'never', 'neither', 'nobody', 'nothing',
                      'nowhere', 'hardly', 'barely', 'without'}

    INTENSIFIERS = {'very': 1.5, 'really': 1.5, 'extremely': 2.0, 'absolutely': 2.0,
                    'completely': 1.5, 'totally': 1.5, 'so': 1.3, 'incredibly': 2.0,
                    'beyond': 1.5, 'super': 1.5}

    def analyze(self, text: str) -> float:
        """Return sentiment score from -1.0 (very negative) to 1.0 (very positive)."""
        if not text or len(text.strip()) < 2:
            return 0.0  # neutral for empty/tiny messages

        words = re.findall(r"[a-z']+", text.lower())
        if not words:
            return 0.0

        pos_score = 0.0
        neg_score = 0.0
        prev_word = ""
        prev_prev_word = ""

        for word in words:
            multiplier = 1.0
            # Check if previous word is an intensifier
            if prev_word in self.INTENSIFIERS:
                multiplier = self.INTENSIFIERS[prev_word]

            # Check for negation (flips sentiment)
            negated = False
            if prev_word in self.NEGATION_WORDS or (
                prev_word.endswith("n't") or prev_prev_word in self.NEGATION_WORDS
            ):
                negated = True

            if word in self.POSITIVE_WORDS:
                weight = self.POSITIVE_WORDS[word] * multiplier
                if negated:
                    neg_score += weight * 0.5  # negated positive = mild negative
                else:
                    pos_score += weight

            if word in self.NEGATIVE_WORDS:
                weight = self.NEGATIVE_WORDS[word] * multiplier
                if negated:
                    pos_score += weight * 0.3  # negated negative = mild positive
                else:
                    neg_score += weight

            prev_prev_word = prev_word
            prev_word = word

        # ALL CAPS detection (anger signal)
        alpha_chars = re.sub(r'[^a-zA-Z]', '', text)
        if len(alpha_chars) > 15 and alpha_chars == alpha_chars.upper():
            neg_score += 5.0

        # Exclamation marks amplify existing sentiment
        excl_count = text.count('!')
        if excl_count >= 3:
            if neg_score > pos_score:
                neg_score *= 1.3
            elif pos_score > neg_score:
                pos_score *= 1.2

        # Normalize to -1..1 range
        total = pos_score + neg_score
        if total == 0:
            return 0.0

        raw = (pos_score - neg_score) / total  # range: -1 to 1
        return round(max(-1.0, min(1.0, raw)), 2)


# ── Knowledge Base (TF-IDF search) ────────────────────────────────────────

class KnowledgeBase:
    """Loads product-docs.md and provides TF-IDF-based section retrieval."""

    STOPWORDS = {
        'the', 'a', 'an', 'is', 'are', 'i', 'my', 'we', 'you', 'it', 'me',
        'to', 'for', 'of', 'in', 'on', 'and', 'or', 'but', 'not', 'how',
        'do', 'can', 'what', 'this', 'that', 'with', 'from', 'have', 'has',
        'be', 'was', 'were', 'been', 'does', 'did', 'will', 'would', 'if',
        'hi', 'hello', 'hey', 'thanks', 'thank', 'please', 'help', 'about',
        'so', 'at', 'by', 'as', 'our', 'your', 'its', 'all', 'any', 'up',
        'just', 'get', 'also', 'when', 'than', 'then', 'into', 'them',
        'more', 'some', 'could', 'should', 'would', 'there', 'their',
    }

    def __init__(self, docs_path: Path):
        self.sections = []
        self.doc_freq = Counter()  # document frequency per word
        self._load(docs_path)
        self._build_idf()

    def _load(self, path: Path):
        text = path.read_text(encoding="utf-8")
        parts = re.split(r'\n(?=#{2,3}\s)', text)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            lines = part.split("\n", 1)
            title = lines[0].lstrip("#").strip()
            body = lines[1] if len(lines) > 1 else ""
            words = self._tokenize(title + " " + body)
            word_set = set(words)
            self.sections.append({
                "title": title,
                "body": body,
                "full": part,
                "words": Counter(words),
                "word_set": word_set,
                "title_words": set(self._tokenize(title)),
            })

    def _build_idf(self):
        """Compute inverse document frequency for each word across all sections."""
        for section in self.sections:
            for word in section["word_set"]:
                self.doc_freq[word] += 1

    def _tokenize(self, text: str) -> list:
        words = re.findall(r'[a-z][a-z0-9]*', text.lower())
        return [w for w in words if w not in self.STOPWORDS and len(w) > 1]

    def search(self, query: str, top_k: int = 3) -> list:
        """TF-IDF scored search with title boost."""
        query_words = self._tokenize(query)
        if not query_words:
            return []

        query_tf = Counter(query_words)
        n_docs = len(self.sections)

        scored = []
        for section in self.sections:
            score = 0.0
            for word, q_count in query_tf.items():
                if word not in section["word_set"]:
                    continue
                # TF in document
                tf = section["words"][word]
                # IDF
                df = self.doc_freq.get(word, 1)
                idf = math.log(n_docs / df) + 1.0
                # TF-IDF contribution
                word_score = tf * idf * q_count

                # Title match gets a 3x boost
                if word in section["title_words"]:
                    word_score *= 3.0

                score += word_score

            if score > 0:
                scored.append((score, section))

        scored.sort(key=lambda x: -x[0])
        return [s[1] for s in scored[:top_k]]


# ── Escalation Engine ─────────────────────────────────────────────────────

class EscalationEngine:
    """Rule-based escalation detection based on escalation-rules.md."""

    # ALWAYS escalate — mandatory human handoff
    ALWAYS_ESCALATE_PATTERNS = {
        "billing": [
            r'\brefund\b',
            r'\bmoney\s*back\b',
            r'\bcharged\s*(twice|incorrectly|wrong)',
            r'\bduplicate\s*charge',
            r'\bbilling\s*dispute',
            r'\bdiscount\b',
            r'\bcustom\s*(pricing|invoice)',
            r'\bPO\s*number\b',
            r'\bpurchase\s*order\b',
            r'\bcharged\b.{0,40}\b(never\s*(upgraded|signed|agreed|authorized))',
            r'\b(unauthorized|unexpected|surprise)\s*(charge|billing|payment)',
        ],
        "legal": [
            # GDPR / compliance keywords (always escalate)
            r'\bgdpr\b',
            r'\bdata\s*deletion\b',
            r'\bright\s*to\s*(erasure|be\s*forgotten)',
            r'\bccpa\b',
            r'\bdpa\b',
            r'\bdata\s*processing\s*agreement\b',
            r'\bsoc\s*2\b',
            r'\bcompliance\s*(documentation|report|certification|audit)',
            # Legal *action* context — require action-related words nearby
            r'\blawyer\b',
            r'\battorney\b',
            r'\bsue\b',
            r'\bsubpoena\b',
            r'\blegal\s+(action|threat|team|department|counsel|dispute|proceeding|notice)',
            r'\b(threaten|filing|file)\s+(a\s+)?(lawsuit|complaint|dispute)',
        ],
        "security": [
            r'\bdata\s*breach\b',
            r'\bunauthorized\s*access\b',
            r'\bsecurity\s*(bug|vulnerability|concern|issue)\b',
            r'\bsuspicious\s*(activity|login)',
            r'\bpermission.{0,20}bypass\b',
            r'\bguest.{0,30}(edit|modify|change|move|delete).{0,20}(task|card|board|project)',
        ],
        "account": [
            r'\b(workspace|account)\s*deletion\b',
            r'\bownership\s*transfer\b',
            r'\bdeactivated\s*(email|account)\b',
            r'\btransfer\s*ownership\b',
        ],
    }

    # LIKELY escalate — use judgment
    LIKELY_ESCALATE_PATTERNS = {
        "human_requested": [
            r'\breal\s*person\b',
            r'\bhuman\s*(agent)?\b',
            r'\bspeak\s*to\s*(a\s*)?(manager|someone|person)\b',
            r'\btalk\s*to\s*(a\s*)?(manager|someone|person|human)\b',
            r'\btransfer\s*me\b',
        ],
        "churn_risk": [
            r'\bswitch(ing)?\s*to\s*(asana|trello|monday|competitor)\b',
            r'\bcancel\s*(my|our)\s*(account|subscription)\b',
            r'\bmigrat(e|ing)\s*(to|away)\b',
            r'\bconsidering\s*(switch|moving|leaving)\b',
        ],
        "angry": [
            r'\bgarbage\b', r'\bterrible\b', r'\bworst\b', r'\bunacceptable\b',
            r'\buseless\b', r'\bpathetic\b', r'\bdisgrace\b',
        ],
        "data_loss": [
            r'\bdata\s*loss\b',
            r'\blost\s*(work|data|tasks|files|hours|changes|progress)',
            r'\b(tasks?|data|files|work)\s*(disappeared|vanished|gone|missing|deleted)',
            r'\bdisappeared\b',
            r'\bvanished\b',
        ],
        "critical_enterprise_bug": [
            r'\b(critical|blocking|blocks)\s*(bug|issue|problem)\b.{0,40}\b(team|organization|company|workspace|everyone|all\s*users)',
            r'\b(feature|view|page|board|dashboard).{0,30}(not\s*load|stuck\s*on\s*spinner|timeout|unusable)\b.{0,40}\b(team|organization|users|workspace)',
            r'\b(entire|whole)\s*(team|organization|company|workspace)\b.{0,40}(block|impact|affect|stop)',
        ],
        "account_lockout": [
            r'\blocked\s*out\b.{0,40}(admin|workspace|entire|company|organization)',
            r'\b2fa\b.{0,40}(lost|locked|cannot|can\'t|no\s*access)',
            r'\bauthenticator\b.{0,30}(lost|broken|damaged|stolen)',
            r'\brecovery\s*codes?\b.{0,30}(lost|cannot|can\'t|missing)',
        ],
        "stuck_operations": [
            r'\b(export|import|sync|upload|download|migration).{0,60}(stuck|hanging|frozen|stalled|processing|pending)',
            r'\b(stuck|hanging|frozen)\s*(for|since|over)\s*\d+\s*(hour|day|week)',
            r'\bmore\s*than\s*\d+\s*(hour|day)',
            r'\b\d+\s*(hour|day|week)s?\b.{0,30}(still|not\s*complete|processing|pending)',
            r'\bstill\s*(show|display|say).{0,20}(processing|pending|waiting|queued)',
        ],
        "repeat_contact": [
            r'\b(second|third|fourth|2nd|3rd|4th)\s*time\b',
            r'\bagain\b',
            r'\bstill\s*not\b',
            r'\balready\s*(contacted|reported|emailed|told|asked)',
            r'\b(THIRD|SECOND)\s*TIME\b',
            r'\bthree\s*times\b',
        ],
    }

    SENTIMENT_ESCALATE_THRESHOLD = -0.3    # map to: very negative
    SENTIMENT_FLAG_THRESHOLD = -0.1        # map to: mildly negative

    def check(self, ticket: Ticket, detected_sentiment: float) -> tuple:
        """Returns (should_escalate: bool, reason: str, confidence_adjustment: float)."""
        message = ticket.message + " " + ticket.subject
        reasons = []
        confidence_penalty = 0.0

        # Check ALWAYS-escalate patterns
        always_matched = False
        for category, patterns in self.ALWAYS_ESCALATE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, message, re.IGNORECASE):
                    reasons.append(f"ALWAYS_ESCALATE: {category}")
                    confidence_penalty = max(confidence_penalty, 0.4)
                    always_matched = True
                    break  # one match per category is enough

        # Check LIKELY-escalate patterns
        likely_matched = False
        for category, patterns in self.LIKELY_ESCALATE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, message, re.IGNORECASE):
                    reasons.append(f"LIKELY_ESCALATE: {category}")
                    confidence_penalty = max(confidence_penalty, 0.25)
                    likely_matched = True
                    break

        # Sentiment-based escalation (using our detected sentiment, -1 to 1)
        if detected_sentiment <= self.SENTIMENT_ESCALATE_THRESHOLD:
            reasons.append(f"SENTIMENT: very negative ({detected_sentiment:.2f})")
            confidence_penalty = max(confidence_penalty, 0.3)
        elif detected_sentiment <= self.SENTIMENT_FLAG_THRESHOLD:
            reasons.append(f"SENTIMENT: negative ({detected_sentiment:.2f}) — flag for review")
            confidence_penalty = max(confidence_penalty, 0.1)

        # ALL CAPS detection (anger signal)
        alpha_chars = re.sub(r'[^a-zA-Z]', '', ticket.message)
        if len(alpha_chars) > 15 and alpha_chars == alpha_chars.upper():
            reasons.append("ANGER_SIGNAL: message is ALL CAPS")
            confidence_penalty = max(confidence_penalty, 0.35)

        # Enterprise + critical priority signal (contextual escalation)
        if ticket.customer_plan == "enterprise" and ticket.priority == "critical":
            if not always_matched:
                reasons.append("CONTEXT: enterprise customer + critical priority")
                confidence_penalty = max(confidence_penalty, 0.2)

        should_escalate = (
            always_matched
            or (likely_matched and confidence_penalty >= 0.2)
            or (len(reasons) >= 2 and confidence_penalty >= 0.2)
        )
        reason_text = "; ".join(reasons) if reasons else ""
        return should_escalate, reason_text, confidence_penalty


# ── Intent Detector ────────────────────────────────────────────────────────

class IntentDetector:
    """Keyword-based intent classification."""

    INTENT_PATTERNS = {
        "password_reset": [
            r'\bpassword\b', r'\blogin\b', r'\blog\s*in\b', r'\blocked\s*out\b',
            r'\b2fa\b', r'\bcredentials\b', r'\bsign\s*in\b',
        ],
        "integration_issue": [
            r'\bslack\b', r'\bgithub\b', r'\bgoogle\s*(drive|calendar)\b',
            r'\bzapier\b', r'\bteams\b', r'\bintegration\b', r'\bokta\b',
            r'\bsaml\b', r'\bsso\b',
        ],
        "sync_problem": [
            r'\bsync\b', r'\bnot\s*(updating|showing|appearing|syncing)\b',
            r'\boffline\b',
        ],
        "billing_inquiry": [
            r'\bbilling\b', r'\bcharged?\b', r'\brefund\b', r'\bpric(e|ing)\b',
            r'\bplan\b', r'\bsubscription\b', r'\binvoice\b', r'\bpayment\b',
            r'\bdiscount\b', r'\bcost\b',
        ],
        "how_to": [
            r'\bhow\s*(do|to|can)\b', r'\bwhere\s*(do|is|can)\b',
            r'\bset\s*up\b', r'\bcreate\b', r'\bimport\b', r'\bexport\b',
            r'\bwalk\s*me\s*through\b', r'\bstep[\s-]*by[\s-]*step\b',
            r'\bconfigure\b', r'\benable\b',
        ],
        "bug_report": [
            r'\bbug\b', r'\bnot\s*working\b', r'\bbroken\b', r'\bcrash(ing|es)?\b',
            r'\berror\b', r'\bfailing\b', r'\bstuck\b', r'\bglitch\b',
            r'\bnon.?functional\b',
        ],
        "feature_request": [
            r'\bfeature\s*request\b', r'\bwould\s*be\s*(great|nice|amazing)\b',
            r'\bcan\s*you\s*add\b', r'\bdark\s*mode\b', r'\bplease\s*add\b',
            r'\bsuggestion\b',
        ],
        "data_concern": [
            r'\bgdpr\b', r'\bdata\s*(deletion|export|residency|retention)\b',
            r'\bsoc\s*2\b', r'\bcompliance\b', r'\bdpa\b', r'\bdata\s*location\b',
        ],
        "notification_issue": [
            r'\bnotification\b', r'\balert\b', r'\bemail\s*notification\b',
            r'\bpush\s*notification\b',
        ],
        "mobile_issue": [
            r'\bapp\b.*\b(crash|not\s*working|slow|crashing)\b',
            r'\bmobile\b', r'\biphone\b', r'\bandroid\b', r'\bios\b',
        ],
        "greeting": [
            r'^[\s]*(hi|hello|hey|good\s*(morning|afternoon|evening))[\s!.,]*$',
        ],
        "unclear": [
            r'^.{0,5}$',
        ],
        "spam": [
            r'(buy\s*cheap|click\s*now|limited\s*time\s*offer|guaranteed.*returns)',
            r'(www\s*dot|\.biz|tempmail)',
        ],
    }

    def detect(self, message: str) -> str:
        message_lower = message.lower().strip()
        scores = {}
        for intent, patterns in self.INTENT_PATTERNS.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    score += 1
            if score > 0:
                scores[intent] = score

        if not scores:
            return "general_inquiry"

        # Spam detection has priority
        if "spam" in scores and scores["spam"] >= 2:
            return "spam"

        return max(scores, key=scores.get)


# ── Response Formatter ─────────────────────────────────────────────────────

class ResponseFormatter:
    """Channel-specific response formatting following brand-voice.md."""

    def format(self, channel: str, customer_name: str, body: str,
               ticket_id: str = "", is_escalation: bool = False,
               sentiment: float = 0.0) -> str:

        name = customer_name if customer_name not in ("Unknown", "", None) else "there"

        if channel == "gmail":
            return self._format_email(name, body, ticket_id, is_escalation, sentiment)
        elif channel == "whatsapp":
            return self._format_whatsapp(name, body, is_escalation, sentiment)
        elif channel == "web-form":
            return self._format_webform(name, body, ticket_id, is_escalation, sentiment)
        else:
            return body

    def _format_email(self, name: str, body: str, ticket_id: str,
                      is_escalation: bool, sentiment: float) -> str:
        greeting = f"Dear {name},"

        if is_escalation and sentiment < -0.2:
            empathy = ("I completely understand your frustration, and I'm sorry "
                       "for the trouble you've been experiencing. ")
        elif is_escalation:
            empathy = ("Thanks for reaching out. I want to make sure you get "
                       "the best help on this. ")
        elif sentiment < -0.2:
            empathy = ("I understand how frustrating this must be, and I appreciate "
                       "your patience. ")
        elif sentiment > 0.3:
            empathy = "Thanks for reaching out! "
        else:
            empathy = "Thanks for contacting TaskFlow Support! "

        ref = f"\n\nReference: {ticket_id}" if ticket_id else ""
        closing = ("\n\nBest regards,\nTaskFlow Support Team\n"
                   "support@techcorp.io")

        return f"{greeting}\n\n{empathy}{body}{ref}{closing}"

    def _format_whatsapp(self, name: str, body: str, is_escalation: bool,
                         sentiment: float) -> str:
        if is_escalation:
            if sentiment < -0.3:
                return (f"Hi {name}, I completely understand your frustration "
                        f"and I'm sorry for the trouble. I'm connecting you with "
                        f"our support team right now. They'll follow up shortly.")
            return (f"Hi {name}! I'm connecting you with our support team "
                    f"right now. They'll follow up shortly. Is there anything "
                    f"quick I can help with in the meantime?")

        # Format with emoji based on intent context
        formatted = self._whatsapp_truncate(body, max_chars=280)
        return f"Hi {name}!\n\n{formatted}"

    def _whatsapp_truncate(self, text: str, max_chars: int = 280) -> str:
        """Truncate at sentence boundaries, never mid-word or mid-list-item."""
        if len(text) <= max_chars:
            return text

        # Split into logical chunks: paragraphs first, then sentences
        # but DON'T split after numbered list items (e.g. "1." "2.")
        # Use negative lookbehind to avoid splitting after \d.
        sentences = re.split(r'(?<=[.!?])(?<!\d\.)(?<!\d\d\.)\s+', text)

        # Also split on newlines to handle list items as separate chunks
        chunks = []
        for s in sentences:
            for part in s.split('\n'):
                part = part.strip()
                if part:
                    chunks.append(part)

        result = []
        current_len = 0

        for chunk in chunks:
            new_len = current_len + len(chunk) + (1 if result else 0)
            if new_len <= max_chars:
                result.append(chunk)
                current_len = new_len
            else:
                break

        if result:
            truncated = "\n".join(result)
            if truncated != text:
                truncated += "\n\nWant me to explain more?"
            return truncated

        # Fallback: if first chunk is too long, truncate at last word boundary
        words = text.split()
        result_words = []
        current_len = 0
        for word in words:
            new_len = current_len + len(word) + (1 if result_words else 0)
            if new_len <= max_chars - 25:  # reserve space for "..."
                result_words.append(word)
                current_len = new_len
            else:
                break

        if result_words:
            return " ".join(result_words) + "...\n\nWant me to explain more?"

        return text[:max_chars]

    def _format_webform(self, name: str, body: str, ticket_id: str,
                        is_escalation: bool, sentiment: float) -> str:
        header = (f"Hi {name},\n\nThank you for contacting TaskFlow Support. "
                  f"We've received your request.")
        tid = f"\n\n**Ticket ID:** {ticket_id}" if ticket_id else ""

        if is_escalation and sentiment < -0.2:
            empathy = ("I understand your concern and I want to make sure this "
                       "gets the attention it deserves. ")
        elif is_escalation:
            empathy = ("I've reviewed your request and want to make sure you "
                       "get the most accurate help. ")
        else:
            empathy = ""

        footer = ("\n\nIf you need further assistance, you can reply to this "
                  "message or reach us at support@techcorp.io."
                  "\n\n-- TaskFlow Support Team")

        return f"{header}{tid}\n\n{empathy}{body}{footer}"


# ── Main Agent ─────────────────────────────────────────────────────────────

class CustomerSuccessAgent:
    """Prototype v0.2 — TF-IDF retrieval, enhanced escalation, sentiment analysis.

    Can operate stateless (handle_ticket) or stateful (handle_ticket_with_context)
    when connected to a ConversationManager.
    """

    def __init__(self, conversation_manager=None):
        docs_path = CONTEXT_DIR / "product-docs.md"
        self.kb = KnowledgeBase(docs_path)
        self.escalation = EscalationEngine()
        self.intent = IntentDetector()
        self.formatter = ResponseFormatter()
        self.sentiment = SentimentAnalyzer()
        self.conversations = conversation_manager  # optional

    def handle_ticket_with_context(self, ticket: Ticket) -> AgentResponse:
        """Handle a ticket using conversation history for context."""
        if not self.conversations:
            return self.handle_ticket(ticket)

        cm = self.conversations
        customer_id = ticket.customer_email.lower().strip()

        # Get or create conversation
        conv = cm.get_or_create_conversation(
            customer_id=customer_id,
            channel=ticket.channel,
            customer_name=ticket.customer_name,
            customer_plan=ticket.customer_plan,
        )

        # Detect sentiment
        detected_sentiment = self.sentiment.analyze(
            ticket.message + " " + ticket.subject
        )

        # Detect intent
        detected_intent = self.intent.detect(ticket.message)

        # Record the customer message
        cm.add_message(
            conversation_id=conv.conversation_id,
            role="customer",
            content=ticket.message,
            channel=ticket.channel,
            sentiment=detected_sentiment,
            intent=detected_intent,
            ticket_id=ticket.id,
        )

        # Check sentiment trend for auto-escalation
        trend = cm.check_sentiment_trend(conv.conversation_id)

        # Check cross-channel context
        cross_channel_ctx = cm.get_cross_channel_context(
            customer_id, ticket.channel
        )

        # Run normal escalation check
        should_escalate, esc_reason, confidence_penalty = self.escalation.check(
            ticket, detected_sentiment
        )

        # Merge sentiment-trend escalation
        if trend["should_escalate"] and not should_escalate:
            should_escalate = True
            esc_reason = (esc_reason + "; " if esc_reason else "") + \
                f"SENTIMENT_TREND: {trend['reason']}"
            confidence_penalty = max(confidence_penalty, 0.3)

        # Search knowledge base
        search_query = ticket.subject + " " + ticket.message
        matched_sections = self.kb.search(search_query, top_k=3)
        matched_titles = [s["title"] for s in matched_sections]

        # Calculate confidence
        confidence = self._calculate_confidence(
            detected_intent, matched_sections, ticket,
            confidence_penalty, detected_sentiment
        )

        # Generate response body (with cross-channel context prefix)
        response_text = self._generate_full_response(
            ticket, detected_intent, should_escalate, esc_reason,
            detected_sentiment, matched_sections, confidence,
            cross_channel_context=cross_channel_ctx,
        )

        # Record agent response
        cm.add_message(
            conversation_id=conv.conversation_id,
            role="agent",
            content=response_text,
            channel=ticket.channel,
            ticket_id=ticket.id,
        )

        # Update conversation state if escalated
        if should_escalate:
            cm.escalate_conversation(conv.conversation_id, esc_reason)

        return AgentResponse(
            ticket_id=ticket.id,
            response_text=response_text,
            should_escalate=should_escalate,
            escalation_reason=esc_reason,
            confidence_score=round(confidence, 2),
            detected_sentiment=detected_sentiment,
            matched_docs=matched_titles,
            detected_intent=detected_intent,
        )

    def _generate_full_response(self, ticket, detected_intent, should_escalate,
                                esc_reason, detected_sentiment, matched_sections,
                                confidence, cross_channel_context=None):
        """Generate formatted response, optionally prepending cross-channel context."""
        if detected_intent == "spam":
            return "[SPAM DETECTED — No response sent. Ticket auto-closed.]"

        # Build the body
        if should_escalate and confidence < 0.4:
            body = self._generate_escalation_response(ticket, esc_reason)
        elif detected_intent == "greeting":
            body = self._generate_greeting(ticket)
        elif detected_intent == "unclear":
            body = self._generate_unclear_response(ticket)
        else:
            body = self._generate_answer(
                detected_intent, matched_sections, ticket
            )

        # Prepend cross-channel context
        if cross_channel_context:
            body = cross_channel_context + "\n\n" + body

        return self.formatter.format(
            channel=ticket.channel,
            customer_name=ticket.customer_name,
            body=body,
            ticket_id=ticket.id,
            is_escalation=should_escalate,
            sentiment=detected_sentiment,
        )

    def handle_ticket(self, ticket: Ticket) -> AgentResponse:
        # 1. Analyze sentiment
        detected_sentiment = self.sentiment.analyze(
            ticket.message + " " + ticket.subject
        )

        # 2. Detect intent
        detected_intent = self.intent.detect(ticket.message)

        # 3. Check escalation rules (pass sentiment)
        should_escalate, esc_reason, confidence_penalty = self.escalation.check(
            ticket, detected_sentiment
        )

        # 4. Search knowledge base
        search_query = ticket.subject + " " + ticket.message
        matched_sections = self.kb.search(search_query, top_k=3)
        matched_titles = [s["title"] for s in matched_sections]

        # 5. Calculate confidence
        confidence = self._calculate_confidence(
            detected_intent, matched_sections, ticket,
            confidence_penalty, detected_sentiment
        )

        # 6. Generate response body
        if detected_intent == "spam":
            body = ""
            response_text = "[SPAM DETECTED — No response sent. Ticket auto-closed.]"
        elif should_escalate and confidence < 0.4:
            body = self._generate_escalation_response(ticket, esc_reason)
            response_text = self.formatter.format(
                channel=ticket.channel, customer_name=ticket.customer_name,
                body=body, ticket_id=ticket.id, is_escalation=True,
                sentiment=detected_sentiment,
            )
        elif detected_intent == "greeting":
            body = self._generate_greeting(ticket)
            response_text = self.formatter.format(
                channel=ticket.channel, customer_name=ticket.customer_name,
                body=body, ticket_id=ticket.id, is_escalation=False,
                sentiment=detected_sentiment,
            )
        elif detected_intent == "unclear":
            body = self._generate_unclear_response(ticket)
            response_text = self.formatter.format(
                channel=ticket.channel, customer_name=ticket.customer_name,
                body=body, ticket_id=ticket.id, is_escalation=False,
                sentiment=detected_sentiment,
            )
        else:
            body = self._generate_answer(detected_intent, matched_sections, ticket)
            response_text = self.formatter.format(
                channel=ticket.channel, customer_name=ticket.customer_name,
                body=body, ticket_id=ticket.id,
                is_escalation=should_escalate,
                sentiment=detected_sentiment,
            )

        return AgentResponse(
            ticket_id=ticket.id,
            response_text=response_text,
            should_escalate=should_escalate,
            escalation_reason=esc_reason,
            confidence_score=round(confidence, 2),
            detected_sentiment=detected_sentiment,
            matched_docs=matched_titles,
            detected_intent=detected_intent,
        )

    def _calculate_confidence(self, intent: str, matched_docs: list,
                              ticket: Ticket, penalty: float,
                              sentiment: float) -> float:
        base = 0.5

        # Boost if we found relevant docs
        if len(matched_docs) >= 2:
            base += 0.2
        elif len(matched_docs) == 1:
            base += 0.1

        # Boost for clear intent
        if intent not in ("general_inquiry", "unclear", "greeting", "spam"):
            base += 0.15

        # Boost for how-to and feature requests (easy categories)
        if intent in ("how_to", "feature_request"):
            base += 0.1

        # Penalize for short messages (less context)
        word_count = len(ticket.message.split())
        if word_count < 5:
            base -= 0.15
        elif word_count < 10:
            base -= 0.05

        # Penalize for very negative sentiment
        if sentiment < -0.3:
            base -= 0.1

        # Apply escalation penalty
        base -= penalty

        return max(0.0, min(1.0, base))

    def _generate_greeting(self, ticket: Ticket) -> str:
        """Handle greeting messages with channel-appropriate responses."""
        if ticket.channel == "whatsapp":
            return "How can I help you today? \U0001f44b"
        return "How can I help you today?"

    def _generate_unclear_response(self, ticket: Ticket) -> str:
        """Handle very short/unclear messages."""
        msg = ticket.message.strip()
        # Check for emoji-only messages
        if len(msg) <= 4 or not re.search(r'[a-zA-Z]', msg):
            if ticket.channel == "whatsapp":
                return "Is there anything I can help you with today? \U0001f60a"
            return "Is there anything I can help you with today?"

        if ticket.channel == "whatsapp":
            return "Could you tell me a bit more about what you need help with?"
        return ("Could you tell me a bit more about what you need help with? "
                "I'm happy to assist with any TaskFlow questions!")

    def _generate_answer(self, intent: str, docs: list, ticket: Ticket) -> str:
        """Generate a response body from matched documentation sections."""
        if not docs:
            return (
                "I want to make sure I give you the right answer. "
                "Could you provide a few more details about what you're trying to do? "
                "In the meantime, you can check our help center at app.taskflow.io/help."
            )

        # Use the best matching section
        best = docs[0]
        section_body = best["body"].strip()

        # Extract relevant portion (channel-aware length)
        max_chars = 600 if ticket.channel == "gmail" else 350
        excerpt = self._extract_relevant_excerpt(section_body, max_chars)

        # Build response based on intent
        if intent == "how_to":
            return (f"Great question! Here's how you can do this:\n\n{excerpt}\n\n"
                    f"Let me know if you need any clarification on these steps.")

        elif intent == "billing_inquiry":
            return (f"I understand billing questions are important. "
                    f"Here's the relevant information:\n\n{excerpt}\n\n"
                    f"If you need further assistance with billing, our team at "
                    f"billing@techcorp.io can help.")

        elif intent == "bug_report":
            return (f"I'm sorry you're running into this issue. Here are some "
                    f"troubleshooting steps that may help:\n\n{excerpt}\n\n"
                    f"If the problem persists after trying these steps, please "
                    f"let me know and I'll look into it further.")

        elif intent in ("sync_problem", "mobile_issue"):
            return (f"I understand how frustrating sync issues can be. "
                    f"Let's try these steps:\n\n{excerpt}\n\n"
                    f"If the issue continues, please let me know your app version "
                    f"and device details so I can investigate further.")

        elif intent == "integration_issue":
            return (f"Let me help you with that integration issue. "
                    f"Here's what I'd recommend:\n\n{excerpt}\n\n"
                    f"If reconnecting doesn't resolve the issue, please let me "
                    f"know and I'll dig deeper.")

        elif intent == "feature_request":
            return ("That's a great suggestion — thanks for sharing it! "
                    "I've logged this feedback for our product team. While I can't "
                    "share specific timeline commitments, this is the kind of input "
                    "that helps shape our roadmap. Is there anything else I can help with?")

        elif intent == "password_reset":
            return (f"I understand how frustrating it is to be locked out. "
                    f"Here's how to regain access:\n\n{excerpt}\n\n"
                    f"If you're still having trouble after these steps, let me "
                    f"know and I'll help further.")

        elif intent == "notification_issue":
            return (f"Let's get your notifications sorted out. "
                    f"Here's what to check:\n\n{excerpt}\n\n"
                    f"Let me know if any of these steps help!")

        elif intent == "data_concern":
            return ("I've received your request regarding data handling. "
                    "This is being forwarded to our compliance team who will "
                    "respond within the required timeframe. You'll receive a "
                    "confirmation shortly.")

        else:
            return (f"Thanks for reaching out! Based on your question, here's "
                    f"the relevant information:\n\n{excerpt}\n\n"
                    f"Is there anything else I can help with?")

    def _extract_relevant_excerpt(self, section_body: str, max_chars: int) -> str:
        """Extract a clean excerpt from a doc section, respecting structure."""
        lines = section_body.split("\n")
        relevant_lines = []
        char_count = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Skip table header separators
            if stripped.startswith('|') and set(stripped.replace('|', '').strip()) <= {'-', ' '}:
                continue

            relevant_lines.append(stripped)
            char_count += len(stripped)
            if char_count > max_chars:
                break

        return "\n".join(relevant_lines)

    def _generate_escalation_response(self, ticket: Ticket, reason: str) -> str:
        """Generate a response acknowledging the issue and promising human follow-up."""
        sla_map = {"enterprise": "1 hour", "pro": "4 hours", "free": "24 hours"}
        sla = sla_map.get(ticket.customer_plan, "24 hours")

        if "billing" in reason.lower() or "refund" in reason.lower():
            return (
                f"I understand how important billing matters are, and I want to "
                f"make sure this is handled properly. I've forwarded your request "
                f"to our billing team, who will review it and get back to you "
                f"within {sla}. Your reference number is {ticket.id}."
            )
        elif any(kw in reason.lower() for kw in ("legal", "gdpr", "compliance", "soc", "dpa")):
            return (
                f"I've received your request and it's being forwarded to our "
                f"compliance team immediately. You'll receive a confirmation "
                f"within 72 hours, and the request will be fulfilled within the "
                f"required timeframe. Your reference number is {ticket.id}."
            )
        elif "human" in reason.lower():
            return (
                f"Of course! I'm connecting you with a member of our support "
                f"team right now. They'll follow up within {sla}."
            )
        elif any(kw in reason.lower() for kw in ("sentiment", "anger", "all caps")):
            return (
                f"I completely understand your frustration, and I'm sorry for "
                f"the trouble you've been experiencing. I want to make sure this "
                f"gets the attention it deserves. I'm connecting you with a "
                f"senior member of our support team who will personally follow "
                f"up within {sla}. Your reference number is {ticket.id}."
            )
        elif "data_loss" in reason.lower() or "disappeared" in reason.lower():
            return (
                f"I understand how concerning it is when data appears to be "
                f"missing. I'm treating this as a high priority and connecting "
                f"you with our engineering team who will investigate immediately. "
                f"They'll follow up within {sla}. Your reference number is "
                f"{ticket.id}."
            )
        elif "lockout" in reason.lower() or "2fa" in reason.lower():
            return (
                f"I understand being locked out of your account is urgent. "
                f"I'm escalating this to our support team who can verify your "
                f"identity and help you regain access. They'll reach out within "
                f"{sla}. Your reference number is {ticket.id}."
            )
        elif "stuck" in reason.lower() or "export" in reason.lower():
            return (
                f"I can see this operation is taking longer than expected. "
                f"I'm escalating this to our engineering team to investigate "
                f"and resolve the issue. They'll follow up within {sla}. "
                f"Your reference number is {ticket.id}."
            )
        else:
            return (
                f"I want to make sure you get the most accurate help on this. "
                f"I'm connecting you with a specialist on our team who will "
                f"follow up within {sla}. Your reference number is {ticket.id}."
            )


# ── Test Runner ────────────────────────────────────────────────────────────

def load_tickets() -> list:
    tickets_path = CONTEXT_DIR / "sample-tickets.json"
    with open(tickets_path, encoding="utf-8") as f:
        data = json.load(f)
    return [Ticket(**t) for t in data["tickets"]]


def print_result(resp: AgentResponse, ticket: Ticket):
    """Pretty-print a test result."""
    esc_icon = "YES" if resp.should_escalate else "no"
    expected_esc = "YES" if ticket.should_escalate else "no"
    match = "CORRECT" if resp.should_escalate == ticket.should_escalate else "MISMATCH"

    print(f"\n{'='*70}")
    print(f"TICKET: {ticket.id} [{ticket.channel}] [{ticket.customer_plan}]")
    print(f"FROM:   {ticket.customer_name} <{ticket.customer_email}>")
    print(f"SUBJECT: {ticket.subject}")
    msg_preview = ticket.message[:120].replace('\n', ' ')
    print(f"MESSAGE: {msg_preview}{'...' if len(ticket.message) > 120 else ''}")
    print(f"-"*70)
    print(f"INTENT:       {resp.detected_intent}")
    print(f"SENTIMENT:    {resp.detected_sentiment:+.2f} (ground truth: {ticket.sentiment:.2f})")
    print(f"CONFIDENCE:   {resp.confidence_score}")
    print(f"ESCALATE:     {esc_icon} (expected: {expected_esc}) [{match}]")
    if resp.escalation_reason:
        print(f"ESC REASON:   {resp.escalation_reason}")
    print(f"MATCHED DOCS: {resp.matched_docs}")
    print(f"-"*70)
    print(f"RESPONSE:")
    print(resp.response_text)
    print(f"{'='*70}")


def run_tests():
    """Run 5 diverse test tickets + full dataset analysis."""
    # Fix encoding for Windows
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        os.environ["PYTHONIOENCODING"] = "utf-8"

    agent = CustomerSuccessAgent()
    all_tickets = load_tickets()
    ticket_map = {t.id: t for t in all_tickets}

    # 5 diverse test tickets
    test_ids = [
        "TF-20260216-0022",  # How-to: recurring tasks (gmail, easy, no escalation)
        "TF-20260216-0029",  # Technical: mobile app crashing (whatsapp, short)
        "TF-20260216-0006",  # Billing: refund request (gmail, should escalate)
        "TF-20260216-0045",  # Angry customer: ALL CAPS (whatsapp, should escalate)
        "TF-20260216-0038",  # Edge case: just "hi" (whatsapp, minimal)
    ]

    results = []
    for tid in test_ids:
        ticket = ticket_map[tid]
        resp = agent.handle_ticket(ticket)
        results.append((resp, ticket))
        print_result(resp, ticket)

    # Summary
    print(f"\n{'='*70}")
    print("TEST SUMMARY (5 selected tickets)")
    print(f"{'='*70}")
    correct = sum(1 for r, t in results if r.should_escalate == t.should_escalate)
    print(f"Escalation accuracy: {correct}/{len(results)} ({correct/len(results)*100:.0f}%)")
    avg_conf = sum(r.confidence_score for r, _ in results) / len(results)
    print(f"Average confidence: {avg_conf:.2f}")
    avg_sent = sum(r.detected_sentiment for r, _ in results) / len(results)
    print(f"Average detected sentiment: {avg_sent:+.2f}")

    # Full dataset
    print(f"\n{'='*70}")
    print(f"FULL DATASET ESCALATION ACCURACY ({len(all_tickets)} tickets)")
    print(f"{'='*70}")
    correct_total = 0
    false_positives = []
    false_negatives = []
    sentiment_errors = []

    for ticket in all_tickets:
        resp = agent.handle_ticket(ticket)
        if resp.should_escalate == ticket.should_escalate:
            correct_total += 1
        elif resp.should_escalate and not ticket.should_escalate:
            false_positives.append((ticket.id, resp.escalation_reason))
        else:
            false_negatives.append((ticket.id, ticket.escalation_reason or ""))

        # Track sentiment accuracy
        # Map ground truth 0-1 to our -1..1 scale: gt_mapped = (gt - 0.5) * 2
        gt_mapped = (ticket.sentiment - 0.5) * 2
        error = abs(resp.detected_sentiment - gt_mapped)
        sentiment_errors.append(error)

    n = len(all_tickets)
    print(f"Correct: {correct_total}/{n} ({correct_total/n*100:.0f}%)")

    if false_positives:
        print(f"\nFalse positives (agent escalated, shouldn't have):")
        for tid, reason in false_positives:
            print(f"  {tid}: {reason}")

    if false_negatives:
        print(f"\nFalse negatives (agent didn't escalate, should have):")
        for tid, reason in false_negatives:
            print(f"  {tid}: {reason}")

    # Sentiment stats
    avg_err = sum(sentiment_errors) / len(sentiment_errors)
    print(f"\nSentiment Analysis:")
    print(f"  Mean absolute error (vs ground truth): {avg_err:.2f}")
    print(f"  Sentiment range detected: {min(r.detected_sentiment for r in [agent.handle_ticket(t) for t in all_tickets[:5]]):.2f} to {max(r.detected_sentiment for r in [agent.handle_ticket(t) for t in all_tickets[:5]]):.2f}")

    # Channel examples
    print(f"\n{'='*70}")
    print("CHANNEL FORMAT EXAMPLES")
    print(f"{'='*70}")

    # Pick one example per channel
    channel_examples = {
        "gmail": "TF-20260216-0004",     # how-to automations
        "whatsapp": "TF-20260216-0029",  # mobile crash
        "web-form": "TF-20260216-0048",  # how-to subtasks
    }
    for channel, tid in channel_examples.items():
        ticket = ticket_map[tid]
        resp = agent.handle_ticket(ticket)
        print(f"\n--- {channel.upper()} Example ({tid}) ---")
        print(resp.response_text)
        print()


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--ticket-id":
        if sys.platform == "win32":
            sys.stdout.reconfigure(encoding="utf-8")
        agent = CustomerSuccessAgent()
        all_tickets = load_tickets()
        ticket_map = {t.id: t for t in all_tickets}
        tid = sys.argv[2]
        if tid in ticket_map:
            resp = agent.handle_ticket(ticket_map[tid])
            print_result(resp, ticket_map[tid])
        else:
            print(f"Ticket {tid} not found. Available: {list(ticket_map.keys())[:5]}...")
    elif len(sys.argv) > 1 and sys.argv[1] == "--all":
        if sys.platform == "win32":
            sys.stdout.reconfigure(encoding="utf-8")
        agent = CustomerSuccessAgent()
        all_tickets = load_tickets()
        for ticket in all_tickets:
            resp = agent.handle_ticket(ticket)
            print_result(resp, ticket)
    else:
        run_tests()
