"""consumer.py — pulls events from Pub/Sub and writes them to BigQuery."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from google.cloud import bigquery, pubsub_v1

PROJECT_ID = "pulse-analytics-prod"
SUBSCRIPTION_ID = "pulse-events-sub"
DATASET_ID = "pulse_raw"
TABLE_ID = "events"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Direct / explicit calls
# ---------------------------------------------------------------------------


def get_subscriber() -> pubsub_v1.SubscriberClient:
    return pubsub_v1.SubscriberClient()


def get_bq_client() -> bigquery.Client:
    return bigquery.Client(project=PROJECT_ID)


def pull_events(
    subscription_path: str,
    max_messages: int = 100,
) -> list[tuple[str, dict]]:
    """Pull messages from a subscription. Returns (ack_id, event_dict) pairs."""
    subscriber = pubsub_v1.SubscriberClient()
    response = subscriber.pull(
        request={"subscription": subscription_path, "max_messages": max_messages}
    )
    results = [
        (msg.ack_id, json.loads(msg.message.data.decode("utf-8")))
        for msg in response.received_messages
    ]
    logger.info("Pulled %d messages", len(results))
    return results


def acknowledge_messages(subscription_path: str, ack_ids: list[str]) -> None:
    """Acknowledge a list of Pub/Sub messages by ack_id."""
    subscriber = pubsub_v1.SubscriberClient()
    subscriber.acknowledge(
        request={"subscription": subscription_path, "ack_ids": ack_ids}
    )
    logger.info("Acknowledged %d messages", len(ack_ids))


def write_to_bigquery(
    rows: list[dict],
    dataset_id: str = DATASET_ID,
    table_id: str = TABLE_ID,
) -> None:
    """Streaming-insert rows into BigQuery via insert_rows_json."""
    client = bigquery.Client(project=PROJECT_ID)
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"
    errors = client.insert_rows_json(table_ref, rows)
    if errors:
        raise RuntimeError(f"BigQuery insert errors: {errors}")
    logger.info("Inserted %d rows into %s", len(rows), table_ref)


def stream_event(
    event: dict,
    dataset_id: str = DATASET_ID,
    table_id: str = TABLE_ID,
) -> None:
    """Insert a single event as a streaming row, stamped with ingestion time."""
    row = {**event, "ingested_at": datetime.now(timezone.utc).isoformat()}
    write_to_bigquery([row], dataset_id, table_id)


# ---------------------------------------------------------------------------
# Abstracted: pull + ack + BQ write hidden inside EventConsumer
# ---------------------------------------------------------------------------


class EventConsumer:
    """Encapsulates the full consume loop — direct SDK calls live inside."""

    def __init__(
        self,
        project_id: str = PROJECT_ID,
        subscription_id: str = SUBSCRIPTION_ID,
    ) -> None:
        self._subscriber = pubsub_v1.SubscriberClient()
        self._bq_client = bigquery.Client(project=project_id)
        self._subscription_path = self._subscriber.subscription_path(
            project_id, subscription_id
        )
        self._table_ref = f"{project_id}.{DATASET_ID}.{TABLE_ID}"

    def process_batch(self, max_messages: int = 100) -> int:
        """Pull -> write to BQ -> ack. Returns the count of events processed."""
        response = self._subscriber.pull(
            request={
                "subscription": self._subscription_path,
                "max_messages": max_messages,
            }
        )
        if not response.received_messages:
            return 0
        rows, ack_ids = [], []
        for msg in response.received_messages:
            event = json.loads(msg.message.data.decode("utf-8"))
            rows.append(
                {**event, "ingested_at": datetime.now(timezone.utc).isoformat()}
            )
            ack_ids.append(msg.ack_id)
        errors = self._bq_client.insert_rows_json(self._table_ref, rows)
        if errors:
            raise RuntimeError(f"BQ insert errors: {errors}")
        self._subscriber.acknowledge(
            request={
                "subscription": self._subscription_path,
                "ack_ids": ack_ids,
            }
        )
        return len(rows)
