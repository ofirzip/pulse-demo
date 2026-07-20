# Pulse Security Demo — Simulated Risks & VAST Findings

A plain-language summary of the security mistakes planted into the two example
projects — the app code (`pulse-demo`) and its cloud setup (`pulse-infra`) — and
how VAST detects each one. For the detailed, per-line verification table see
[`vast-observations-verification.md`](./vast-observations-verification.md).

## How VAST finds things (two ways)

- **Code scan** — VAST reads the app's source code and lists what it does with cloud
  services: reading secrets, deleting data, changing permissions, and so on.
- **Drift detection** — VAST compares the permissions the app was *granted* against the
  ones it actually *uses*. A large gap means the app is over-powered.

**Status legend:** **Detected now** = fires in a live VAST scan today · **Planted** =
staged in the repos and the raw evidence is present, but VAST's specific scored check
isn't shipped yet, so it will light up automatically once that detector ships.

---

## Detected today

These fire in a live scan of the demo right now. The code-scan result went from a clean
bill of health to an overall **Critical** rating.

### From the code scan (`pulse-demo`)

| Risk (plain language) | Severity | How it's simulated | How VAST catches it | Observation |
|---|---|---|---|---|
| **Gives itself more power** — the app rewrites the project's permission list to hand its own account a powerful role. | Critical | The scheduler calls `set_iam_policy` to grant the `pulse-runner` account a role. | The scan spots the permission-change call and flags *privilege escalation*. | `blast.privilege_escalation` |
| **Reads a stored secret** — the app pulls a secret API key out of Google's secret vault. | High | The enrichment step fetches the key with `access_secret_version`. | The scan sees the secret-read call and flags *"reads secrets."* | `sensitivity.high_service` |
| **Can delete stored data** — the app can erase report files from cloud storage. | High | The report step deletes old files with `objects.delete`. | The scan sees the delete call and flags *"can destroy data."* | `blast.write_delete` |
| **Can pull out large amounts of data** — the app runs large database queries that could extract many records. | High | The report step runs BigQuery queries (`jobs.create`). | The scan sees the query call and flags a *data-exfiltration risk*. | `sensitivity.medium_service` |
| **Sends data to an outside AI service** — the app hands each user's activity to an external AI (Anthropic) to label it. | Info | The enrichment step calls the Anthropic API with the event data. | The scan lists the AI service and notes personal data is shared — recorded for context. | `sensitivity.saas_usage` |

### From drift detection (`pulse-infra` + live project)

| Risk (plain language) | Severity | How it's simulated | How VAST catches it | Observation |
|---|---|---|---|---|
| **Wildly over-powered account** — the account that runs the app was given full *Owner* of the project, but the code only needs a handful of permissions. | Critical | The cloud setup grants `roles/owner` to the `pulse-runner` account. | Drift compares granted vs used and finds **13,524** permissions granted but never touched → flagged over-privileged. | `blast.unused_permissions`, `blast.broad_service_grant` |
| **Loses the "properly locked down" credit** — a well-scoped app earns a positive "least privilege" mark; the over-grant means this one doesn't. | Info | Same `roles/owner` grant — it breaks the tidy baseline. | The positive mark is *absent* from the result — the good score you'd otherwise see is gone. | `blast.least_privilege_aligned` (absent) |

---

## Planted — detector still being built

These mistakes are staged in the code and cloud setup, and VAST records the raw evidence.
The specific scored check hasn't shipped yet, so they'll light up automatically once it does.

| Risk (plain language) | How it's simulated | Observation |
|---|---|---|
| **Personal data in the AI prompt** — the full event, including the user's ID, is put into the AI request. | The enrichment prompt embeds the whole event payload. | `sensitivity.llm_data_sharing`, `sensitivity.saas_pii_egress` |
| **Hardcoded secret** — an API key is written directly into the code as a fallback. | An `sk-ant-…` key sits in `enrichment.py`. | `sensitivity.hardcoded_secret` |
| **Secret sent to a third party** — that same key travels out of the estate with every AI call. | The key is passed to the Anthropic client on each request. | `sensitivity.secrets_to_third_party` |
| **Public report storage** — the bucket holding user-derived reports is set readable by anyone. | `pulse-infra` grants `allUsers` read on the reports bucket. | `sensitivity.public_data_store`, `exposure.public_workload` |
| **Anyone can trigger the function** — the cloud function accepts calls with no sign-in required. | `pulse-infra` grants `allUsers` the invoker role. | `exploitability.unauthenticated_endpoint` |
| **No customer-managed encryption** — storage and database rely on default keys only, not keys you control. | No CMEK / encryption block on the bucket or dataset. | `sensitivity.unencrypted_data` |
| **Admin-level grant** — the Owner role handed to the runner is admin-level, the strongest tier. | Same `roles/owner` grant. | `blast.admin_grant` |

---

_Detection engine: VAST (code scan + drift detection). Code & cloud setup: `pulse-demo` (app),
`pulse-infra` (cloud). Last updated: 2026-07-20._
