# Pulse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the `ofirzip/pulse-demo` GitHub repository with five Python modules that exercise GCP SDK call patterns (direct, abstracted, GAPIC) for VAST's static code scanner.

**Architecture:** Flat Python package — five modules at repo root, each importing real `google-cloud-*` clients with no mocking. Each module contains direct SDK calls visible to an AST scanner, a wrapper class that hides the calls, and `ingestor.py` adds GAPIC service-client examples.

**Tech Stack:** Python 3.11+, google-cloud-pubsub, google-cloud-bigquery, google-cloud-bigquery-storage, google-cloud-firestore, google-cloud-storage, pytest

---

## File Structure

```
pulse-demo/
├── ingestor.py          # Pub/Sub publisher (direct + GAPIC + EventPublisher class)
├── consumer.py          # Pub/Sub subscriber + BigQuery writer (direct + EventConsumer class)
├── session_store.py     # Firestore session CRUD (direct + SessionRepository class)
├── report_exporter.py   # BigQuery query + GCS upload (direct + ReportExporter class)
├── scheduler.py         # Cloud Functions entry point orchestrating the pipeline
├── requirements.txt
├── README.md
├── tests/
│   ├── test_ingestor.py
│   ├── test_consumer.py
│   ├── test_session_store.py
│   ├── test_report_exporter.py
│   └── test_scheduler.py
└── docs/
    └── superpowers/
        ├── specs/2026-06-08-pulse-design.md
        └── plans/2026-06-08-pulse-implementation.md
```

---

### Task 1: Initialize repository and push to GitHub

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Initialize git repo locally**

```bash
cd /Users/ofirz/dev/pulse-demo
git init
git checkout -b main
```

- [ ] **Step 2: Create .gitignore**

```
__pycache__/
*.pyc
*.pyo
.env
.venv/
venv/
*.egg-info/
dist/
build/
.pytest_cache/
.DS_Store
```

- [ ] **Step 3: Create GitHub repo**

```bash
gh repo create ofirzip/pulse-demo --public \
  --description "Pulse — fictional product analytics backend (GCP scanner demo)"
git remote add origin https://github.com/ofirzip/pulse-demo.git
```

Expected: GitHub confirms repo created at `https://github.com/ofirzip/pulse-demo`

- [ ] **Step 4: Stage and commit .gitignore**

```bash
git add .gitignore
git commit -m "chore: initialize repository"
```

---

### Task 2: requirements.txt and README.md

**Files:**
- Create: `requirements.txt`
- Create: `README.md`

- [ ] **Step 1: Write requirements.txt**

```
google-cloud-pubsub>=2.18.0
google-cloud-bigquery>=3.11.0
google-cloud-bigquery-storage>=2.22.0
google-cloud-firestore>=2.11.0
google-cloud-storage>=2.10.0
pytest>=7.4.0
```

- [ ] **Step 2: Write README.md**

```markdown
# Pulse

Pulse is a fictional self-hosted product analytics backend for a SaaS company — think Segment or Amplitude, running on GCP.

It receives product usage events, stores and aggregates them, and exports daily reports. This repository exists as a realistic GCP SDK usage demo; it is not production-ready.

## Architecture

```
Events → ingestor.py → Pub/Sub → consumer.py → BigQuery
                                                     ↓
                        session_store.py ← Firestore  ↓
                                                     ↓
                        report_exporter.py → GCS ← BigQuery
                                ↑
                          scheduler.py (Cloud Functions entry point)
```

## Modules

| Module | GCP Services | Purpose |
|---|---|---|
| `ingestor.py` | Pub/Sub | Publish usage events to a topic |
| `consumer.py` | Pub/Sub, BigQuery | Pull events and write to raw table |
| `session_store.py` | Firestore | Read/write user session state |
| `report_exporter.py` | BigQuery, Cloud Storage | Query aggregates and upload CSV reports |
| `scheduler.py` | — | Cloud Functions entry point, orchestrates the pipeline |

## Setup

```bash
pip install -r requirements.txt
```

Set `GOOGLE_APPLICATION_CREDENTIALS` to a service account key with Pub/Sub, BigQuery, Firestore, and Storage permissions.

## Running tests

```bash
pytest tests/ -v
```

## GCP resources expected

- Project: `pulse-analytics-prod`
- Pub/Sub topic: `pulse-events`, subscription: `pulse-events-sub`
- BigQuery dataset: `pulse_raw`, table: `events`
- Firestore collection: `user_sessions`
- GCS bucket: `pulse-analytics-reports`
```

- [ ] **Step 3: Commit**

```bash
git add requirements.txt README.md
git commit -m "docs: add requirements and README"
```

---

### Task 3: ingestor.py — Pub/Sub publisher (direct + GAPIC + abstracted)

**Files:**
- Create: `tests/test_ingestor.py`
- Create: `ingestor.py`

- [ ] **Step 1: Create tests directory and write the failing test**

```bash
mkdir -p tests
```

Write `tests/test_ingestor.py`:

```python
from unittest.mock import MagicMock, patch
import pytest
from ingestor import (
    get_publisher,
    ensure_topic_exists,
    publish_event,
    publish_batch,
    list_topics_gapic,
    get_topic_gapic,
    EventPublisher,
)


@patch("ingestor.pubsub_v1.PublisherClient")
def test_get_publisher_returns_client(MockClient):
    result = get_publisher()
    MockClient.assert_called_once()
    assert result is MockClient.return_value


@patch("ingestor.pubsub_v1.PublisherClient")
def test_ensure_topic_exists_creates_topic(MockClient):
    mock_pub = MockClient.return_value
    mock_pub.topic_path.return_value = "projects/p/topics/t"
    ensure_topic_exists("p", "t")
    mock_pub.create_topic.assert_called_once_with(
        request={"name": "projects/p/topics/t"}
    )


@patch("ingestor.pubsub_v1.PublisherClient")
def test_ensure_topic_exists_ignores_already_exists(MockClient):
    mock_pub = MockClient.return_value
    mock_pub.topic_path.return_value = "projects/p/topics/t"
    mock_pub.create_topic.side_effect = Exception("AlreadyExists")
    ensure_topic_exists("p", "t")  # must not raise


@patch("ingestor.pubsub_v1.PublisherClient")
def test_publish_event_returns_message_id(MockClient):
    mock_pub = MockClient.return_value
    mock_pub.topic_path.return_value = "projects/p/topics/pulse-events"
    mock_future = MagicMock()
    mock_future.result.return_value = "msg-001"
    mock_pub.publish.return_value = mock_future

    result = publish_event({"event_type": "page_view", "user_id": "u1"})

    assert result == "msg-001"
    mock_pub.publish.assert_called_once()


@patch("ingestor.pubsub_v1.PublisherClient")
def test_publish_batch_returns_all_ids(MockClient):
    mock_pub = MockClient.return_value
    mock_pub.topic_path.return_value = "projects/p/topics/pulse-events"
    ids = ["id-1", "id-2", "id-3"]
    futures = [MagicMock() for _ in ids]
    for f, i in zip(futures, ids):
        f.result.return_value = i
    mock_pub.publish.side_effect = futures

    result = publish_batch([{"event_type": "click"} for _ in ids])

    assert result == ids


@patch("ingestor.GapicPublisherClient")
def test_list_topics_gapic(MockGapic):
    topic_a = MagicMock()
    topic_a.name = "projects/p/topics/a"
    topic_b = MagicMock()
    topic_b.name = "projects/p/topics/b"
    MockGapic.return_value.list_topics.return_value = [topic_a, topic_b]

    result = list_topics_gapic("p")

    assert result == ["projects/p/topics/a", "projects/p/topics/b"]


@patch("ingestor.GapicPublisherClient")
def test_get_topic_gapic(MockGapic):
    mock_topic = MagicMock()
    mock_topic.name = "projects/p/topics/pulse-events"
    MockGapic.return_value.get_topic.return_value = mock_topic

    result = get_topic_gapic("p", "pulse-events")

    assert result.name == "projects/p/topics/pulse-events"
    MockGapic.return_value.get_topic.assert_called_once_with(
        request={"topic": "projects/p/topics/pulse-events"}
    )


@patch("ingestor.pubsub_v1.PublisherClient")
def test_event_publisher_send(MockClient):
    mock_pub = MockClient.return_value
    mock_pub.topic_path.return_value = "projects/p/topics/pulse-events"
    mock_future = MagicMock()
    mock_future.result.return_value = "msg-xyz"
    mock_pub.publish.return_value = mock_future

    publisher = EventPublisher()
    result = publisher.send({"event_type": "signup"})

    assert result == "msg-xyz"
    mock_pub.publish.assert_called_once()


@patch("ingestor.pubsub_v1.PublisherClient")
def test_event_publisher_send_many(MockClient):
    mock_pub = MockClient.return_value
    mock_pub.topic_path.return_value = "projects/p/topics/pulse-events"
    counter = [0]

    def make_future(*args, **kwargs):
        counter[0] += 1
        f = MagicMock()
        f.result.return_value = f"msg-{counter[0]}"
        return f

    mock_pub.publish.side_effect = make_future

    publisher = EventPublisher()
    results = publisher.send_many([{"event_type": "click"}, {"event_type": "view"}])

    assert len(results) == 2
    assert results[0] == "msg-1"
    assert results[1] == "msg-2"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/ofirz/dev/pulse-demo
pytest tests/test_ingestor.py -v
```

Expected: `ImportError: No module named 'ingestor'`

- [ ] **Step 3: Write ingestor.py**

```python
"""ingestor.py — receives product usage events and publishes them to Pub/Sub."""

from __future__ import annotations

import json
import logging

from google.cloud import pubsub_v1
from google.cloud.pubsub_v1.services.publisher import PublisherClient as GapicPublisherClient
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
```

- [ ] **Step 4: Install dependencies and run tests**

```bash
pip install -r requirements.txt
pytest tests/test_ingestor.py -v
```

Expected: all 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add ingestor.py tests/test_ingestor.py
git commit -m "feat: add ingestor module with Pub/Sub publisher, GAPIC, and EventPublisher"
```

---

### Task 4: consumer.py — Pub/Sub subscriber + BigQuery writer

**Files:**
- Create: `tests/test_consumer.py`
- Create: `consumer.py`

- [ ] **Step 1: Write tests/test_consumer.py**

```python
import json
from unittest.mock import MagicMock, patch

import pytest

from consumer import (
    EventConsumer,
    acknowledge_messages,
    get_bq_client,
    get_subscriber,
    pull_events,
    stream_event,
    write_to_bigquery,
)


def _make_received_message(ack_id: str, event: dict):
    msg = MagicMock()
    msg.ack_id = ack_id
    msg.message.data = json.dumps(event).encode("utf-8")
    return msg


@patch("consumer.pubsub_v1.SubscriberClient")
def test_get_subscriber(MockSub):
    result = get_subscriber()
    MockSub.assert_called_once()
    assert result is MockSub.return_value


@patch("consumer.bigquery.Client")
def test_get_bq_client(MockBQ):
    result = get_bq_client()
    MockBQ.assert_called_once()
    assert result is MockBQ.return_value


@patch("consumer.pubsub_v1.SubscriberClient")
def test_pull_events_returns_ack_event_pairs(MockSub):
    mock_sub = MockSub.return_value
    mock_sub.pull.return_value.received_messages = [
        _make_received_message("ack-1", {"event_type": "click"}),
        _make_received_message("ack-2", {"event_type": "view"}),
    ]

    results = pull_events("projects/p/subscriptions/s")

    assert len(results) == 2
    assert results[0] == ("ack-1", {"event_type": "click"})
    assert results[1] == ("ack-2", {"event_type": "view"})


@patch("consumer.pubsub_v1.SubscriberClient")
def test_pull_events_returns_empty_on_no_messages(MockSub):
    MockSub.return_value.pull.return_value.received_messages = []
    assert pull_events("projects/p/subscriptions/s") == []


@patch("consumer.pubsub_v1.SubscriberClient")
def test_acknowledge_messages(MockSub):
    mock_sub = MockSub.return_value
    acknowledge_messages("projects/p/subscriptions/s", ["ack-1", "ack-2"])
    mock_sub.acknowledge.assert_called_once_with(
        request={
            "subscription": "projects/p/subscriptions/s",
            "ack_ids": ["ack-1", "ack-2"],
        }
    )


@patch("consumer.bigquery.Client")
def test_write_to_bigquery_no_errors(MockBQ):
    MockBQ.return_value.insert_rows_json.return_value = []
    write_to_bigquery([{"event_type": "click"}])
    MockBQ.return_value.insert_rows_json.assert_called_once()


@patch("consumer.bigquery.Client")
def test_write_to_bigquery_raises_on_errors(MockBQ):
    MockBQ.return_value.insert_rows_json.return_value = [{"error": "bad row"}]
    with pytest.raises(RuntimeError, match="BigQuery insert errors"):
        write_to_bigquery([{"event_type": "click"}])


@patch("consumer.bigquery.Client")
@patch("consumer.pubsub_v1.SubscriberClient")
def test_event_consumer_process_batch_returns_count(MockSub, MockBQ):
    mock_sub = MockSub.return_value
    mock_sub.subscription_path.return_value = "projects/p/subscriptions/s"
    mock_sub.pull.return_value.received_messages = [
        _make_received_message("ack-1", {"event_type": "purchase"}),
        _make_received_message("ack-2", {"event_type": "click"}),
    ]
    MockBQ.return_value.insert_rows_json.return_value = []

    consumer = EventConsumer()
    count = consumer.process_batch()

    assert count == 2
    mock_sub.acknowledge.assert_called_once()


@patch("consumer.bigquery.Client")
@patch("consumer.pubsub_v1.SubscriberClient")
def test_event_consumer_process_batch_empty_returns_zero(MockSub, MockBQ):
    mock_sub = MockSub.return_value
    mock_sub.subscription_path.return_value = "projects/p/subscriptions/s"
    mock_sub.pull.return_value.received_messages = []

    consumer = EventConsumer()
    count = consumer.process_batch()

    assert count == 0
    mock_sub.acknowledge.assert_not_called()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_consumer.py -v
```

Expected: `ImportError: No module named 'consumer'`

- [ ] **Step 3: Write consumer.py**

```python
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
        """Pull → write to BQ → ack. Returns the count of events processed."""
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_consumer.py -v
```

Expected: all 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add consumer.py tests/test_consumer.py
git commit -m "feat: add consumer module with Pub/Sub pull and BigQuery streaming insert"
```

---

### Task 5: session_store.py — Firestore session CRUD

**Files:**
- Create: `tests/test_session_store.py`
- Create: `session_store.py`

- [ ] **Step 1: Write tests/test_session_store.py**

```python
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from session_store import (
    SessionRepository,
    delete_session,
    get_firestore_client,
    get_session,
    list_active_sessions,
    set_session,
)


@patch("session_store.firestore.Client")
def test_get_firestore_client(MockClient):
    result = get_firestore_client()
    MockClient.assert_called_once()
    assert result is MockClient.return_value


@patch("session_store.firestore.Client")
def test_set_session_calls_document_set(MockClient):
    db = MockClient.return_value
    set_session("user-1", {"plan": "pro"})
    db.collection.assert_called_with("user_sessions")
    db.collection().document.assert_called_with("user-1")
    db.collection().document().set.assert_called_once()


@patch("session_store.firestore.Client")
def test_get_session_returns_dict_when_found(MockClient):
    db = MockClient.return_value
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"plan": "pro"}
    db.collection().document().get.return_value = mock_doc

    result = get_session("user-1")

    assert result == {"plan": "pro"}


@patch("session_store.firestore.Client")
def test_get_session_returns_none_when_missing(MockClient):
    db = MockClient.return_value
    mock_doc = MagicMock()
    mock_doc.exists = False
    db.collection().document().get.return_value = mock_doc

    assert get_session("ghost") is None


@patch("session_store.firestore.Client")
def test_delete_session_calls_delete(MockClient):
    db = MockClient.return_value
    delete_session("user-1")
    db.collection().document().delete.assert_called_once()


@patch("session_store.firestore.Client")
def test_list_active_sessions_returns_enriched_dicts(MockClient):
    db = MockClient.return_value
    doc_a = MagicMock()
    doc_a.id = "user-1"
    doc_a.to_dict.return_value = {"plan": "free"}
    doc_b = MagicMock()
    doc_b.id = "user-2"
    doc_b.to_dict.return_value = {"plan": "pro"}
    db.collection().where().stream.return_value = [doc_a, doc_b]

    since = datetime(2026, 6, 1, tzinfo=timezone.utc)
    results = list_active_sessions(since)

    assert results == [
        {"plan": "free", "user_id": "user-1"},
        {"plan": "pro", "user_id": "user-2"},
    ]


@patch("session_store.firestore.Client")
def test_session_repository_save(MockClient):
    db = MockClient.return_value
    repo = SessionRepository()
    repo.save("user-3", {"plan": "enterprise"})
    db.collection().document().set.assert_called_once()


@patch("session_store.firestore.Client")
def test_session_repository_load_found(MockClient):
    db = MockClient.return_value
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"plan": "enterprise"}
    db.collection().document().get.return_value = mock_doc

    repo = SessionRepository()
    result = repo.load("user-3")

    assert result == {"plan": "enterprise"}


@patch("session_store.firestore.Client")
def test_session_repository_remove(MockClient):
    db = MockClient.return_value
    repo = SessionRepository()
    repo.remove("user-1")
    db.collection().document().delete.assert_called_once()


@patch("session_store.firestore.Client")
def test_session_repository_active_since(MockClient):
    db = MockClient.return_value
    doc = MagicMock()
    doc.id = "user-5"
    doc.to_dict.return_value = {"plan": "free"}
    db.collection().where().stream.return_value = [doc]

    repo = SessionRepository()
    results = repo.active_since(datetime(2026, 6, 1, tzinfo=timezone.utc))

    assert results == [{"plan": "free", "user_id": "user-5"}]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_session_store.py -v
```

Expected: `ImportError: No module named 'session_store'`

- [ ] **Step 3: Write session_store.py**

```python
"""session_store.py — reads and writes user session state to Firestore."""

from __future__ import annotations

import logging
from datetime import datetime

from google.cloud import firestore

PROJECT_ID = "pulse-analytics-prod"
COLLECTION_NAME = "user_sessions"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Direct / explicit calls
# ---------------------------------------------------------------------------


def get_firestore_client() -> firestore.Client:
    return firestore.Client(project=PROJECT_ID)


def set_session(user_id: str, session_data: dict) -> None:
    """Write (or overwrite) a user session document."""
    db = firestore.Client(project=PROJECT_ID)
    db.collection(COLLECTION_NAME).document(user_id).set(
        {**session_data, "updated_at": firestore.SERVER_TIMESTAMP}
    )
    logger.info("Set session for user %s", user_id)


def get_session(user_id: str) -> dict | None:
    """Return session dict for the user, or None if absent."""
    db = firestore.Client(project=PROJECT_ID)
    doc = db.collection(COLLECTION_NAME).document(user_id).get()
    return doc.to_dict() if doc.exists else None


def delete_session(user_id: str) -> None:
    """Delete a user's session document."""
    db = firestore.Client(project=PROJECT_ID)
    db.collection(COLLECTION_NAME).document(user_id).delete()
    logger.info("Deleted session for user %s", user_id)


def list_active_sessions(since: datetime) -> list[dict]:
    """Return all sessions updated at or after `since`."""
    db = firestore.Client(project=PROJECT_ID)
    docs = (
        db.collection(COLLECTION_NAME)
        .where("updated_at", ">=", since)
        .stream()
    )
    sessions = [doc.to_dict() | {"user_id": doc.id} for doc in docs]
    logger.info("Found %d active sessions since %s", len(sessions), since)
    return sessions


# ---------------------------------------------------------------------------
# Abstracted: all Firestore calls hidden inside SessionRepository
# ---------------------------------------------------------------------------


class SessionRepository:
    """Thin repository over Firestore — direct calls are inside instance methods."""

    def __init__(self, project_id: str = PROJECT_ID) -> None:
        self._client = firestore.Client(project=project_id)
        self._col = self._client.collection(COLLECTION_NAME)

    def save(self, user_id: str, data: dict) -> None:
        self._col.document(user_id).set(
            {**data, "updated_at": firestore.SERVER_TIMESTAMP}
        )

    def load(self, user_id: str) -> dict | None:
        doc = self._col.document(user_id).get()
        return doc.to_dict() if doc.exists else None

    def remove(self, user_id: str) -> None:
        self._col.document(user_id).delete()

    def active_since(self, since: datetime) -> list[dict]:
        docs = self._col.where("updated_at", ">=", since).stream()
        return [d.to_dict() | {"user_id": d.id} for d in docs]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_session_store.py -v
```

Expected: all 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add session_store.py tests/test_session_store.py
git commit -m "feat: add session_store module with Firestore CRUD and SessionRepository"
```

---

### Task 6: report_exporter.py — BigQuery query + GCS upload

**Files:**
- Create: `tests/test_report_exporter.py`
- Create: `report_exporter.py`

- [ ] **Step 1: Write tests/test_report_exporter.py**

```python
from unittest.mock import MagicMock, patch

import pytest

from report_exporter import (
    ReportExporter,
    delete_old_report,
    list_existing_reports,
    results_to_csv,
    run_aggregation_query,
    upload_report,
)


@patch("report_exporter.bigquery.Client")
def test_run_aggregation_query_returns_list_of_dicts(MockBQ):
    fake_row = {"event_type": "click", "count": 5}
    MockBQ.return_value.query.return_value.result.return_value = [fake_row]

    result = run_aggregation_query("SELECT 1")

    assert result == [{"event_type": "click", "count": 5}]
    MockBQ.return_value.query.assert_called_once_with("SELECT 1")


def test_results_to_csv_empty():
    assert results_to_csv([]) == ""


def test_results_to_csv_produces_header_and_rows():
    rows = [
        {"event_type": "click", "count": 3},
        {"event_type": "view", "count": 10},
    ]
    csv_str = results_to_csv(rows)
    assert "event_type" in csv_str
    assert "count" in csv_str
    assert "click" in csv_str
    assert "view" in csv_str
    assert csv_str.count("\n") == 3  # header + 2 rows + trailing newline


@patch("report_exporter.storage.Client")
def test_upload_report_returns_gs_uri(MockStorage):
    mock_blob = MagicMock()
    MockStorage.return_value.bucket.return_value.blob.return_value = mock_blob

    uri = upload_report("my-bucket", "reports/r.csv", "col1,col2\n1,2\n")

    assert uri == "gs://my-bucket/reports/r.csv"
    mock_blob.upload_from_string.assert_called_once_with(
        "col1,col2\n1,2\n", content_type="text/csv"
    )


@patch("report_exporter.storage.Client")
def test_list_existing_reports(MockStorage):
    blob_a = MagicMock()
    blob_a.name = "daily/2026-06-07.csv"
    MockStorage.return_value.list_blobs.return_value = [blob_a]

    names = list_existing_reports("my-bucket", "daily/")

    assert names == ["daily/2026-06-07.csv"]
    MockStorage.return_value.list_blobs.assert_called_once_with(
        "my-bucket", prefix="daily/"
    )


@patch("report_exporter.storage.Client")
def test_delete_old_report(MockStorage):
    mock_blob = MagicMock()
    MockStorage.return_value.bucket.return_value.blob.return_value = mock_blob

    delete_old_report("my-bucket", "daily/old.csv")

    mock_blob.delete.assert_called_once()


@patch("report_exporter.storage.Client")
@patch("report_exporter.bigquery.Client")
def test_report_exporter_export_returns_uri(MockBQ, MockStorage):
    fake_row = {"event_type": "click", "count": 5}
    MockBQ.return_value.query.return_value.result.return_value = [fake_row]
    mock_blob = MagicMock()
    MockStorage.return_value.bucket.return_value.blob.return_value = mock_blob

    exporter = ReportExporter(bucket_name="test-bucket")
    uri = exporter.export("SELECT 1", "daily/test.csv")

    assert uri == "gs://test-bucket/daily/test.csv"
    mock_blob.upload_from_string.assert_called_once()


@patch("report_exporter.storage.Client")
@patch("report_exporter.bigquery.Client")
def test_report_exporter_upload_to_gcs_is_private(MockBQ, MockStorage):
    """_upload_to_gcs is the abstracted path — verify it's not top-level."""
    exporter = ReportExporter()
    assert callable(exporter._upload_to_gcs)
    assert not hasattr(report_exporter, "_upload_to_gcs")  # not a module-level symbol


import report_exporter  # noqa: E402 (needed for the attribute check above)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_report_exporter.py -v
```

Expected: `ImportError: No module named 'report_exporter'`

- [ ] **Step 3: Write report_exporter.py**

```python
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_report_exporter.py -v
```

Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add report_exporter.py tests/test_report_exporter.py
git commit -m "feat: add report_exporter module with BigQuery query and GCS upload"
```

---

### Task 7: scheduler.py — Cloud Functions orchestrator

**Files:**
- Create: `tests/test_scheduler.py`
- Create: `scheduler.py`

- [ ] **Step 1: Write tests/test_scheduler.py**

```python
from unittest.mock import MagicMock, patch

import pytest

from scheduler import (
    aggregate_sessions,
    drain_event_queue,
    export_daily_report,
    run_daily_aggregation,
)


@patch("scheduler.EventConsumer")
def test_drain_event_queue_stops_on_empty_batch(MockConsumer):
    mock_consumer = MockConsumer.return_value
    mock_consumer.process_batch.side_effect = [5, 3, 0]

    total = drain_event_queue(max_batches=10)

    assert total == 8
    assert mock_consumer.process_batch.call_count == 3


@patch("scheduler.EventConsumer")
def test_drain_event_queue_respects_max_batches(MockConsumer):
    mock_consumer = MockConsumer.return_value
    mock_consumer.process_batch.return_value = 10

    total = drain_event_queue(max_batches=3)

    assert total == 30
    assert mock_consumer.process_batch.call_count == 3


@patch("scheduler.SessionRepository")
@patch("scheduler.list_active_sessions")
def test_aggregate_sessions_re_saves_active_users(mock_list, MockRepo):
    mock_list.return_value = [
        {"user_id": "u1", "plan": "pro"},
        {"user_id": "u2", "plan": "free"},
    ]

    count = aggregate_sessions()

    assert count == 2
    assert MockRepo.return_value.save.call_count == 2


@patch("scheduler.SessionRepository")
@patch("scheduler.list_active_sessions")
def test_aggregate_sessions_returns_zero_when_no_sessions(mock_list, MockRepo):
    mock_list.return_value = []
    assert aggregate_sessions() == 0


@patch("scheduler.ReportExporter")
@patch("scheduler.results_to_csv")
@patch("scheduler.run_aggregation_query")
def test_export_daily_report_uses_given_date(mock_query, mock_csv, MockExporter):
    mock_query.return_value = [{"event_type": "click", "count": 5}]
    mock_csv.return_value = "event_type,count\nclick,5\n"
    MockExporter.return_value.export.return_value = "gs://bucket/daily/pulse-report-2026-06-07.csv"

    uri = export_daily_report("2026-06-07")

    assert uri == "gs://bucket/daily/pulse-report-2026-06-07.csv"
    mock_query.assert_called_once()
    sql_arg = mock_query.call_args[0][0]
    assert "2026-06-07" in sql_arg


@patch("scheduler.export_daily_report")
@patch("scheduler.aggregate_sessions")
@patch("scheduler.drain_event_queue")
def test_run_daily_aggregation_returns_summary(mock_drain, mock_sessions, mock_export):
    mock_drain.return_value = 42
    mock_sessions.return_value = 7
    mock_export.return_value = "gs://bucket/daily/report.csv"

    result = run_daily_aggregation({}, None)

    assert result["status"] == "ok"
    assert result["events_drained"] == 42
    assert result["sessions_synced"] == 7
    assert result["report_uri"] == "gs://bucket/daily/report.csv"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_scheduler.py -v
```

Expected: `ImportError: No module named 'scheduler'`

- [ ] **Step 3: Write scheduler.py**

```python
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
```

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS (approx 34 tests across 5 files)

- [ ] **Step 5: Commit**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "feat: add scheduler module as Cloud Functions entry point"
```

---

### Task 8: Push everything to GitHub

- [ ] **Step 1: Verify full test suite passes cleanly**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests PASS, 0 failures, 0 errors

- [ ] **Step 2: Confirm all files are committed**

```bash
git status
```

Expected: `nothing to commit, working tree clean`

- [ ] **Step 3: Push to GitHub**

```bash
git push -u origin main
```

Expected: branch pushed, GitHub URL printed

- [ ] **Step 4: Push the docs (spec + plan)**

The docs were created before the git repo was initialized. Stage and push them now:

```bash
git add docs/
git commit -m "docs: add design spec and implementation plan"
git push
```

- [ ] **Step 5: Verify on GitHub**

```bash
gh repo view ofirzip/pulse-demo --web
```

Expected: GitHub shows 5 Python modules + requirements.txt + README.md + tests/ + docs/

---

## Self-Review

**Spec coverage:**
- ✅ `ingestor.py` — `get_publisher`, `ensure_topic_exists`, `publish_event`, `publish_batch`, GAPIC `list_topics_gapic` + `get_topic_gapic`, `EventPublisher` class
- ✅ `consumer.py` — `get_subscriber`, `get_bq_client`, `pull_events`, `acknowledge_messages`, `write_to_bigquery`, `stream_event`, `EventConsumer` class
- ✅ `session_store.py` — `get_firestore_client`, `set_session`, `get_session`, `delete_session`, `list_active_sessions`, `SessionRepository` class
- ✅ `report_exporter.py` — `run_aggregation_query`, `results_to_csv`, `upload_report`, `list_existing_reports`, `delete_old_report`, `ReportExporter` class with `_upload_to_gcs`
- ✅ `scheduler.py` — `run_daily_aggregation`, `drain_event_queue`, `aggregate_sessions`, `export_daily_report`; exercises both direct and abstracted interfaces from other modules
- ✅ `requirements.txt` — all five `google-cloud-*` packages + bigquery-storage for GAPIC + pytest
- ✅ `README.md`
- ✅ GitHub repo `ofirzip/pulse-demo`

**No placeholders, no TODOs.**

**Type consistency:** All function signatures used consistently across tasks. `EventConsumer`, `SessionRepository`, `ReportExporter`, `EventPublisher` defined in Task 3–6 and imported correctly in Task 7's `scheduler.py`.
