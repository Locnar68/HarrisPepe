# 02 — Interview Guide

Every question the installer will ask, grouped by section. Use this as a **pre-interview worksheet** — gather the answers up-front and the interview goes very quickly.

---

## 2a — Business

| Field | Type | Example | Notes |
|---|---|---|---|
| Legal company name | text | `Madison Ave Construction LLC` | Appears on billing / audit docs. |
| Display name | text, auto-suggested | `madison-ave-construction` | 2–30 chars, lowercase letters/digits/hyphens only. Used as a prefix for bucket names, SA names, Vertex IDs. |
| Primary domain | text | `madisonaveconstruction.com` | Used for Workspace detection and to pre-fill the contact email. |
| Industry / vertical | select | `construction` | Pick closest — Vertex can tune retrieval slightly. |
| Country (ISO 3166-1 alpha-2) | text | `US` | Two-letter code. |

---

## 2b — Primary contact

| Field | Type | Example | Notes |
|---|---|---|---|
| Full name | text | `Michael Pepe` | |
| Email | text, validated | `admin@madisonaveconstruction.com` | Receives billing alerts and system notifications. |
| Phone | text, optional | `+16315550100` | E.164 format or US-style. Leave blank to skip. |
| Role | select | `Owner` | Owner / CTO / IT Admin / Ops / Developer / Other |

---

## 2c — Google Cloud

| Field | Type | Example | Notes |
|---|---|---|---|
| Do you have a GCP account? | yes / no | yes | If no, installer shows signup link and exits. |
| Use an existing project? | yes / no | yes | If yes, installer lists visible projects. |
| Project ID | text, validated | `commanding-way-380716` | 6–30 chars, lowercase letters/digits/hyphens. Immutable. |
| Workspace organization? | yes / no | no | Only if your project sits under a Workspace org. |
| Organization ID | text, optional | `123456789012` | Numeric. Run `gcloud organizations list` if unsure. |
| Folder ID | text, optional | `987654321098` | Leave blank if project is directly under org. |
| Billing account | select from visible list | `01ABCD-234EFG-567HIJ` | If none visible, installer shows link to create one. |
| Default region | select | `us-central1` | Used for GCS, Cloud Run, Scheduler. |

Note: Vertex AI Search data stores are always `location=global` — this is currently the only valid value.

---

## 2d — Service account

| Field | Type | Example | Notes |
|---|---|---|---|
| SA short name | text, validated | `madison-ave-construction-rag-sa` | 6–30 chars, lowercase letters/digits/hyphens. |
| SA display name | text | `madison-ave-construction RAG pipeline` | Shown in Cloud console. |

Roles granted (not asked — baked into the installer):

- `roles/storage.admin`
- `roles/discoveryengine.admin`
- `roles/secretmanager.secretAccessor`
- `roles/aiplatform.user`
- `roles/run.invoker`
- `roles/cloudscheduler.admin`
- `roles/logging.logWriter`

---

## 2e — Storage

| Field | Type | Example | Notes |
|---|---|---|---|
| Raw bucket name | text, validated | `madison-ave-construction-rag-raw` | Globally unique in GCS. |
| Processed bucket name | text, validated | `madison-ave-construction-rag-processed` | Globally unique in GCS. |
| Archive bucket (optional) | text | `madison-ave-construction-rag-archive` | Leave blank to skip. |
| Storage class | select | `STANDARD` | Standard / Nearline / Coldline / Archive. |
| Enable lifecycle rule? | yes / no | yes | Only asked if archive bucket is set. |
| Days before archive | integer | `90` | 1–3650. |

---

## 2f — Vertex AI Search

| Field | Type | Example | Notes |
|---|---|---|---|
| Data store ID | text, validated | `madison-ave-construction-ds-v1` | Append `-v2`, `-v3` on re-runs to dodge the reserved-ID window. |
| Engine ID | text, validated | `madison-ave-construction-engine-v1` | |
| Tier | select | `ENTERPRISE` | **Enterprise recommended.** Standard summarization is conservative on form-heavy PDFs (POC learning). |
| Content config | select | `CONTENT_REQUIRED` | `CONTENT_REQUIRED` / `NO_CONTENT` / `PUBLIC_WEBSITE`. |
| Industry vertical | select | `GENERIC` | `GENERIC` / `MEDIA` / `HEALTHCARE_FHIR`. |
| Language code | text | `en` | BCP-47. |
| Enable Layout Parser? | yes / no | yes | **Must be set at creation time — cannot be patched later.** Recommended ON. |

---

## 2g — Connector menu

Multi-select. **Defaults: Gmail + Google Drive checked.**

- Gmail
- Google Drive
- OneDrive (Phase 4 stub)
- SQL database (Phase 4 stub)
- File share / SMB (Phase 4 stub)

---

## 2h — Gmail connector (if enabled)

| Field | Type | Example | Notes |
|---|---|---|---|
| Is domain a Workspace account? | yes / no | yes | If no, installer warns: personal Gmail blocks `drive.readonly` OAuth scope. |
| OAuth client ID | text | `12345...apps.googleusercontent.com` | Created manually in the console — installer provides link. |
| OAuth client SECRET | password | hidden | Goes straight to Secret Manager. |
| Mailbox email | text, validated | `info@madisonaveconstruction.com` | The inbox that will be indexed. |
| Gmail label | text | `INBOX` | Or a custom label. |
| Gmail search query | text, optional | `newer_than:90d` | Any Gmail search query. |
| Sync frequency | select | `0 */6 * * *` | Or `custom` to enter a cron. |

---

## 2i — Google Drive connector (if enabled)

| Field | Type | Example | Notes |
|---|---|---|---|
| Access mode | select | `service_account` | SA mode recommended; works with personal Gmail. OAuth mode is Workspace-only. |
| Drive type | select | `specific_folders` | `my_drive` / `shared_drive` / `specific_folders`. |
| Folder IDs | text, validated | `1aBc...,2dEf...` | Comma-separated. From the Drive URL. |
| MIME allowlist | text | (default list) | Comma-separated MIME types, or `*` for all. |
| OAuth client ID (only if mode=oauth) | text | | |
| OAuth client SECRET (only if mode=oauth) | password | | |
| Sync frequency | select | `0 */3 * * *` | |

---

## 2j — Review

A final table showing every collected value. Confirm with `Y` to start creating GCP resources.

**After this point the installer begins making changes.** Nothing is created up to and including the review screen.
