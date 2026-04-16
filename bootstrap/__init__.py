"""Bootstrap — idempotent creation of the GCP resources the pipeline needs.

Every function in this package checks "does it exist?" first and returns
cleanly if so. Safe to run repeatedly.
"""
from .apis import enable_apis, REQUIRED_APIS
from .iam import ensure_service_account, grant_project_roles, create_key_if_missing
from .bucket import ensure_bucket
from .data_store import ensure_data_store
from .engine import ensure_engine

__all__ = [
    "enable_apis",
    "REQUIRED_APIS",
    "ensure_service_account",
    "grant_project_roles",
    "create_key_if_missing",
    "ensure_bucket",
    "ensure_data_store",
    "ensure_engine",
]
