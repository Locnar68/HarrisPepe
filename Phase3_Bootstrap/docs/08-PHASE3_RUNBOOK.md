# 08 — Phase 3 Runbook (for Michael)

Everything needed to get Phase 3 from this folder into the HarrisPepe GitHub repo safely, without disturbing Phase 1 or in-flight Phase 2 work.

---

## 1. Lock Phase 2 before starting Phase 3

The repo README currently marks Phase 2 as "🚧 In progress". Before merging Phase 3, freeze a Phase 2 baseline so you can roll back if anything breaks.

### Option A — Phase 2 is fully done

```powershell
cd D:\LAB\vertex-ai-search
git checkout main
git pull
git tag -a v2.0 -m "Phase 2 — Connector breadth + custom schema"
git push origin v2.0

gh release create v2.0 `
  --title "Phase 2 — Connector breadth + custom schema" `
  --notes-file documents/08-ROADMAP.md
```

### Option B — Phase 2 is partially done and you want to snapshot current state

```powershell
git tag -a v2.0-partial -m "Phase 2 snapshot before Phase 3 work"
git push origin v2.0-partial
```

Either way, the tag gives you a named checkpoint you can reset to if Phase 3 introduces regressions.

---

## 2. Create the Phase 3 branch

```powershell
cd D:\LAB\vertex-ai-search
git checkout main
git pull
git checkout -b phase-3
```

---

## 3. Drop the Phase3_Bootstrap folder into the repo

The Phase 3 files are currently staged at `D:\LAB\vertex-ai-search\Phase3_Bootstrap\`. You just need to add them to git:

```powershell
# From the repo root
git add Phase3_Bootstrap
git status

# Sanity-check: confirm .gitignore is excluding secrets
git check-ignore -v Phase3_Bootstrap/secrets/service-account.json
git check-ignore -v Phase3_Bootstrap/config/config.yaml
git check-ignore -v Phase3_Bootstrap/.venv
```

All three should report they are ignored. **If they aren't ignored, stop** — don't commit until the `.gitignore` is picking them up.

Commit:

```powershell
git commit -m "Phase 3: turnkey bootstrap framework

- One-command installer (bootstrap.ps1 / bootstrap.sh)
- Zero-assumption: detects/installs Python, gcloud, git via winget/apt/brew
- Exhaustive interactive interview (business, contact, GCP, SA, storage,
  Vertex, connectors)
- Menu-driven connector selection (Gmail + GDrive in Phase 3)
- REST-based data store provisioning (v1alpha, Layout Parser at creation)
- Handles deleted-ID reservation with auto -v2/-v3 fallback
- Treats LRO 404s during polling as success (POC lesson)
- Service account, GCS, Secret Manager, Cloud Run + Scheduler wiring
- Resumable via state/bootstrap.state.json
- Documentation under Phase3_Bootstrap/docs/"

git push -u origin phase-3
```

---

## 4. Update the repo-root README

Add a row to the Phase table in `/README.md`:

```markdown
| Phase 3 | Turnkey bootstrap framework | 🧱 In branch `phase-3` |
```

And near the top, add a pointer:

```markdown
> **New in Phase 3:** a zero-assumption turnkey installer. See [`Phase3_Bootstrap/`](./Phase3_Bootstrap/README.md).
```

Commit that separately:

```powershell
git add README.md
git commit -m "docs: point Phase 3 users at Phase3_Bootstrap/"
git push
```

---

## 5. Open the PR

```powershell
gh pr create --base main --head phase-3 `
  --title "Phase 3: turnkey bootstrap framework" `
  --body-file Phase3_Bootstrap/docs/08-PHASE3_RUNBOOK.md
```

---

## 6. (Once merged) tag Phase 3 release

```powershell
git checkout main && git pull
git tag -a v3.0 -m "Phase 3 — Turnkey bootstrap framework"
git push origin v3.0

gh release create v3.0 `
  --title "Phase 3 — Turnkey bootstrap framework" `
  --notes "One-command installer for the whole Vertex AI RAG stack.
Gmail + Drive connectors enabled. OneDrive/SQL/FileShare queued for Phase 4."
```

---

## 7. Smoke-test from a clean machine

The whole point of Phase 3 is that a fresh operator can run it on a machine that's never touched this project. Before you declare Phase 3 done, test that:

```powershell
# On a clean VM / new user account / fresh WSL shell:
git clone https://github.com/Locnar68/HarrisPepe.git
cd HarrisPepe\Phase3_Bootstrap
.\bootstrap.ps1
```

If the machine has no Python / gcloud / git, the bootstrap should install them (via winget) and prompt you to close-and-reopen PowerShell. If it skips straight to the interview, your machine is too prepared — try on a VM.

A full green run produces:

- A new (or reused) GCP project
- 7 required APIs enabled
- 1 service account with 7 role bindings
- 2 or 3 GCS buckets
- 1 Secret Manager secret per connector (Gmail / GDrive OAuth)
- 1 Vertex AI Search data store with Layout Parser
- 1 Search engine
- 2 Cloud Run jobs (Gmail sync, Drive sync)
- 2 Cloud Scheduler entries

Total wall-clock on a good network: **~8 minutes** after the interview (~15 minutes including interview time).

---

## 8. Rollback procedure

If Phase 3 goes sideways:

```powershell
# Delete the branch locally and remotely
git branch -D phase-3
git push origin --delete phase-3

# Reset main to the Phase 2 tag if you've already merged
git checkout main
git reset --hard v2.0    # or v2.0-partial
git push --force-with-lease origin main
```

**Don't do the force-push unless you're sure no one else has pulled Phase 3 already.** The safer rollback is a revert commit:

```powershell
git revert <phase3-merge-commit-sha>
git push
```
