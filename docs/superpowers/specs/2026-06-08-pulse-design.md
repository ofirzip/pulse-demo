---
title: Pulse — Product Analytics Backend
date: 2026-06-08
status: approved
---

# Pulse Design Spec

## Overview

Pulse is a fictional self-hosted product analytics backend for a SaaS company (think Segment or Amplitude on GCP). It receives usage events, stores and aggregates them, and exports reports. The primary purpose of this repository is to exercise VAST's GCP code scanner with realistic, varied patterns of google-cloud-* SDK usage.

## Goals

- Provide realistic GCP SDK call patterns across Pub/Sub, BigQuery, Firestore, and Cloud Storage
- Exercise static analysis tooling with three distinct call patterns per module:
  1. **Direct/explicit** — client instantiation and method calls at the top level, fully visible to AST-based scanners
  2. **Abstracted** — GCP calls wrapped inside helper classes or functions that hide the call from a top-level static scan
  3. **GAPIC** — use of the low-level generated clients (e.g. `google.cloud.pubsub_v1`) for at least one module
- Not a production system — plausible logic, not hardened code

## Non-Goals

- No FastAPI, Flask, or other web frameworks
- No mocking or patching — real import-and-call patterns only
- No microservices or containerization
- No google-auth or google-api-core direct usage — higher-level service clients only

## Module Design

### `ingestor.py` — Event Ingestion via Pub/Sub

**Purpose:** Receives product usage events and publishes them to a Pub/Sub topic.

**Services:** `google-cloud-pubsub`

**Functions (3–6):**
- `get_publisher()` — instantiates and returns a `PublisherClient` (direct)
- `publish_event(event: dict)` — serializes event dict and calls `publisher.publish(topic_path, data)` (direct)
- `publish_batch(events: list)` — uses `BatchSettings` for batched publishing (direct, exercises batch config)
- `ensure_topic_exists(project_id, topic_id)` — calls `publisher.create_topic()` with error handling (direct)
- `EventPublisher` class — wraps the publisher client; `send()` method calls `publish` internally (abstracted)

**GAPIC note:** Uses `google.cloud.pubsub_v1.PublisherClient` directly for the GAPIC pattern.

---

### `consumer.py` — Event Consumption and BigQuery Storage

**Purpose:** Pulls events from Pub/Sub and writes raw events to a BigQuery table.

**Services:** `google-cloud-pubsub`, `google-cloud-bigquery`

**Functions (3–6):**
- `pull_events(subscription_path, max_messages)` — calls `subscriber.pull()` (direct)
- `acknowledge_messages(subscription_path, ack_ids)` — calls `subscriber.acknowledge()` (direct)
- `write_to_bigquery(rows: list)` — calls `bq_client.insert_rows_json(table_ref, rows)` (direct)
- `stream_event(event: dict)` — single-row streaming insert (direct)
- `EventConsumer` class — encapsulates pull + ack + BQ write in a `process_batch()` method (abstracted)

---

### `session_store.py` — User Session State in Firestore

**Purpose:** Reads and writes user session state to Firestore.

**Services:** `google-cloud-firestore`

**Functions (3–6):**
- `get_firestore_client()` — returns a `firestore.Client` (direct)
- `set_session(user_id, session_data)` — calls `db.collection().document().set()` (direct)
- `get_session(user_id)` — calls `db.collection().document().get()` (direct)
- `delete_session(user_id)` — calls `doc_ref.delete()` (direct)
- `list_active_sessions(since: datetime)` — calls `collection.where().stream()` (direct)
- `SessionRepository` class — wraps Firestore client; all CRUD methods delegate to `_client` (abstracted)

---

### `report_exporter.py` — BigQuery Queries and GCS Report Upload

**Purpose:** Queries BigQuery for aggregated event data and uploads CSV reports to Cloud Storage.

**Services:** `google-cloud-bigquery`, `google-cloud-storage`

**Functions (3–6):**
- `run_aggregation_query(sql)` — calls `bq_client.query(sql).result()` (direct)
- `results_to_csv(rows)` — converts query results to CSV string (utility)
- `upload_report(bucket_name, blob_name, content)` — calls `bucket.blob().upload_from_string()` (direct)
- `list_existing_reports(bucket_name, prefix)` — calls `storage_client.list_blobs()` (direct)
- `delete_old_report(bucket_name, blob_name)` — calls `bucket.blob().delete()` (direct)
- `ReportExporter` class — orchestrates query + CSV + upload; individual GCS calls are inside `_upload_to_gcs()` private method (abstracted)

---

### `scheduler.py` — Daily Aggregation Orchestrator

**Purpose:** Cloud Functions-style entry point (`run_daily_aggregation(event, context)`) that orchestrates the full pipeline.

**Services:** All of the above modules; no new GCP SDK calls directly.

**Functions:**
- `run_daily_aggregation(event, context)` — main entry point
- `aggregate_sessions()` — calls session_store module functions
- `export_daily_report(date_str)` — calls report_exporter module functions
- Demonstrates calling both the direct-call and abstracted-class interfaces from the other modules

---

## Supporting Files

### `requirements.txt`

```
google-cloud-pubsub>=2.18.0
google-cloud-bigquery>=3.11.0
google-cloud-firestore>=2.11.0
google-cloud-storage>=2.10.0
```

### `README.md`

Short description of Pulse as a fictional analytics backend, setup instructions, and module overview.

---

## Repository

- **GitHub:** `ofirzip/pulse-demo`
- **Local:** `/Users/ofirz/dev/pulse-demo`
- **Structure:** Flat — all Python modules at root, docs at `docs/`

## Scanner Exercise Summary

| Module | Direct calls | Abstracted calls | GAPIC |
|---|---|---|---|
| ingestor.py | `publisher.publish`, `create_topic`, `BatchSettings` | `EventPublisher.send()` | Yes (`pubsub_v1`) |
| consumer.py | `subscriber.pull`, `acknowledge`, `insert_rows_json` | `EventConsumer.process_batch()` | No |
| session_store.py | `collection().document().set/get`, `where().stream()` | `SessionRepository` class | No |
| report_exporter.py | `bq_client.query`, `upload_from_string`, `list_blobs` | `ReportExporter._upload_to_gcs()` | No |
| scheduler.py | None directly | Calls both direct functions and abstracted classes from other modules | No |
