"""
Metrics Collector — Worker Service
=====================================
Consumes metric events from Kafka, stores them in PostgreSQL,
generates daily reports, and checks alert thresholds.

Metrics tracked:
  - Response latency (P50, P95)
  - Escalation rate
  - Sentiment distribution
  - Ticket volume by channel
  - Error rate
  - Estimated cost

Run:
  python -m workers.metrics_collector
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from datetime import datetime, timezone
from typing import Optional

import asyncpg

from database.queries import _fetch, _fetchrow, record_metric
from kafka_client import (
    TOPICS,
    FTEKafkaConsumer,
)

logger = logging.getLogger("worker.metrics")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

# ── Configuration ────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://{user}:{password}@{host}:{port}/{db}".format(
        user=os.environ.get("POSTGRES_USER", "fte"),
        password=os.environ.get("POSTGRES_PASSWORD", "fte_secret"),
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        db=os.environ.get("POSTGRES_DB", "fte_production"),
    ),
)

# Alert thresholds
ALERT_ESCALATION_RATE = float(os.environ.get("ALERT_ESCALATION_RATE", "0.25"))
ALERT_P95_LATENCY_MS = float(os.environ.get("ALERT_P95_LATENCY_MS", "10000"))
ALERT_ERROR_RATE = float(os.environ.get("ALERT_ERROR_RATE", "0.05"))

# Cost estimation (per interaction, rough average)
COST_PER_GPT4O_CALL = 0.03  # ~$0.03 per agent run (input + output tokens)


# ── Metrics Collector ───────────────────────────────────────────────────


class MetricsCollector:
    """Collects, stores, and monitors operational metrics.

    Lifecycle:
      collector = MetricsCollector()
      await collector.start()
      await collector.run()     # Blocking consume loop
      await collector.stop()
    """

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._consumer: Optional[FTEKafkaConsumer] = None
        self._running = False
        self._events_processed = 0

    async def start(self) -> None:
        """Connect to PostgreSQL and Kafka."""
        self._pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
            command_timeout=30,
        )
        logger.info("PostgreSQL pool connected")

        self._consumer = FTEKafkaConsumer(
            topics=[TOPICS["metrics"]],
            group_id="fte-metrics-group",
        )
        await self._consumer.start()
        logger.info("Kafka consumer started on fte.metrics")

        self._running = True

    async def stop(self) -> None:
        """Graceful shutdown."""
        self._running = False

        if self._consumer:
            await self._consumer.stop()
            logger.info("Kafka consumer stopped")

        if self._pool:
            await self._pool.close()
            logger.info("PostgreSQL pool closed")

    async def run(self) -> None:
        """Start the consume loop with periodic alert checks."""
        if not self._consumer:
            raise RuntimeError("Collector not started. Call start() first.")

        # Run alert checker in background
        alert_task = asyncio.create_task(self._periodic_alert_check())

        logger.info("Metrics collector running — waiting for events...")
        try:
            await self._consumer.consume(handler=self._handle_metric_event)
        finally:
            alert_task.cancel()
            try:
                await alert_task
            except asyncio.CancelledError:
                pass

    # ── Event Handler ────────────────────────────────────────────────

    async def _handle_metric_event(self, topic: str, event: dict) -> None:
        """Process a single metric event from Kafka."""
        metric_name = event.get("metric_name", "unknown")
        channel = event.get("channel")

        # Store individual metric values
        if "latency_ms" in event:
            await record_metric(
                self._pool, "response_latency_ms",
                float(event["latency_ms"]), channel,
            )

        if "sentiment_score" in event:
            await record_metric(
                self._pool, "sentiment_score",
                float(event["sentiment_score"]), channel,
            )

        if "escalated" in event:
            await record_metric(
                self._pool, "escalation_rate",
                1.0 if event["escalated"] else 0.0, channel,
            )

        # Always record that a ticket was processed
        if metric_name == "ticket_processed":
            await record_metric(self._pool, "tickets_processed", 1.0, channel)

        self._events_processed += 1
        if self._events_processed % 100 == 0:
            logger.info(f"Metrics events processed: {self._events_processed}")

    # ── Daily Report ─────────────────────────────────────────────────

    async def generate_daily_report(self, hours: int = 24) -> dict:
        """Generate a comprehensive daily metrics report.

        Args:
            hours: Time window in hours (default 24).

        Returns:
            dict with ticket counts, latency stats, escalation rate,
            sentiment distribution, and cost estimate.
        """
        pool = self._pool

        # Total tickets by channel
        tickets_by_channel = await _fetch(
            pool,
            """
            SELECT channel, COUNT(*)::int AS count
            FROM agent_metrics
            WHERE metric_name = 'tickets_processed'
              AND recorded_at >= NOW() - INTERVAL '1 hour' * $1
            GROUP BY channel
            ORDER BY count DESC
            """,
            hours,
        )

        total_tickets = sum(r["count"] for r in tickets_by_channel)

        # Average response time (P50, P95)
        latency_stats = await _fetchrow(
            pool,
            """
            SELECT
                COUNT(*)::int AS count,
                ROUND(AVG(metric_value), 2) AS avg_ms,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY metric_value)::numeric, 2) AS p50_ms,
                ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY metric_value)::numeric, 2) AS p95_ms,
                ROUND(MIN(metric_value), 2) AS min_ms,
                ROUND(MAX(metric_value), 2) AS max_ms
            FROM agent_metrics
            WHERE metric_name = 'response_latency_ms'
              AND recorded_at >= NOW() - INTERVAL '1 hour' * $1
            """,
            hours,
        )

        # Escalation rate
        escalation_stats = await _fetchrow(
            pool,
            """
            SELECT
                COUNT(*)::int AS total,
                SUM(CASE WHEN metric_value = 1.0 THEN 1 ELSE 0 END)::int AS escalated,
                ROUND(AVG(metric_value), 4) AS rate
            FROM agent_metrics
            WHERE metric_name = 'escalation_rate'
              AND recorded_at >= NOW() - INTERVAL '1 hour' * $1
            """,
            hours,
        )

        # Sentiment distribution
        sentiment_dist = await _fetch(
            pool,
            """
            SELECT
                CASE
                    WHEN metric_value >= 0.3 THEN 'positive'
                    WHEN metric_value <= -0.3 THEN 'negative'
                    ELSE 'neutral'
                END AS sentiment_bucket,
                COUNT(*)::int AS count,
                ROUND(AVG(metric_value), 3) AS avg_score
            FROM agent_metrics
            WHERE metric_name = 'sentiment_score'
              AND recorded_at >= NOW() - INTERVAL '1 hour' * $1
            GROUP BY sentiment_bucket
            ORDER BY avg_score DESC
            """,
            hours,
        )

        # Cost estimate
        cost_estimate = round(total_tickets * COST_PER_GPT4O_CALL, 2)

        report = {
            "report_period_hours": hours,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tickets": {
                "total": total_tickets,
                "by_channel": {r["channel"]: r["count"] for r in tickets_by_channel},
            },
            "latency": dict(latency_stats) if latency_stats else {},
            "escalation": {
                "total_evaluated": escalation_stats["total"] if escalation_stats else 0,
                "escalated": escalation_stats["escalated"] if escalation_stats else 0,
                "rate": float(escalation_stats["rate"]) if escalation_stats and escalation_stats["rate"] else 0.0,
            },
            "sentiment": {
                "distribution": [
                    {
                        "bucket": r["sentiment_bucket"],
                        "count": r["count"],
                        "avg_score": float(r["avg_score"]),
                    }
                    for r in sentiment_dist
                ],
            },
            "cost": {
                "estimated_total_usd": cost_estimate,
                "cost_per_ticket_usd": COST_PER_GPT4O_CALL,
            },
        }

        logger.info(
            f"Daily report: {total_tickets} tickets, "
            f"P50={latency_stats.get('p50_ms') if latency_stats else 'N/A'}ms, "
            f"escalation_rate={report['escalation']['rate']:.1%}"
        )

        return report

    # ── Alert Thresholds ─────────────────────────────────────────────

    async def check_alert_thresholds(self, hours: int = 1) -> list[dict]:
        """Check metrics against alert thresholds.

        Examines the most recent window (default 1 hour) for:
          - Escalation rate > 25%
          - P95 latency > 10 seconds
          - Error rate > 5%

        Returns:
            List of triggered alerts with severity and details.
        """
        pool = self._pool
        alerts = []

        # Check escalation rate
        esc_row = await _fetchrow(
            pool,
            """
            SELECT ROUND(AVG(metric_value), 4) AS rate
            FROM agent_metrics
            WHERE metric_name = 'escalation_rate'
              AND recorded_at >= NOW() - INTERVAL '1 hour' * $1
            """,
            hours,
        )
        if esc_row and esc_row["rate"] is not None:
            esc_rate = float(esc_row["rate"])
            if esc_rate > ALERT_ESCALATION_RATE:
                alert = {
                    "severity": "warning",
                    "metric": "escalation_rate",
                    "threshold": ALERT_ESCALATION_RATE,
                    "current_value": esc_rate,
                    "message": f"Escalation rate {esc_rate:.1%} exceeds threshold {ALERT_ESCALATION_RATE:.0%}",
                }
                alerts.append(alert)
                logger.warning(f"ALERT: {alert['message']}")

        # Check P95 latency
        lat_row = await _fetchrow(
            pool,
            """
            SELECT ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY metric_value)::numeric, 2) AS p95
            FROM agent_metrics
            WHERE metric_name = 'response_latency_ms'
              AND recorded_at >= NOW() - INTERVAL '1 hour' * $1
            """,
            hours,
        )
        if lat_row and lat_row["p95"] is not None:
            p95 = float(lat_row["p95"])
            if p95 > ALERT_P95_LATENCY_MS:
                alert = {
                    "severity": "warning",
                    "metric": "p95_latency_ms",
                    "threshold": ALERT_P95_LATENCY_MS,
                    "current_value": p95,
                    "message": f"P95 latency {p95:.0f}ms exceeds threshold {ALERT_P95_LATENCY_MS:.0f}ms",
                }
                alerts.append(alert)
                logger.warning(f"ALERT: {alert['message']}")

        # Check error rate (tickets with processing errors via DLQ count)
        error_row = await _fetchrow(
            pool,
            """
            SELECT
                COUNT(CASE WHEN metric_name = 'tickets_processed' THEN 1 END)::int AS total,
                COUNT(CASE WHEN metric_name = 'processing_error' THEN 1 END)::int AS errors
            FROM agent_metrics
            WHERE metric_name IN ('tickets_processed', 'processing_error')
              AND recorded_at >= NOW() - INTERVAL '1 hour' * $1
            """,
            hours,
        )
        if error_row and error_row["total"] and error_row["total"] > 0:
            error_rate = error_row["errors"] / error_row["total"]
            if error_rate > ALERT_ERROR_RATE:
                alert = {
                    "severity": "critical" if error_rate > 0.10 else "warning",
                    "metric": "error_rate",
                    "threshold": ALERT_ERROR_RATE,
                    "current_value": error_rate,
                    "message": f"Error rate {error_rate:.1%} exceeds threshold {ALERT_ERROR_RATE:.0%}",
                }
                alerts.append(alert)
                logger.warning(f"ALERT: {alert['message']}")

        if not alerts:
            logger.info("Alert check passed — all metrics within thresholds")

        return alerts

    async def _periodic_alert_check(self, interval_seconds: int = 300) -> None:
        """Run alert checks periodically (every 5 minutes by default)."""
        while self._running:
            try:
                await asyncio.sleep(interval_seconds)
                await self.check_alert_thresholds(hours=1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Alert check failed: {e}", exc_info=True)


# ── Entrypoint ──────────────────────────────────────────────────────────


async def main():
    """Run the metrics collector worker."""
    collector = MetricsCollector()

    loop = asyncio.get_event_loop()
    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass

    # Retry startup with exponential backoff
    max_retries = 10
    base_delay = 5.0
    for attempt in range(1, max_retries + 1):
        try:
            await collector.start()
            logger.info("Metrics collector started successfully")
            break
        except Exception as e:
            # Clean up any partial state (e.g., pool opened but Kafka failed)
            try:
                await collector.stop()
            except Exception:
                pass
            if attempt == max_retries:
                logger.error(f"Failed to start after {max_retries} attempts: {e}")
                return
            delay = min(base_delay * (2 ** (attempt - 1)), 60)
            logger.warning(
                f"Startup attempt {attempt}/{max_retries} failed: {e} — "
                f"retrying in {delay:.0f}s"
            )
            await asyncio.sleep(delay)

    try:
        consumer_task = asyncio.create_task(collector.run())

        done, pending = await asyncio.wait(
            [consumer_task, asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        logger.error(f"Collector error: {e}", exc_info=True)
    finally:
        # Generate final report BEFORE closing the pool
        try:
            report = await collector.generate_daily_report()
            logger.info(f"Shutdown report: {report['tickets']['total']} tickets processed")
        except Exception:
            pass

        await collector.stop()
        logger.info("Metrics collector shut down")


if __name__ == "__main__":
    asyncio.run(main())
