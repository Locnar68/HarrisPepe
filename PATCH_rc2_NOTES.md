# Phase 3 — Patch rc2

Fixes three bugs you hit during the first smoke test on Windows.

## What's fixed

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | `gcloud --version` → `WinError 2: The system cannot find the file specified` | Python `subprocess.run(["gcloud", ...], shell=False)` ignores PATHEXT; can't find `gcloud.cmd` | `installer/utils/shell.py` now resolves Windows commands via `shutil.which` before handing them to subprocess |
| 2 | Wrapper printed "Phase 3 bootstrap complete" in green *after* a fatal error | `__main__.py` didn't propagate Python's return code; `$LASTEXITCODE` stayed at 0 | `installer/__main__.py` now calls `sys.exit(cli())` |
| 3 | `-SkipPrereqs` skipped the PowerShell checks but Python still ran its own prereq checks → crashed on bug #1 | `bootstrap.ps1` never passed the flag through | `bootstrap.ps1` now appends `--skip-prereqs` to the Python args; `installer/main.py` adds the argparse flag |

## How to apply — pick ONE

### Path A (simpler): re-unzip the full bundle

```powershell
# 1. Close any PowerShell window that has Phase3_Bootstrap\.venv activated
# 2. Optionally back up the existing folder
Move-Item D:\LAB\vertex-ai-search\Phase3_Bootstrap D:\LAB\vertex-ai-search\Phase3_Bootstrap.pre-rc2.bak

# 3. Unzip the new bundle
cd D:\LAB\vertex-ai-search
Expand-Archive .\Phase3_Bootstrap_rc2.zip -DestinationPath . -Force

# 4. Re-run (the .venv will be recreated automatically)
cd Phase3_Bootstrap
.\bootstrap.ps1 -SkipPrereqs    # should get past gcloud check now
```

### Path B (surgical): overlay just the 4 changed files

```powershell
# 1. Unzip the patch somewhere
cd $env:TEMP
Expand-Archive $HOME\Downloads\Phase3_Bootstrap_patch_rc2.zip -Force
cd phase3_patch

# 2. Copy each patched file over the existing install
$dest = "D:\LAB\vertex-ai-search\Phase3_Bootstrap"
Copy-Item .\bootstrap.ps1                  $dest\bootstrap.ps1                  -Force
Copy-Item .\installer\__main__.py          $dest\installer\__main__.py          -Force
Copy-Item .\installer\main.py              $dest\installer\main.py              -Force
Copy-Item .\installer\utils\shell.py       $dest\installer\utils\shell.py       -Force

# 3. Keep your existing .venv — no need to rebuild it
cd $dest
.\bootstrap.ps1 -SkipPrereqs
```

## Expected behaviour after the patch

Running `.\bootstrap.ps1 -SkipPrereqs` should now print:

```
>>> Launching Python installer
...
┌─ Step 1 — Host prerequisites (skipped) ─────────────────────┐
│ Called with --skip-prereqs.                                 │
│ Assuming Python + gcloud + git are all present.             │
└─────────────────────────────────────────────────────────────┘

┌─ Step 2 — Interactive interview ────────────────────────────┐
...first question: Legal company name...
```

From here you're in the real interview. Hit **Ctrl-C at the first question** to back out cleanly — no GCP resources have been created yet. State is saved to `state\bootstrap.state.json`, so you can re-run with `-Resume` to continue when you're ready to answer for real.

If you DON'T use `-SkipPrereqs`, the installer will run the normal prereq checks — and with the `shell.py` fix, the `gcloud --version` call will now succeed on Windows.

## Re-run the tests to confirm

```powershell
cd D:\LAB\vertex-ai-search\Phase3_Bootstrap
.\.venv\Scripts\Activate.ps1
python -m pytest tests/ -v
deactivate
```

Should still show **85 passed**. I re-ran them in the sandbox with the patches applied.

## If you hit something else

Check the bootstrap log — it captures every subprocess call:

```powershell
cd D:\LAB\vertex-ai-search\Phase3_Bootstrap\logs
Get-Content (Get-ChildItem bootstrap-*.log | Sort-Object LastWriteTime -Desc | Select-Object -First 1)
```

Paste any new traceback back and I'll fix it the same way. This is exactly what a smoke test is for.

## Unrelated: the Flask error from earlier

Your `scripts\web.py` failed with `No module named 'flask'`. That's not Phase 3 — it's Phase 1 code running in your system Python (which doesn't have Flask installed). Either:

- `D:\Python313\Scripts\pip.exe install flask` to install system-wide, or
- Run `scripts\web.py` from the Phase 1/2 venv where Flask is already available

Don't install Flask into the Phase3_Bootstrap `.venv` — that venv is for the installer only and should stay lean.
