# 03 — GCP Account Setup (first-time users)

If you've never used Google Cloud before, do these steps once, then come back and run `.\bootstrap.ps1`.

---

## Step 1 — Sign up

Go to **https://cloud.google.com/free** and click **Get started for free**.

You'll be asked for:

- A Google account (personal Gmail works; Workspace works; it just has to be a Google identity)
- A phone number (for verification)
- A credit card (for identity — won't be charged unless you explicitly upgrade from Free Tier)
- Business name and country

When the wizard finishes, you land in the Cloud Console at **https://console.cloud.google.com/**.

> You get **$300 in credit** valid for 90 days. Phase 3 on a small corpus uses well under $50 in credit.

---

## Step 2 — Make sure the free trial billing account exists

Go to **https://console.cloud.google.com/billing**.

You should see a billing account called "My Billing Account" or "Billing Account for <email>". Confirm it's **Active** (open, not closed). That's the one the installer will ask you to pick.

If you're on a Workspace org, you may already have a shared billing account — either works.

---

## Step 3 — Create a new project (optional)

You can either:

- **Let the installer create one for you** (pick "no" to "use existing project" during the interview) — recommended.
- **Create one manually** at **https://console.cloud.google.com/projectcreate** first.

If creating manually: note the project ID (the string at the top, not the name). The installer asks for the ID, not the name.

---

## Step 4 — (Optional) Set up OAuth consent screen

Only required if you will enable the Gmail connector. If you're only using Drive, skip this step.

1. Go to **https://console.cloud.google.com/apis/credentials/consent**
2. User type:
   - **Internal** — if your email is on a Workspace domain, this is simpler (no verification, unlimited users in your org).
   - **External** — for personal Gmail. You'll start in "Testing" mode, which works fine for up to 100 test users and doesn't require Google review.
3. App registration:
   - App name: e.g. "Madison Ave RAG Pipeline"
   - User support email: your email
   - Developer contact information: your email
4. Scopes: click **Add or Remove Scopes** and add
   - `https://www.googleapis.com/auth/gmail.readonly`
5. (External only) Test users: add the Gmail address you want to sync.
6. Save and continue through the wizard.

You do **not** need to submit the app for verification to use it yourself in testing mode.

---

## Step 5 — (Optional) Create an OAuth 2.0 Client ID

Again, only for Gmail. Skip if using Drive only.

1. **https://console.cloud.google.com/apis/credentials** → **Create Credentials** → **OAuth client ID**
2. Application type: **Desktop app**
3. Name: e.g. "Phase 3 Gmail Sync"
4. Click **Create**.

Google will show you a **Client ID** and **Client secret**. Copy both — the installer will ask for them.

---

## Step 6 — Come back and run the bootstrap

```powershell
cd D:\LAB\vertex-ai-search\Phase3_Bootstrap
.\bootstrap.ps1
```

When the interview asks "Do you already have a Google Cloud account?" answer **yes**.

---

## What if I don't have a credit card?

Google requires one for identity verification but does not charge it during the trial. If you genuinely can't provide one, you have two options:

1. **Ask someone on a Workspace plan to invite you** as a member of their project — their billing covers yours. You'd then use the invited account to run the bootstrap.
2. **Skip the free trial and start on paid** — same dollar amounts, no free credit, but also no trial restrictions. Pick this during signup only if you know what you're doing.

The installer does not care which path you took — it just needs a working GCP account and a billing account it can link.
