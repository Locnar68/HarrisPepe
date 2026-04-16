"""Path → metadata extractor.

Two classification strategies, tried in order:

  1. STRICT — expects `<mirror_prefix>/Properties/<property>/<category>/...`.
     Deterministic; preferred when the source is well-organized.

  2. HEURISTIC — filename regex → tag rules from config.yaml.
     Fallback for flat/messy folders. Enable with metadata.heuristic_classification.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

from core.config import Config

_NN_PREFIX = re.compile(r"^\d{1,3}-")


def classify_strict(cfg: Config, gcs_path: str) -> dict | None:
    """Tag from the canonical `<prefix>/Properties/<property>/<category>/...` layout."""
    p = PurePosixPath(gcs_path)
    parts = p.parts
    if len(parts) < 5:
        return None
    if parts[0] != cfg.mirror_prefix or parts[1] != "Properties":
        return None

    property_folder = parts[2]
    category_folder = parts[3]
    filename = parts[-1]
    subpath = "/".join(parts[4:-1])

    doc_type = cfg.category_folders.get(category_folder)
    if doc_type is None:
        return None

    category = _NN_PREFIX.sub("", category_folder)
    return {
        "property": property_folder,
        "category": category,
        "doc_type": doc_type,
        "subpath":  subpath,
        "filename": filename,
    }


def classify_heuristic(cfg: Config, gcs_path: str) -> dict | None:
    """Tag by filename pattern. Rules and default_property come from config.yaml.

    Each rule is `{pattern: <regex>, doc_type: <str>, property: <str (optional)>}`.
    Case-insensitive. First match wins.
    """
    md = cfg.raw.get("metadata", {}) or {}
    if not md.get("heuristic_classification"):
        return None

    rules = md.get("heuristic_rules", []) or []
    default_property = md.get("default_property")

    filename = PurePosixPath(gcs_path).name
    matched_property = default_property
    doc_type = None

    for rule in rules:
        pattern = rule.get("pattern", "")
        if not pattern:
            continue
        if re.search(pattern, filename, re.IGNORECASE):
            doc_type = rule.get("doc_type") or doc_type
            if rule.get("property"):
                matched_property = rule["property"]
            break

    if doc_type is None or matched_property is None:
        return None

    return {
        "property": matched_property,
        "category": doc_type.title(),
        "doc_type": doc_type,
        "subpath":  "",
        "filename": filename,
    }


def classify(cfg: Config, gcs_path: str) -> dict | None:
    """Try strict first, fall back to heuristic if configured."""
    tags = classify_strict(cfg, gcs_path)
    if tags is not None:
        return tags
    return classify_heuristic(cfg, gcs_path)
