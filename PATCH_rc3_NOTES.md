# Phase 3 — rc3 notes (pick-up from where you got stuck)

## TL;DR — what to do right now

1. **Ctrl-C out of the stuck OAuth prompt** in the current PowerShell window
2. **Apply the rc3 patch** (full zip or surgical — either works)
3. **Edit `islandadvantage.yaml`** to pick ONE connector (Gmail OR Drive, or both)
4. **Run with the pre-filled config** — skips the whole interview:
   ```powershell
   .\bootstrap.ps1 -SkipPrereqs -ConfigFile islandadvantage.yaml
   ```

You'll go straight to GCP sign-in → project creation → all the rest. No more interview questions.

---

## What rc3 fixes

### Bug: OAuth was in the wrong step

The "You need additional access to project island-advantage-realty-rag-14" screen you hit was **not a permissions problem**. The project literally didn't exist yet — the installer was still in Step 2 (interview) and project creation is Step 4. The link sent you to a page for a project that hadn't been created.

**Fix:** OAuth client ID/secret collection moved out of the interview entirely. After the bootstrap provisions everything, the final summary screen tells you to:
- Open the OAuth consent + credentials console pages (project exists now, links work)
- Save the downloaded OAuth JSON to `secrets\gmail-oauth-client.json`
- Run `python -m installer.connectors.gmail authorize` to finalize

That ordering makes physical sense. The interview got it backwards.

### Bug: too many prompts

You called out — correctly — that these have one right answer 99% of the time. **Removed from the interview, hardcoded as static defaults:**

- Country = `US`
- Language = `en`
- Content config = `CONTENT_REQUIRED`
- Industry vertical = `GENERIC`
- Layout Parser = `ON`

If a future advanced user needs to override, they edit `config/config.yaml` before the GCP steps run.

### Bug: multi-select checkbox was error-prone

You accidentally picked 2 connectors when you only wanted 1. **Replaced with two clear Y/N prompts:**

```
? Enable Gmail connector? (indexes a mailbox) (Y/n)
? Enable Google Drive connector? (indexes folders) (Y/n)
```

No more toggling, no surprise picks.

### Bug: the Workspace question was confusing

You asked "what's a Workspace?" Fair question. Google Workspace = the paid business product (`you@yourcompany.com` backed by Google). Your `@gmail.com` address is personal Gmail, which is **not** Workspace.

The question is gone. The installer now always uses the safe pattern (service account + folder share for Drive, explicit OAuth per-mailbox for Gmail) which works for both personal Gmail and Workspace.

---

## What's in this drop

| File | What it is |
|---|---|
| `Phase3_Bootstrap_rc3.zip` | Full bundle with all patches applied (unzip to replace the current folder) |
| `Phase3_Bootstrap_patch_rc3.zip` | Surgical patch — just the 6 files that changed |
| `islandadvantage.yaml` | Pre-filled config with everything you already typed (skips the interview entirely) |

---

## Full step-by-step

### 1. Kill the stuck shell

In your current PowerShell window: press **Ctrl-C** to exit the hung OAuth prompt.

### 2. Apply the patch (pick one)

**Path A — full replace (simpler):**

```powershell
cd D:\LAB\vertex-ai-search

# Back up, for safety
Move-Item .\Phase3_Bootstrap .\Phase3_Bootstrap.rc2.bak -ErrorAction SilentlyContinue

# Drop in rc3
Expand-Archive .\Phase3_Bootstrap_rc3.zip -DestinationPath . -Force
```

**Path B — surgical overlay:**

```powershell
cd $env:TEMP
Expand-Archive $HOME\Downloads\Phase3_Bootstrap_patch_rc3.zip -DestinationPath .\phase3_patch_rc3 -Force
$dest = "D:\LAB\vertex-ai-search\Phase3_Bootstrap"
Copy-Item .\phase3_patch_rc3\installer\interview\business.py        $dest\installer\interview\business.py        -Force
Copy-Item .\phase3_patch_rc3\installer\interview\vertex.py          $dest\installer\interview\vertex.py          -Force
Copy-Item .\phase3_patch_rc3\installer\interview\connectors_menu.py $dest\installer\interview\connectors_menu.py -Force
Copy-Item .\phase3_patch_rc3\installer\interview\gmail_iv.py        $dest\installer\interview\gmail_iv.py        -Force
Copy-Item .\phase3_patch_rc3\installer\interview\gdrive_iv.py       $dest\installer\interview\gdrive_iv.py       -Force
Copy-Item .\phase3_patch_rc3\installer\banner.py                    $dest\installer\banner.py                    -Force
```

### 3. Drop the pre-filled config into place

```powershell
Copy-Item $HOME\Downloads\islandadvantage.yaml D:\LAB\vertex-ai-search\Phase3_Bootstrap\
```

### 4. Edit the config — tell it which connector you want

Open `D:\LAB\vertex-ai-search\Phase3_Bootstrap\islandadvantage.yaml` in any editor.

**Two edits to make:**

a. **Disable whichever connector you DON'T want.** Find this section:
```yaml
  - name: "gdrive"
    enabled: true      # <-- change to false if you only want Gmail
```
Do the same for `gmail` if you only want Drive.

b. **If you enabled Drive, paste your folder IDs.** Find:
```yaml
    options:
      mode: "service_account"
      drive_type: "specific_folders"
      folder_ids: []     # <-- put your folder IDs here
```
Become:
```yaml
      folder_ids:
        - "1aBcDeFg..."
        - "2xYzQrSt..."
```
Get a folder ID from its Drive URL: `https://drive.google.com/drive/folders/THIS-IS-THE-ID`.

Or leave it empty — you can add folder IDs later to `config/config.yaml` and re-run.

### 5. Run with the pre-filled config

```powershell
cd D:\LAB\vertex-ai-search\Phase3_Bootstrap
.\bootstrap.ps1 -SkipPrereqs -ConfigFile islandadvantage.yaml
```

**Expected flow:**

```
>>> Launching Python installer
  Step 1 — skipped (--skip-prereqs)
  Config loaded from islandadvantage.yaml    ← interview skipped!
  Step 3 — Google Cloud sign-in
  ...gcloud auth login flow...
  Step 4 — GCP project
  Creating project 'island-advantage-realty-rag-14'...
  ...
```

You'll spend most of your time at "Step 3 — sign-in" doing the browser dance, then the rest runs on autopilot.

---

## After the bootstrap finishes (important)

The final panel will print a numbered checklist. The two non-skippable items:

### OAuth for Gmail (if you kept Gmail enabled)

The final report will print exact URLs and filenames. Summary:

1. Open the consent screen page (project exists now — link works):
   ```
   https://console.cloud.google.com/apis/credentials/consent?project=island-advantage-realty-rag-14
   ```
   - Pick "External" user type (you're on personal Gmail, not Workspace)
   - Add your Gmail as a Test User under the "Test users" section
   - Add scope: `https://www.googleapis.com/auth/gmail.readonly`

2. Create an OAuth client ID:
   ```
   https://console.cloud.google.com/apis/credentials?project=island-advantage-realty-rag-14
   ```
   - Create Credentials → OAuth client ID → Desktop app
   - Download the JSON, save it to:
     ```
     D:\LAB\vertex-ai-search\Phase3_Bootstrap\secrets\gmail-oauth-client.json
     ```

3. Finalize:
   ```powershell
   cd D:\LAB\vertex-ai-search\Phase3_Bootstrap
   .\.venv\Scripts\python.exe -m installer.connectors.gmail authorize
   ```

### Share Drive folders (if you kept Drive enabled)

For each folder ID you put in the config, open it in Drive, click **Share**, paste the SA email the installer printed (looks like `island-advantage-realty-rag-sa@...iam.gserviceaccount.com`), set role = **Viewer**, click Share.

Without this step, the sync will see zero files.

---

## One more fix this round

The rc3 banner.py also makes the post-install checklist **much clearer** — it walks you through OAuth with copy-pasteable URLs that include your actual project ID. The old version was generic and easy to miss.

---

## If something else goes wrong

Paste the new traceback and I'll patch it the same way. This smoke-test loop is how every installer gets solid. Two rounds in, we've already eliminated the biggest Windows subprocess bug, the exit-code bug, the flag-pass-through bug, and now the five interview UX bugs. Each round makes the framework more production-ready.
