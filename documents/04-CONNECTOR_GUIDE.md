# 04 — Connector Guide

How to add a new data source, or implement one of the Phase 2 stubs.

## The contract

Every connector subclasses `connectors.base.Connector`:

```python
from connectors.base import Connector, SyncStats

class MyConnector(Connector):
    name = "my_source"

    def sync(self, dry_run=False, force=False, log=print) -> SyncStats:
        stats = SyncStats()
        # walk source
        # for each file, upload to gs://<bucket>/<mirror_prefix>/<subpath>/...
        # set blob.metadata = {"source": self.name, "source_id": <stable id>,
        #                      "source_mtime": <rfc3339 or epoch>}
        # increment stats.walked / uploaded / skipped_same / errors / bytes
        return stats
```

Register it in `connectors/__init__.py`:

```python
REGISTRY = {
    ...,
    "my_source": MyConnector,
}
```

Turn it on in `config.yaml`:

```yaml
connectors:
  my_source:
    enabled: true
    # any fields you need; the dict is passed to your __init__ as self.c
```

Now `python scripts/sync.py` runs it alongside the others.

## Idempotency is mandatory

The same file must produce the same GCS object name on every sync. Use stable ids (Drive file id, email Message-ID, file hash). Skip uploads when `source_mtime` matches what's already in GCS metadata.

## Path layout matters

The metadata extractor expects `<mirror_prefix>/Properties/<property>/<category>/...`. Your connector decides how to map source structure to that shape. For non-file sources (Gmail, CSV), you can pick a synthetic layout — just make sure the path under `Properties/` still resolves to a `property` and `category` the schema recognizes.

## Implementing the Phase 2 stubs

### Gmail

**Auth.** Personal Gmail blocks service accounts. Two options:

1. **Per-user OAuth with `client_secret.json`.** Create OAuth client ID credentials (Desktop type) in Cloud Console. Use `google_auth_oauthlib.flow.InstalledAppFlow` on first run to pop a browser, get a refresh token, persist to `gmail_token.json`. Works for personal Gmail.
2. **Workspace domain-wide delegation.** Workspace admin delegates the SA the gmail.readonly scope; SA impersonates each user via `.with_subject(user_email)`. Works only if you control a Workspace domain.

**Layout.** For each matching message:

```
<mirror_prefix>/Properties/_inbox/06-Invoices/<YYYY-MM>/<msg_id>.eml
<mirror_prefix>/Properties/_inbox/06-Invoices/<YYYY-MM>/<msg_id>__<attach_name>
```

You'll need a synthetic property name (e.g., `_inbox`) — or parse the body for keywords and route to the right real property.

**Incremental.** Query once with `after:<epoch>` from a high-water mark stashed in GCS (e.g., `gs://bucket/_state/gmail_last_sync.txt`).

### OneDrive

**Auth.** Two options:

1. **rclone.** Already has an OneDrive backend that handles OAuth. Config the remote once (`rclone config`), ship the generated `rclone.conf` to Cloud Run via Secret Manager, shell out to `rclone copy`.
2. **Microsoft Graph SDK.** Native Python. More control, more code. Requires Azure AD app registration.

rclone is the fast path. Sketch:

```python
import subprocess
cmd = ["rclone", "copy",
       f"{self.c['remote_name']}:{self.c['source_path']}",
       f":gcs:{self.cfg.bucket}/{self.gcs_base(self.c.get('mirror_as','Properties'))}",
       "--config", self.c.get("rclone_config_path", "rclone.conf"),
       "--fast-list", "--transfers", "8"]
proc = subprocess.run(cmd, capture_output=True, text=True)
# parse proc.stdout for "Transferred: <n> files" to populate stats
```

### CSV

This one's different — you're synthesising documents from rows, not mirroring files.

For each row:
1. Render the row as a small text blob: `"Contact: Jane Doe\nCompany: Acme\n..."`
2. Upload to `gs://bucket/<mirror_prefix>/Properties/_csv/<category>/<row_id>.txt`
3. In step 3 (metadata), you'll want `category_folders` to map `_csv`-subfolders to a `doc_type` like `table`.

Alternative: emit JSONL records directly (skip the GCS file) and feed them via the inline path in `ImportDocuments`. Faster, but caps at ~100 docs per call.

### Local files

Already shipped. See `connectors/local_files.py` as a reference implementation — it's ~60 lines and covers all the patterns (glob, mtime skip, metadata stamp).

## Testing a new connector

```powershell
python scripts\sync.py --only my_source --dry-run
python scripts\sync.py --only my_source
gcloud storage ls gs://<bucket>/data/ --recursive | head -20
python scripts\index.py --discover
python scripts\index.py
python scripts\query.py "something specific to that source"
```
