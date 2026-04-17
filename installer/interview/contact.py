"""Primary contact interview."""

from __future__ import annotations

from installer.config.schema import BusinessConfig, ContactConfig
from installer.utils import ui
from installer.validators import email, non_empty, phone as phone_v


def run(business: BusinessConfig) -> ContactConfig:
    ui.section(
        "2b — Primary contact",
        "Who is the point person for this deployment? Name + email are required; "
        "phone is optional.",
    )

    full_name = ui.ask_text(
        "Full name",
        validator=lambda v: non_empty(v, field_name="full_name"),
    )
    email_addr = ui.ask_text(
        "Email address",
        help_text="This is who will receive system alerts and billing notifications.",
        validator=email,
    )
    phone_num = ui.ask_text(
        "Phone (optional)",
        required=False,
        help_text="Digits only or E.164 format (+14155551212). Leave blank to skip.",
        validator=phone_v,
    )

    return ContactConfig(
        full_name=full_name,
        email=email_addr,
        phone=phone_num,
        role="Administrator",  # hardcoded — no prompt
    )
