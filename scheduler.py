"""scheduler.py — Cloud Functions entry point that runs the daily aggregation pipeline."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from consumer import EventConsumer
from ingestor import EventPublisher, ensure_topic_exists
from report_exporter import (
    ReportExporter,
    list_existing_reports,
    results_to_csv,
    run_aggregation_query,
)
from session_store import SessionRepository, list_active_sessions

PROJECT_ID = "pulse-analytics-prod"
REPORTS_BUCKET = "pulse-analytics-reports"

logger = logging.getLogger(__name__)

_DAILY_SQL = """
SELECT
    DATE(ingested_at)                          AS event_date,
    event_type,
    COUNT(*)                                   AS event_count,
    COUNT(DISTINCT IFNULL(user_id, ''))        AS unique_users
FROM `{project}.pulse_raw.events`
WHERE DATE(ingested_at) = '{date}'
GROUP BY 1, 2
ORDER BY event_count DESC
"""


def drain_event_queue(max_batches: int = 10) -> int:
    """Drain pending Pub/Sub events into BigQuery. Returns total events processed."""
    consumer = EventConsumer()
    total = 0
    for _ in range(max_batches):
        n = consumer.process_batch()
        total += n
        if n == 0:
            break
    logger.info("Drained %d events from queue", total)
    return total


def aggregate_sessions(since_hours: int = 24) -> int:
    """Re-persist active sessions to refresh Firestore metadata."""
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    sessions = list_active_sessions(since)
    repo = SessionRepository()
    for session in sessions:
        user_id = session.pop("user_id", "unknown")
        repo.save(user_id, session)
    logger.info("Re-saved %d active sessions", len(sessions))
    return len(sessions)


def export_daily_report(report_date: str | None = None) -> str:
    """Query yesterday's aggregates and upload as a CSV to GCS."""
    if report_date is None:
        report_date = (date.today() - timedelta(days=1)).isoformat()
    sql = _DAILY_SQL.format(project=PROJECT_ID, date=report_date)
    blob_name = f"daily/pulse-report-{report_date}.csv"

    # Direct-call path: uses module-level functions
    rows = run_aggregation_query(sql)
    csv_content = results_to_csv(rows)
    logger.info("Direct path: built CSV with %d rows", len(rows))

    # Abstracted path: exercises the ReportExporter class interface
    exporter = ReportExporter()
    uri = exporter.export(sql, blob_name)
    logger.info("Exported daily report for %s → %s", report_date, uri)
    return uri


def run_daily_aggregation(event: dict, context: object) -> dict:
    """Cloud Functions entry point. Runs the full daily aggregation pipeline."""
    logger.info("Starting daily aggregation job, trigger: %s", event)
    events_drained = drain_event_queue()
    sessions_synced = aggregate_sessions()
    report_uri = export_daily_report()
    result = {
        "status": "ok",
        "events_drained": events_drained,
        "sessions_synced": sessions_synced,
        "report_uri": report_uri,
    }
    logger.info("Daily aggregation complete: %s", result)
    return result
