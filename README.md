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
