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

## Expected result on today's engine (pre-scan hypothesis)

Before scanning we expected the **visibly firing** items to be `saas_usage` (C1), the `blast`
over-grant/drift family (C5 + B1), and the absence of `least_privilege_aligned` (B3). The
actual Track 1 results below **corrected two of these** — see the ⚠️ notes.

---

## Track 1 — Observed results (2026-07-18, static scan, no deploy)

**Scans run** (both repos merged to `main`, cloned by VAST):
- `vast code scan-repo --repo ofirzip/pulse-demo --cloud gcp` → scan `ada6a890-…`
- `vast code scan-repo --repo ofirzip/pulse-demo --ignore tests` (AllScanners, incl. SaaS) → scan `13b9cef0-…`
- `vast code scan-repo --repo ofirzip/pulse-infra --cloud gcp` → scan `b82b20c7-…`
- `vast code assess-risk <repo>` / `vast code get-risk <repo>` / `vast code get-policy <repo>`

| # | Expected | Observed (Track 1) | Verdict |
|---|---|---|---|
| C1 | `sensitivity.saas_usage` fires | **Anthropic detected** in SaaS inventory (`api.anthropic.com`, pkg `anthropic`, `data_shared: pii`, from `enrichment.py`+`requirements.txt`). But `saas_usage` is **informational** → **not** a scored risk finding; `get-risk` = `none`, `findings: []`. | ⚠️ **Detected, not flagged** (inventory only) |
| C2 | `llm_data_sharing` / `saas_pii_egress` | Not surfaced (planned detectors). Input present (PII in prompt). | ✅ as expected (planned) |
| C3 | `hardcoded_secret` | Not surfaced (Secrets scanner coming-soon). | ✅ as expected (planned) |
| C4 | `secrets_to_third_party` | Not surfaced (planned). | ✅ as expected (planned) |
| C5 | narrow used-permission set | **Confirmed** — generated least-privilege role = **7 perms**: `pubsub.topics.publish/create`, `pubsub.subscriptions.consume`, `bigquery.jobs.create`, `bigquery.tables.updateData`, `storage.objects.create/delete`. | ✅ confirmed |
| B1 | `unused_permissions` / `broad_service_grant` | **Not surfaced.** `iac_frameworks: []` — the Terraform IAM grants were **not extracted**; GCP IaC grant-parsing isn't wired. Static scan cannot see the over-grant. | ⚠️ **needs Track 2** (live `check-drift`) |
| B2 | `admin_grant` | Not surfaced (planned + no IaC extraction). | ✅ as expected |
| B3 | `least_privilege_aligned` absent | N/A — no blast finding either way from the static scan. | — deferred to Track 2 |
| B4 | `public_data_store` / `public_workload` | Not surfaced. IaC config (`allUsers` bucket) not parsed. | ✅ as expected (planned) |
| B5 | `public_workload` / `unauthenticated_endpoint` | Not surfaced. `allUsers` invoker not parsed. | ✅ as expected (planned) |
| B6 | `unencrypted_data` | Not surfaced. | ✅ as expected (planned) |

### Key learnings
1. **`saas_usage` is inventory, not a risk finding.** VAST *catalogs* the Anthropic/PII integration
   (visible via `get-repo` → `third_party_api` and the web Observations/External-APIs tab) but the
   CLI `assess-risk`/`get-risk` show only *risky* findings, so it reads as `none`. The scoring
   egress observations that would flag it are `planned`.
2. **GCP Terraform grant-extraction is not wired.** Scanning `pulse-infra` yielded `iac_frameworks: []`
   and extracted **no** IaC IAM permissions — the `roles/owner` / `allUsers` grants were invisible to
   the static scan. (The GCP "usage" VAST *did* report for pulse-infra came from the vendored
   `functions/daily_aggregation/*.py` copies, not the `.tf` files.) → the over-privilege/drift story
   requires **Track 2** (`vast mapping check-drift --cloud gcp --project …`).
3. **Live plumbing already exists.** VAST already maps `pulse-demo → pulse-runner@…` and IAM
   Recommender runs against the live project (`recommender_ran: true`), currently reporting the SA as
   *right-sized* — because the `roles/owner` grant isn't deployed. Deploying it (Track 2) is what
   would flip this to `excess`.

**Net:** on today's GCP engine, static Track 1 confirms the **code-side inputs** (SaaS integration
detected, narrow used-permissions extracted) but produces **no scored findings** — every planted
observation is informational, `planned`, or (for the IaC grants) not yet extracted. The scored
over-privilege result requires Track 2.

---
_Last updated: 2026-07-18. Line numbers reference commits `pulse-demo@f8e51e9`,
`pulse-infra@17a5729`. Track 1 observed against VAST `APT` @ current checkout._
