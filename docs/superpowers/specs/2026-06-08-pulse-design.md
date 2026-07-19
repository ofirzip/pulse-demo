---
title: Pulse — Product Analytics Backend
date: 2026-06-08
status: approved
---

# Pulse Design Spec

## Overview

Pulse is a fictional self-hosted product analytics backend for a SaaS company (think Segment or Amplitude on GCP). It receives usage events, stores and aggregates them, and exports reports. The primary purpose of this repository is to exercise VAST's GCP code scanner with realistic, varied patterns of google-cloud-* SDK usage.

### Expanded purpose (2026-07): VAST Observations demo

Beyond exercising SDK-call detection, Pulse now also plants **realistic, unannotated vulnerabilities** so it doubles as a live demo of VAST's **Observation** catalog at the *Code* lifecycle stage (the *Build/Deploy* stage is covered by the companion `pulse-infra` Terraform repo). The scenario: Pulse ships an **AI event-enrichment** feature that sends user event data to an external LLM, whose results land in a (publicly-exposed, in `pulse-infra`) reports bucket served by an over-privileged runner. Code-stage observations seeded here:

- `sensitivity.saas_usage` (**active** today) — the Anthropic integration is detected by the SaaS/external-API scanner.
- `sensitivity.llm_data_sharing`, `sensitivity.saas_pii_egress`, `sensitivity.secrets_to_third_party` (roadmap) — event PII + the API key ride the outbound LLM call.
- `sensitivity.hardcoded_secret` (roadmap) — the Anthropic API key is embedded as a module constant.
- `blast.unused_permissions` / `blast.broad_service_grant` (**active**) — the code's actual GCP permission usage stays narrow, so `pulse-infra`'s broad grant to the runner shows as drift.

Code-stage observations that fire from the **code scan itself** (via the GCP risk classifier — see the companion `feat/gcp-risk-classification` APT change):

- `sensitivity.high_service` (**active**) — `enrichment.load_api_key` reads the Anthropic key from **Secret Manager** (`access_secret_version`), classified as secrets access.
- `blast.write_delete` (**active**) — `report_exporter.delete_old_report` deletes GCS report objects during retention cleanup.
- `blast.privilege_escalation` (**active**) — `scheduler.ensure_runner_permissions` writes the **project IAM policy** (`resourcemanager` `set_iam_policy`) to self-grant the runner a role, tying the code to `pulse-infra`'s over-privileged SA.
- `sensitivity.medium_service` (**active**) — the BigQuery aggregation query (`jobs.create`) reads raw event data, classified as data exfiltration.

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

### `enrichment.py` — LLM Event Enrichment (external SaaS)

**Purpose:** Categorizes product usage events by sending each event's full payload (`user_id` + `properties`) to an external LLM (Anthropic) and recording the returned category. This is the one intentional exception to the "no external SaaS" non-goal — it exists to seed the sensitivity/egress Observation family.

**Services:** `anthropic` (external LLM API — `api.anthropic.com`), no GCP SDK.

**Functions:**
- `get_llm_client()` — instantiates and returns an `anthropic.Anthropic` client (direct)
- `enrich_event(event: dict)` — builds a prompt from the full event and calls `client.messages.create()` (direct)
- `EventEnricher` class — the model call is hidden inside `enrich_batch()` (abstracted)

**Seeded Observations:** `sensitivity.saas_usage` (active), `sensitivity.llm_data_sharing` / `saas_pii_egress` / `secrets_to_third_party` / `hardcoded_secret` (roadmap). The `ANTHROPIC_API_KEY` constant is a deliberate hardcoded secret.

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
- `enrich_active_events()` — calls enrichment module (direct + abstracted LLM paths)
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
anthropic>=0.39.0
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
| enrichment.py | `anthropic.Anthropic().messages.create()` | `EventEnricher.enrich_batch()` | No (external LLM, not GCP) |
| report_exporter.py | `bq_client.query`, `upload_from_string`, `list_blobs` | `ReportExporter._upload_to_gcs()` | No |
| scheduler.py | None directly | Calls both direct functions and abstracted classes from other modules | No |
