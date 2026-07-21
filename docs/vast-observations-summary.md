# Pulse Security Demo — Simulated Risks & VAST Findings

A plain-language summary of the security mistakes planted into the two example
projects — the app code (`pulse-demo`) and its cloud setup (`pulse-infra`) — and
how VAST detects each one, with the exact code or policy behind it. For the detailed,
per-line verification table see
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

**Gives itself more power** — `blast.privilege_escalation` · **Critical**
The app rewrites the project's permission list to hand its own account a powerful role.
VAST's code scan spots the permission-change call and flags *privilege escalation*.

```python
# scheduler.py — ensure_runner_permissions()
policy = client.get_iam_policy(request={"resource": resource})
policy.bindings.add(role=RUNNER_ROLE, members=[member])   # RUNNER_ROLE = "roles/editor"
client.set_iam_policy(request={"resource": resource, "policy": policy})
```

**Reads a stored secret** — `sensitivity.high_service` · **High**
The app pulls a secret API key out of Google's secret vault. VAST sees the secret-read
call and flags *"reads secrets."*

```python
# enrichment.py — load_api_key()
client = secretmanager.SecretManagerServiceClient()
response = client.access_secret_version(name=ANTHROPIC_KEY_SECRET)
return response.payload.data.decode("utf-8")
```

**Can delete stored data** — `blast.write_delete` · **High**
The app can erase report files from cloud storage. VAST sees the delete call and flags
*"can destroy data."*

```python
# report_exporter.py — delete_old_report()
client = storage.Client(project=PROJECT_ID)
client.bucket(bucket_name).blob(blob_name).delete()
```

**Can pull out large amounts of data** — `sensitivity.medium_service` · **High**
The app runs large database queries that could extract many records. VAST sees the query
call and flags a *data-exfiltration risk*.

```python
# report_exporter.py — run_aggregation_query()
client = bigquery.Client(project=PROJECT_ID)
job = client.query(sql)
```

**Sends data to an outside AI service** — `sensitivity.saas_usage` · **Info**
The app hands each user's activity to an external AI (Anthropic) to label it. VAST lists
the AI service and notes personal data is shared — recorded for context.

```python
# enrichment.py — enrich_event()
client = anthropic.Anthropic(api_key=load_api_key(), base_url=ANTHROPIC_BASE_URL)
response = client.messages.create(
    model=ENRICH_MODEL, messages=[{"role": "user", "content": prompt}])
```

### From drift detection (`pulse-infra` + live project)

**Wildly over-powered account** — `blast.unused_permissions`, `blast.broad_service_grant` · **Critical**
The account that runs the app was given full *Owner* of the project, but the code only
needs a handful of permissions. Drift compares granted vs used and finds **13,524**
permissions granted but never touched → flagged over-privileged.

```hcl
# modules/iam/main.tf — granted during the rushed launch, never scoped back down
project_roles = toset([ ... "roles/owner" ])

resource "google_project_iam_member" "project_roles" {
  role   = each.value
  member = "serviceAccount:${google_service_account.pulse_runner.email}"
}
```

**Loses the "properly locked down" credit** — `blast.least_privilege_aligned` *(absent)* · **Info**
A well-scoped app earns a positive "least privilege" mark; the `roles/owner` grant above
breaks the tidy baseline, so the positive mark is *absent* — the good score you'd
otherwise see is gone. (No snippet — this is the *absence* of a finding.)

---

## Planted — detector still being built

These mistakes are staged in the code and cloud setup, and VAST records the raw evidence.
The specific scored check hasn't shipped yet, so they'll light up automatically once it does.

**Personal data in the AI prompt** — `sensitivity.llm_data_sharing`, `sensitivity.saas_pii_egress`
The full event, including the user's ID, is put into the AI request.

```python
# enrichment.py — event = {"user_id": ..., "properties": {...}}
prompt = _PROMPT_TEMPLATE.format(event=json.dumps(event))
```

**Hardcoded secret** — `sensitivity.hardcoded_secret`
An API key is written directly into the code as a fallback.

```python
# enrichment.py
ANTHROPIC_API_KEY = "sk-ant-api03-Xq7pL2mN8k…Kd4"
```

**Secret sent to a third party** — `sensitivity.secrets_to_third_party`
That same key travels out of the estate with every AI call.

```python
# enrichment.py
anthropic.Anthropic(api_key=load_api_key(), base_url="https://api.anthropic.com")
```

**Public report storage** — `sensitivity.public_data_store`, `exposure.public_workload`
The bucket holding user-derived reports is set readable by anyone.

```hcl
# modules/storage/main.tf
resource "google_storage_bucket_iam_member" "public_reports" {
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}
```

**Anyone can trigger the function** — `exploitability.unauthenticated_endpoint`
The cloud function accepts calls with no sign-in required.

```hcl
# environments/prod/main.tf
resource "google_cloudfunctions_function_iam_member" "public_invoker" {
  role   = "roles/cloudfunctions.invoker"
  member = "allUsers"
}
```

**No customer-managed encryption** — `sensitivity.unencrypted_data`
Storage and database rely on default keys only — no `kms_key_name` block is set, so there
are no keys you control. (No snippet — this is the *absence* of an encryption block.)

**Admin-level grant** — `blast.admin_grant`
The Owner role handed to the runner is admin-level, the strongest tier — the same
`roles/owner` grant shown under "Wildly over-powered account" above.

---

_Detection engine: VAST (code scan + drift detection). Code & cloud setup: `pulse-demo` (app),
`pulse-infra` (cloud). Last updated: 2026-07-21._
