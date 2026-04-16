"""Metadata schema — what tags are allowed on a document.

Keep this list short. Every new tag here must:
  - be populated by the extractor
  - be queryable via filters (--property, --doc-type, etc.) once schema is registered
  - be documented in documents/05-METADATA_SCHEMA.md
"""
from __future__ import annotations

CORE_TAGS = {
    "property":  "Property/entity folder name, e.g. '15-Northridge'",
    "category":  "Category name with NN- prefix stripped, e.g. 'Permits'",
    "doc_type":  "legal | finance | permit | billing | image | document",
    "source":    "drive | gmail | onedrive | local_files | csv",
    "subpath":   "Any subfolders under the category folder",
    "filename":  "Basename of the original file",
    "updated":   "ISO timestamp of last modification at source",
}

VALID_DOC_TYPES = {"legal", "finance", "permit", "billing", "image", "document"}


def validate(tags: dict) -> list[str]:
    """Return a list of human-readable validation warnings (empty = clean)."""
    warnings: list[str] = []
    for req in ("property", "category", "doc_type", "filename"):
        if req not in tags:
            warnings.append(f"missing required tag: {req}")
    if "doc_type" in tags and tags["doc_type"] not in VALID_DOC_TYPES:
        warnings.append(f"unknown doc_type: {tags['doc_type']}")
    return warnings
