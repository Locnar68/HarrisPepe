"""Business information interview."""

from __future__ import annotations

from installer.config.schema import BusinessConfig
from installer.utils import ui
from installer.validators import domain, non_empty


def run() -> BusinessConfig:
    ui.section("2a — Business", "Tell us about the company this pipeline is for.")

    legal_name = ui.ask_text(
        "Legal company name",
        help_text="e.g. 'Island Advantage Realty LLC' — used on billing / audit docs.",
        validator=non_empty,
    )
    display_name = ui.ask_text(
        "Display name (short)",
        default=_suggest_display_name(legal_name),
        help_text="Used as a prefix for bucket names, SA names, labels. "
                  "Lowercase letters, digits and hyphens only.",
        validator=_normalize_display_name,
    )
    dom = ui.ask_text(
        "Primary domain",
        help_text="e.g. example.com — the business domain, not your personal email.",
        validator=domain,
    )
    industry = ui.ask_select(
        "Industry / vertical",
        choices=[
            "real-estate",
            "construction",
            "legal",
            "healthcare",
            "financial-services",
            "manufacturing",
            "retail",
            "hospitality",
            "professional-services",
            "non-profit",
            "education",
            "other",
        ],
        default="other",
    )

    return BusinessConfig(
        legal_name=legal_name,
        display_name=display_name,
        domain=dom,
        industry=industry,
        country="US",  # static — override in config.yaml if needed
    )


def _suggest_display_name(legal: str) -> str:
    """Turn 'Madison Ave Construction LLC' into 'madison-ave-construction'."""
    import re
    s = legal.lower()
    for suffix in (" llc", " l.l.c.", " inc", " inc.", " co.", " co",
                   " corp", " corp.", " corporation", " ltd", " ltd."):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:30] or "client"


def _normalize_display_name(v: str) -> str:
    import re
    v = v.strip().lower()
    if not re.match(r"^[a-z0-9\-]{2,30}$", v):
        from installer.validators import ValidationError
        raise ValidationError(
            "Display name must be 2–30 chars, lowercase letters, digits, hyphens only."
        )
    return v
