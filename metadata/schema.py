"""Metadata schema — what tags are allowed on a document."""
from __future__ import annotations

CORE_TAGS = {
    "property":  "Property/entity folder name, e.g. '15-Northridge'",
    "category":  "Category name with NN- prefix stripped, e.g. 'Permits'",
    "doc_type":  "legal | finance | permit | billing | image | email | document",
    "source":    "drive | gmail | onedrive | local_files | csv",
    "subpath":   "Any subfolders under the category folder",
    "filename":  "Basename of the original file",
    "updated":   "ISO timestamp of last modification at source",
}

VALID_DOC_TYPES = {"legal", "finance", "permit", "billing", "image", "email", "document"}


def validate(tags: dict) -> list[str]:
    warnings: list[str] = []
    for req in ("property", "category", "doc_type", "filename"):
        if req not in tags:
            warnings.append(f"missing required tag: {req}")
    if "doc_type" in tags and tags["doc_type"] not in VALID_DOC_TYPES:
        warnings.append(f"unknown doc_type: {tags['doc_type']}")
    return warnings
