"""GCP project + billing interview."""

from __future__ import annotations

import random

from installer.config.schema import BusinessConfig, GCPConfig
from installer.utils import shell, ui
from installer.validators import gcp_project_id, non_empty


def run(business: BusinessConfig) -> GCPConfig:
    """GCP interview. Accepts business arg for project ID suggestion."""
    ui.section(
        "2c — Google Cloud Platform",
        "We need a GCP project to host the Vertex AI Search data store, GCS buckets, "
        "and service accounts.",
    )

    has_account = ui.ask_bool(
        "Do you already have a Google Cloud account?",
        default=True,
    )
    if not has_account:
        ui.note(
            "You'll need a Google Cloud account. Sign up at:\n"
            "  https://console.cloud.google.com/freetrial\n\n"
            "Re-run this installer after you've created an account."
        )
        raise SystemExit(0)

    use_existing = ui.ask_bool(
        "Do you want to use an existing GCP project?",
        default=False,
    )

    project_id: str
    project_exists: bool
    if use_existing:
        project_id = ui.ask_text(
            "Existing project ID",
            help_text="The GCP project ID (not the name or number). "
                      "Find it at https://console.cloud.google.com/",
            validator=gcp_project_id,
        )
        project_exists = True
    else:
        # Suggest a project ID based on business name + random suffix
        suffix = random.randint(10, 99)
        suggested = f"{business.display_name}-rag-{suffix}"
        
        project_id = ui.ask_text(
            "New project ID",
            default=suggested,
            help_text="6–30 chars, start with a letter, lowercase only. "
                      "This is immutable once created — choose carefully.",
            validator=gcp_project_id,
        )
        ui.note(f"A new project '{project_id}' will be created in Step 4.")
        project_exists = False

    has_org = ui.ask_bool(
        "Is this project under a Google Workspace organization?",
        default=False,
    )
    org_id = None
    folder_id = None
    if has_org:
        org_id = ui.ask_text(
            "Organization ID (digits only)",
            required=False,
            help_text="Find it at https://console.cloud.google.com/iam-admin/settings",
        )
        folder_id = ui.ask_text(
            "Folder ID (optional)",
            required=False,
            help_text="If the project should live inside a folder. Leave blank for org root.",
        )

    # List billing accounts
    ui.note("Listing billing accounts you can link...")
    res = shell.run(
        ["gcloud", "billing", "accounts", "list", "--format=value(name,displayName)"],
        check=False,
        timeout=30,
    )
    if not res.ok or not res.stdout.strip():
        ui.warn(
            "No billing accounts found, or gcloud can't list them. "
            "You may need to create one at https://console.cloud.google.com/billing"
        )
        billing_account_id = ui.ask_text(
            "Billing account ID",
            help_text="Format: 01ABCD-234EFG-567HIJ",
            validator=non_empty,
        )
    else:
        lines = [ln.strip() for ln in res.stdout.strip().split("\n") if ln.strip()]
        choices = []
        for ln in lines:
            parts = ln.split(None, 1)
            if len(parts) >= 1:
                acct_id = parts[0].replace("billingAccounts/", "")
                display = parts[1] if len(parts) > 1 else acct_id
                choices.append(f"{acct_id}  —  {display}")
            else:
                choices.append(ln)
        if not choices:
            billing_account_id = ui.ask_text(
                "Billing account ID",
                help_text="No billing accounts detected via gcloud. "
                          "Enter manually (format: 01ABCD-234EFG-567HIJ).",
                validator=non_empty,
            )
        else:
            picked = ui.ask_select("Choose a billing account", choices=choices)
            billing_account_id = picked.split()[0]

    # Region is hardcoded
    region = "us-east1"
    ui.note(
        f"Region set to: {region}\n"
        "(GCS buckets, Cloud Run, and Scheduler will use this region. "
        "Vertex AI Search data stores are always 'global'.)"
    )

    return GCPConfig(
        project_id=project_id,
        project_exists=project_exists,
        organization_id=org_id,
        folder_id=folder_id,
        billing_account_id=billing_account_id,
        region=region,
        location="global",
    )
