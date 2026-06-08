"""report_exporter.py — queries BigQuery and uploads CSV reports to GCS."""

from __future__ import annotations

import csv
import io
import logging

from google.cloud import bigquery, storage

PROJECT_ID = "pulse-analytics-prod"
REPORTS_BUCKET = "pulse-analytics-reports"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Direct / explicit calls
# ---------------------------------------------------------------------------


def run_aggregation_query(sql: str) -> list[dict]:
    """Execute a BigQuery SQL query and return rows as a list of dicts."""
    client = bigquery.Client(project=PROJECT_ID)
    job = client.query(sql)
    return [dict(row) for row in job.result()]


def results_to_csv(rows: list[dict]) -> str:
    """Convert a list of row dicts to a CSV string."""
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def upload_report(bucket_name: str, blob_name: str, content: str) -> str:
    """Upload a CSV string to GCS. Returns the gs:// URI."""
    client = storage.Client(project=PROJECT_ID)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(content, content_type="text/csv")
    uri = f"gs://{bucket_name}/{blob_name}"
    logger.info("Uploaded report → %s", uri)
    return uri


def list_existing_reports(
    bucket_name: str = REPORTS_BUCKET, prefix: str = "daily/"
) -> list[str]:
    """Return blob names in the bucket under the given prefix."""
    client = storage.Client(project=PROJECT_ID)
    blobs = client.list_blobs(bucket_name, prefix=prefix)
    names = [b.name for b in blobs]
    logger.info(
        "Found %d reports under gs://%s/%s", len(names), bucket_name, prefix
    )
    return names


def delete_old_report(bucket_name: str, blob_name: str) -> None:
    """Delete a single report blob from GCS."""
    client = storage.Client(project=PROJECT_ID)
    client.bucket(bucket_name).blob(blob_name).delete()
    logger.info("Deleted gs://%s/%s", bucket_name, blob_name)


# ---------------------------------------------------------------------------
# Abstracted: GCS calls hidden inside ReportExporter._upload_to_gcs
# ---------------------------------------------------------------------------


class ReportExporter:
    """Orchestrates BigQuery query → CSV → GCS upload."""

    def __init__(
        self,
        project_id: str = PROJECT_ID,
        bucket_name: str = REPORTS_BUCKET,
    ) -> None:
        self._bq = bigquery.Client(project=project_id)
        self._gcs = storage.Client(project=project_id)
        self._bucket_name = bucket_name

    def export(self, sql: str, blob_name: str) -> str:
        """Run query, convert to CSV, upload. Returns gs:// URI."""
        rows = [dict(row) for row in self._bq.query(sql).result()]
        csv_content = results_to_csv(rows)
        return self._upload_to_gcs(blob_name, csv_content)

    def _upload_to_gcs(self, blob_name: str, content: str) -> str:
        blob = self._gcs.bucket(self._bucket_name).blob(blob_name)
        blob.upload_from_string(content, content_type="text/csv")
        return f"gs://{self._bucket_name}/{blob_name}"
