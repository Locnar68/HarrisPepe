"""
Input validators.

Every user-supplied string is validated against the official format rules
for its target system (GCP project IDs, bucket names, data store IDs, etc.).
Failures raise ``ValidationError`` with a message the interview UI displays
inline so the user can correct without starting over.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class ValidationError(ValueError):
    """Raised when an input does not meet the required format."""


# ---------------------------------------------------------------------------
# Primitive validators
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def email(value: str) -> str:
    v = (value or "").strip()
    if not _EMAIL_RE.match(v):
        raise ValidationError(f"'{v}' is not a valid email address.")
    return v.lower()


def phone(value: str) -> str:
    """Accepts E.164-ish or common US formats. Strips to digits + leading +."""
    v = (value or "").strip()
    if not v:
        return ""
    cleaned = re.sub(r"[^\d+]", "", v)
    digits = cleaned.lstrip("+")
    if len(digits) < 7 or len(digits) > 15:
        raise ValidationError(
            f"'{v}' does not look like a valid phone number (need 7–15 digits)."
        )
    return cleaned


def non_empty(value: str, *, field_name: str = "value") -> str:
    v = (value or "").strip()
    if not v:
        raise ValidationError(f"{field_name} cannot be empty.")
    return v


def domain(value: str) -> str:
    """Light validator — forbids spaces, requires at least one dot."""
    v = (value or "").strip().lower()
    if not v:
        raise ValidationError("domain cannot be empty.")
    if " " in v or "/" in v:
        raise ValidationError(f"'{v}' is not a valid domain.")
    if "." not in v:
        raise ValidationError(f"'{v}' must contain a dot (e.g. example.com).")
    if not re.match(r"^[a-z0-9.\-]+$", v):
        raise ValidationError(f"'{v}' contains invalid characters.")
    return v


# ---------------------------------------------------------------------------
# GCP-specific validators
# ---------------------------------------------------------------------------

# https://cloud.google.com/resource-manager/docs/creating-managing-projects
_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9\-]{4,28}[a-z0-9]$")


def gcp_project_id(value: str) -> str:
    v = (value or "").strip().lower()
    if not _PROJECT_ID_RE.match(v):
        raise ValidationError(
            f"GCP project ID '{v}' invalid. Rules: 6–30 chars, must start with a "
            "letter, end with letter or digit, only lowercase letters/digits/hyphens."
        )
    return v


# https://cloud.google.com/storage/docs/buckets#naming
_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9._\-]{1,61}[a-z0-9]$")


def gcs_bucket_name(value: str) -> str:
    v = (value or "").strip().lower()
    if not _BUCKET_RE.match(v):
        raise ValidationError(
            f"Bucket name '{v}' invalid. 3–63 chars, start/end with letter or digit, "
            "only lowercase letters/digits/dots/dashes/underscores."
        )
    if ".." in v:
        raise ValidationError("Bucket name cannot contain consecutive dots.")
    if v.startswith("goog") or "google" in v:
        raise ValidationError("Bucket name cannot start with 'goog' or contain 'google'.")
    return v


# Vertex AI Search IDs
_DATA_STORE_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]{1,62}[a-z0-9]$")


def vertex_id(value: str, *, field_name: str = "ID") -> str:
    v = (value or "").strip().lower()
    if not _DATA_STORE_RE.match(v):
        raise ValidationError(
            f"{field_name} '{v}' invalid. 3–64 chars, lowercase letters/digits/"
            "hyphens/underscores only."
        )
    return v


def region(value: str) -> str:
    """Minimal region validator — accepts ``global`` or ``<region>[-<zone>]``."""
    v = (value or "").strip().lower()
    if v == "global":
        return v
    if not re.match(r"^[a-z]+-[a-z]+\d+(-[a-z])?$", v):
        raise ValidationError(
            f"'{v}' does not look like a GCP region (e.g. us-central1, europe-west4)."
        )
    return v


# Service account short name (the part before @)
_SA_RE = re.compile(r"^[a-z][a-z0-9\-]{4,28}[a-z0-9]$")


def sa_short_name(value: str) -> str:
    v = (value or "").strip().lower()
    if not _SA_RE.match(v):
        raise ValidationError(
            f"Service account name '{v}' invalid. 6–30 chars, start with a letter, "
            "end with a letter or digit, only lowercase letters/digits/hyphens."
        )
    return v


# ---------------------------------------------------------------------------
# Collection helper used by the interview UI
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Validator:
    """Binds a validator callable to a descriptive error context."""
    fn: callable
    description: str = ""

    def __call__(self, value: str) -> str:
        return self.fn(value)
