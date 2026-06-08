"""ingestor.py — receives product usage events and publishes them to Pub/Sub."""

from __future__ import annotations

import json
import logging

from google.cloud import pubsub_v1
from google.pubsub_v1.services.publisher import PublisherClient as GapicPublisherClient
from google.cloud.pubsub_v1.types import Topic

PROJECT_ID = "pulse-analytics-prod"
TOPIC_ID = "pulse-events"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Direct / explicit calls — fully visible to a static scanner
# ---------------------------------------------------------------------------


def get_publisher() -> pubsub_v1.PublisherClient:
    """Instantiate and return a PublisherClient."""
    return pubsub_v1.PublisherClient()


def ensure_topic_exists(
    project_id: str = PROJECT_ID, topic_id: str = TOPIC_ID
) -> None:
    """Create the Pub/Sub topic if it does not already exist."""
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, topic_id)
    try:
        publisher.create_topic(request={"name": topic_path})
        logger.info("Created topic: %s", topic_path)
    except Exception as exc:  # noqa: BLE001
        if "AlreadyExists" in str(exc):
            logger.debug("Topic already exists: %s", topic_path)
        else:
            raise


def publish_event(
    event: dict,
    project_id: str = PROJECT_ID,
    topic_id: str = TOPIC_ID,
) -> str:
    """Serialize and publish a single event dict. Returns the Pub/Sub message ID."""
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, topic_id)
    data = json.dumps(event).encode("utf-8")
    future = publisher.publish(
        topic_path, data, event_type=event.get("event_type", "")
    )
    message_id = future.result()
    logger.info("Published %s → %s", event.get("event_type"), message_id)
    return message_id


def publish_batch(
    events: list[dict],
    project_id: str = PROJECT_ID,
    topic_id: str = TOPIC_ID,
) -> list[str]:
    """Publish many events with BatchSettings tuned for throughput."""
    batch_settings = pubsub_v1.types.BatchSettings(
        max_messages=500,
        max_bytes=10 * 1024 * 1024,
        max_latency=0.05,
    )
    publisher = pubsub_v1.PublisherClient(batch_settings=batch_settings)
    topic_path = publisher.topic_path(project_id, topic_id)
    futures = [
        publisher.publish(topic_path, json.dumps(e).encode("utf-8"))
        for e in events
    ]
    ids = [f.result() for f in futures]
    logger.info("Published batch of %d events", len(ids))
    return ids


# ---------------------------------------------------------------------------
# GAPIC: low-level generated service client accessed directly
# ---------------------------------------------------------------------------


def list_topics_gapic(project_id: str = PROJECT_ID) -> list[str]:
    """List all Pub/Sub topics using the GAPIC service client."""
    client = GapicPublisherClient()
    pager = client.list_topics(request={"project": f"projects/{project_id}"})
    return [topic.name for topic in pager]


def get_topic_gapic(
    project_id: str = PROJECT_ID, topic_id: str = TOPIC_ID
) -> Topic:
    """Fetch a Topic resource via the GAPIC client directly."""
    client = GapicPublisherClient()
    topic_path = f"projects/{project_id}/topics/{topic_id}"
    return client.get_topic(request={"topic": topic_path})


# ---------------------------------------------------------------------------
# Abstracted: GCP calls hidden inside EventPublisher — harder for a static scanner
# ---------------------------------------------------------------------------


class EventPublisher:
    """Wraps PublisherClient. Direct SDK calls are inside instance methods."""

    def __init__(
        self,
        project_id: str = PROJECT_ID,
        topic_id: str = TOPIC_ID,
    ) -> None:
        self._client = pubsub_v1.PublisherClient()
        self._topic_path = self._client.topic_path(project_id, topic_id)

    def send(self, event: dict) -> str:
        data = json.dumps(event).encode("utf-8")
        future = self._client.publish(self._topic_path, data)
        return future.result()

    def send_many(self, events: list[dict]) -> list[str]:
        return [self.send(e) for e in events]
