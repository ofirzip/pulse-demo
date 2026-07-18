# VAST Observations — Verification Checklist

A side-catalog mapping each **intentionally planted vulnerability** in `pulse-demo`
(Code stage) and `pulse-infra` (Build/Deploy stage) to the **VAST Observation** it is
meant to trigger. The application/IaC code itself is deliberately left unannotated so it
reads as a realistic target — use this table to verify VAST's results after a scan.

> **Status legend**
> `active` = a detector ships today (should appear now) · `planned` = catalogued in
> `issue_rules.py` but no detector yet (input is present; will surface as detectors ship).
> Verified against `APT/src/vast/services/issue_rules.py`.

## How to run the scans

| # | What it checks | Command | Notes |
|---|---|---|---|
| S1 | SaaS / LLM egress (Code) | `vast code scan-external-apis --path /Users/ofirz/dev/pulse-demo --deep --ignore tests` | Local, no network. **Verified working.** |
| S2 | GCP permissions *used* (Code) | `vast code scan-repo --repo ofirzip/pulse-demo --cloud gcp` | Requires the repo pushed + registered (`vast settings code github add-repo`). Clones from GitHub. |
| S3 | GCP grants + IaC config (Build/Deploy) | `vast code scan-repo --repo ofirzip/pulse-infra --cloud gcp` | Requires pulse-infra pushed + registered. |
| R  | Observations / score | `vast code assess-risk` then `vast code get-risk --repo <owner/repo>` (or the web UI: `vast web`) | Renders the Observation list, aspects, and score after scanning. |

The **blast-drift** observations are cross-repo: S3 supplies the *granted* permissions,
S2 supplies the *used* permissions; the gap is the drift.

---

## Code stage — `pulse-demo`

| # | Planted vulnerability | Location | Expected Observation | Aspect · Kind | Status | Verify via |
|---|---|---|---|---|---|---|
| C1 | Anthropic LLM SDK integration | `enrichment.py:8` (import), `requirements.txt:6` | `sensitivity.saas_usage` | sensitivity · informational | **active** | S1 — expect `Anthropic [ai]`, `data shared: pii` |
| C2 | Full event payload (`user_id` + `properties`) sent in the LLM prompt | `enrichment.py:45,76` (`_PROMPT_TEMPLATE.format(event=…)`) | `sensitivity.llm_data_sharing`, `sensitivity.saas_pii_egress` | sensitivity · negative | planned | S1 deep probe shows data class `pii`; observation via R |
| C3 | Hardcoded API key | `enrichment.py:14` (`ANTHROPIC_API_KEY = "sk-ant-…"`) | `sensitivity.hardcoded_secret` | sensitivity · negative | planned (Secrets scanner coming-soon) | R |
| C4 | Secret transmitted to 3rd party (key rides the outbound call) | `enrichment.py:35,44,69` (`api_key=ANTHROPIC_API_KEY`) | `sensitivity.secrets_to_third_party` | sensitivity · negative | planned | R |
| C5 | Narrow GCP permission usage (baseline for drift) | `consumer.py`, `session_store.py`, `report_exporter.py` (pubsub/bq/firestore/gcs calls only) | *(input to* `blast.unused_permissions` *)* | blast | **active** | S2 — used-permission set should be small |

---

## Build / Deploy stage — `pulse-infra`

| # | Planted vulnerability | Location | Expected Observation | Aspect · Kind | Status | Verify via |
|---|---|---|---|---|---|---|
| B1 | `pulse-runner` SA granted `roles/owner` | `modules/iam/main.tf:45` | `blast.unused_permissions`, `blast.broad_service_grant` | blast · negative | **active** | S3 + drift vs S2 |
| B2 | " (admin-level grant) | `modules/iam/main.tf:45` | `blast.admin_grant` | blast · negative | planned | R |
| B3 | **Absence** of the positive least-privilege signal (owner grant breaks alignment) | `modules/iam/main.tf:45` | `blast.least_privilege_aligned` should **NOT** appear | blast · positive | **active** | R — confirm this positive is *absent* |
| B4 | Reports bucket world-readable | `modules/storage/main.tf:17-21` (`public_reports`, `allUsers` → `objectViewer`) | `sensitivity.public_data_store`, `exposure.public_workload` | sensitivity + exposure · negative | planned | S3 / R |
| B5 | Cloud Function publicly invokable | `environments/prod/main.tf:127-133` (`public_invoker`, `allUsers` → `invoker`) | `exposure.public_workload`, `exploitability.unauthenticated_endpoint` | exposure + exploitability · negative | planned | S3 / R |
| B6 | No CMEK on GCS/BigQuery | `modules/storage/main.tf:8-9`; `modules/bigquery/main.tf` (no `encryption` block) | `sensitivity.unencrypted_data` | sensitivity · negative | planned | S3 / R |

---

## Cross-repo attack chain

The individual observations compose into one narrative spanning VAST's aspects:

> **sensitivity** (user event data in Firestore/BigQuery) → egressed to an **external LLM**
> (C1/C2) → results land in a **public** bucket (B4, exposure) → served by a **publicly
> invokable** function (B5, exploitability) → running as an **over-privileged** service
> account (B1/B2, blast).

Expect **combo penalties** to stack where sets are worse together (e.g. a hardcoded secret
in a production workload).

## Expected result on today's engine

Running against the current engine, the **visibly firing** items are:

- **C1** — `sensitivity.saas_usage` (Anthropic, PII) — *verified via S1*.
- **C5 + B1** — the `blast` over-grant / drift family (`unused_permissions`,
  `broad_service_grant`) once both repos are scanned (S2 + S3).
- **B3** — the `blast.least_privilege_aligned` positive should be **absent**.

Everything marked `planned` above is seeded (its scan *input* is present) and should surface
automatically as those detectors ship — no code change needed at that point.

---
_Last updated: 2026-07-18. Line numbers reference commits `pulse-demo@f8e51e9`,
`pulse-infra@17a5729`._
