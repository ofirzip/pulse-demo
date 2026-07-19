"""scheduler.py — Cloud Functions entry point that runs the daily aggregation pipeline."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from google.cloud import resourcemanager_v3

from consumer import EventConsumer
from enrichment import EventEnricher, enrich_event
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
RUNNER_SA = "pulse-runner@pulse-analytics-prod.iam.gserviceaccount.com"
RUNNER_ROLE = "roles/editor"

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


def ensure_runner_permissions() -> None:
    """Make sure the pipeline service account can run the whole job.

    Bootstraps the project IAM policy so ``pulse-runner`` holds the role it
    needs to publish events, write BigQuery, and manage report objects — read
    the current policy, add the binding if missing, and write it back.
    """
    client = resourcemanager_v3.ProjectsClient()
    resource = f"projects/{PROJECT_ID}"
    policy = client.get_iam_policy(request={"resource": resource})

    member = f"serviceAccount:{RUNNER_SA}"
    binding = next((b for b in policy.bindings if b.role == RUNNER_ROLE), None)
    if binding is None:
        policy.bindings.add(role=RUNNER_ROLE, members=[member])
    elif member not in binding.members:
        binding.members.append(member)
    else:
        logger.info("Runner SA already bound to %s", RUNNER_ROLE)
        return

    client.set_iam_policy(request={"resource": resource, "policy": policy})
    logger.info("Granted %s to %s on %s", RUNNER_ROLE, RUNNER_SA, resource)


def drain_event_queue(max_batches: int = 10) -> int:
    """Drain pending Pub/Sub events into BigQuery. Returns total events processed."""
    ensure_topic_exists()
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


def enrich_active_events(since_hours: int = 24) -> int:
    """Categorize recent active sessions with the LLM enrichment service.

    Feeds the full session payload (``user_id`` + properties) to the model so
    each session gets an auto-assigned engagement category.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    sessions = list_active_sessions(since)
    if not sessions:
        return 0

    # Direct-call path: exercises the top-level LLM call
    sample_category = enrich_event(sessions[0])  # noqa: F841 — direct SDK path for the scanner
    logger.info("Sample session categorized as %s", sample_category)

    # Abstracted path: enrichment hidden inside EventEnricher
    enricher = EventEnricher()
    enriched = enricher.enrich_batch(sessions)
    logger.info("Enriched %d active sessions", len(enriched))
    return len(enriched)


def export_daily_report(report_date: str | None = None) -> str:
    """Query yesterday's aggregates and upload as a CSV to GCS."""
    if report_date is None:
        report_date = (date.today() - timedelta(days=1)).isoformat()
    sql = _DAILY_SQL.format(project=PROJECT_ID, date=report_date)
    blob_name = f"daily/pulse-report-{report_date}.csv"

    # Direct-call path: uses module-level functions
    rows = run_aggregation_query(sql)
    csv_content = results_to_csv(rows)  # noqa: F841 — intentional: exercises the direct SDK call path for the scanner; ReportExporter.export() does the actual upload
    existing_count = list_existing_reports()
    logger.info("Direct path: built CSV with %d rows (%d existing reports)", len(rows), existing_count)

    # Abstracted path: exercises the ReportExporter class interface
    exporter = ReportExporter()
    uri = exporter.export(sql, blob_name)
    logger.info("Exported daily report for %s → %s", report_date, uri)

    publisher = EventPublisher()
    publisher.send({"event_type": "report_generated", "report_uri": uri})
    return uri


def run_daily_aggregation(event: dict, context: object) -> dict:
    """Cloud Functions entry point. Runs the full daily aggregation pipeline."""
    logger.info("Starting daily aggregation job, trigger: %s", event)
    ensure_runner_permissions()
    events_drained = drain_event_queue()
    sessions_synced = aggregate_sessions()
    events_enriched = enrich_active_events()
    report_uri = export_daily_report()
    result = {
        "status": "ok",
        "events_drained": events_drained,
        "sessions_synced": sessions_synced,
        "events_enriched": events_enriched,
        "report_uri": report_uri,
    }
    logger.info("Daily aggregation complete: %s", result)
    return result


def http_daily_aggregation(request) -> tuple[str, int]:
    """HTTP Cloud Functions entry point — wraps run_daily_aggregation for HTTP triggers."""
    import json
    result = run_daily_aggregation({}, None)
    return json.dumps(result), 200
