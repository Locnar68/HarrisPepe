"""Metadata — turn GCS paths into searchable tags."""
from .schema import CORE_TAGS, validate
from .extractor import classify

__all__ = ["CORE_TAGS", "validate", "classify"]
