"""
Pydantic v2 schema for the Phase 3 bootstrap configuration.

The interview builds one of these incrementally; once complete, it is
serialized to ``config/config.yaml``. Every downstream step reads from this
object — no stringly-typed dicts, no magic keys.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from installer import validators as V


# =============================================================================
# Business
# =============================================================================

class BusinessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    legal_name: str = Field(..., description="Legal registered name")
    display_name: str = Field(..., description="Short name used in UIs/labels")
    domain: str = Field(..., description="Primary domain, e.g. example.com")
    industry: str = Field("general", description="Industry / vertical")
    country: str = Field("US", description="ISO 3166-1 alpha-2 country code")

    @field_validator("domain")
    @classmethod
    def _v_domain(cls, v: str) -> str:
        return V.domain(v)


# =============================================================================
# Contact
# =============================================================================

class ContactConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str
    email: str
    phone: str = ""
    role: str = "Owner"

    @field_validator("email")
    @classmethod
    def _v_email(cls, v: str) -> str:
        return V.email(v)

    @field_validator("phone")
    @classmethod
    def _v_phone(cls, v: str) -> str:
        return V.phone(v) if v else ""


# =============================================================================
# GCP
# =============================================================================

class GCPConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    project_number: Optional[str] = None      # populated after project creation
    project_exists: bool = False              # True if reusing an existing project
    organization_id: Optional[str] = None     # optional, for orgs
    folder_id: Optional[str] = None           # optional, for folder-based hierarchies
    billing_account_id: Optional[str] = None  # "XXXXXX-XXXXXX-XXXXXX"
    region: str = "us-central1"
    location: str = "global"                  # for data store; "global" is only valid value today

    @field_validator("project_id")
    @classmethod
    def _v_project(cls, v: str) -> str:
        return V.gcp_project_id(v)

    @field_validator("region")
    @classmethod
    def _v_region(cls, v: str) -> str:
        return V.region(v)


# =============================================================================
# Service account
# =============================================================================

class ServiceAccountConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    short_name: str = Field(..., description="Part before @ in SA email")
    display_name: str = "Phase 3 Bootstrap SA"
    email: Optional[str] = None              # populated after creation
    key_path: Optional[str] = None           # local path to JSON key
    roles: list[str] = Field(default_factory=lambda: [
        "roles/storage.admin",
        "roles/discoveryengine.admin",
        "roles/secretmanager.secretAccessor",
        "roles/aiplatform.user",
        "roles/run.invoker",
        "roles/cloudscheduler.admin",
        "roles/logging.logWriter",
    ])

    @field_validator("short_name")
    @classmethod
    def _v_short(cls, v: str) -> str:
        return V.sa_short_name(v)


# =============================================================================
# Storage
# =============================================================================

class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_bucket: str
    processed_bucket: str
    archive_bucket: str = ""                  # optional
    storage_class: Literal["STANDARD", "NEARLINE", "COLDLINE", "ARCHIVE"] = "STANDARD"
    lifecycle_days_to_archive: int = 0        # 0 = disabled

    @field_validator("raw_bucket", "processed_bucket")
    @classmethod
    def _v_required_bucket(cls, v: str) -> str:
        return V.gcs_bucket_name(v)

    @field_validator("archive_bucket")
    @classmethod
    def _v_optional_bucket(cls, v: str) -> str:
        return V.gcs_bucket_name(v) if v else ""


# =============================================================================
# Vertex AI Search
# =============================================================================

VERTEX_TIER = Literal["STANDARD", "ENTERPRISE"]
CONTENT_CONFIG = Literal["NO_CONTENT", "CONTENT_REQUIRED", "PUBLIC_WEBSITE"]
INDUSTRY_VERTICAL = Literal["GENERIC", "MEDIA", "HEALTHCARE_FHIR"]


class VertexConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_store_id: str
    engine_id: str
    collection: str = "default_collection"
    tier: VERTEX_TIER = "ENTERPRISE"
    content_config: CONTENT_CONFIG = "CONTENT_REQUIRED"
    industry_vertical: INDUSTRY_VERTICAL = "GENERIC"
    language_code: str = "en"

    # Layout Parser — MUST be set at creation time per POC learnings
    enable_layout_parser: bool = True
    layout_parser_types: list[str] = Field(default_factory=lambda: [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/html",
    ])

    # Advanced answer features require Enterprise tier
    enable_advanced_site_search: bool = False

    @field_validator("data_store_id")
    @classmethod
    def _v_ds(cls, v: str) -> str:
        return V.vertex_id(v, field_name="data store ID")

    @field_validator("engine_id")
    @classmethod
    def _v_engine(cls, v: str) -> str:
        return V.vertex_id(v, field_name="engine ID")


# =============================================================================
# Connectors
# =============================================================================

class ConnectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["gmail", "gdrive", "onedrive", "sql", "fileshare"]
    enabled: bool = False
    options: dict[str, Any] = Field(default_factory=dict)
    schedule_cron: str = "0 */6 * * *"  # default every 6 hours
    secret_refs: dict[str, str] = Field(default_factory=dict)


# =============================================================================
# Paths (where on disk to put things)
# =============================================================================

class PathsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    install_path: str                                 # absolute path (set at runtime)
    config_dir: str = "config"
    secrets_dir: str = "secrets"
    state_dir: str = "state"
    logs_dir: str = "logs"


# =============================================================================
# Top-level
# =============================================================================

class Phase3Config(BaseModel):
    """Root config model."""
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "3.0"

    business: BusinessConfig
    contact: ContactConfig
    gcp: GCPConfig
    service_account: ServiceAccountConfig
    storage: StorageConfig
    vertex: VertexConfig
    connectors: list[ConnectorConfig]
    paths: PathsConfig

    # --- Helpers -----------------------------------------------------------

    def connector(self, name: str) -> Optional[ConnectorConfig]:
        """Return the connector config with the given name, or None."""
        for c in self.connectors:
            if c.name == name:
                return c
        return None

    def serving_config_path(self) -> str:
        """Full serving config path for /v1alpha/.../search."""
        pn = self.gcp.project_number or self.gcp.project_id
        return (
            f"projects/{pn}/locations/{self.gcp.location}"
            f"/collections/{self.vertex.collection}"
            f"/engines/{self.vertex.engine_id}"
            f"/servingConfigs/default_search"
        )

    def data_store_parent(self) -> str:
        pn = self.gcp.project_number or self.gcp.project_id
        return (
            f"projects/{pn}/locations/{self.gcp.location}"
            f"/collections/{self.vertex.collection}"
        )

    def data_store_path(self) -> str:
        return f"{self.data_store_parent()}/dataStores/{self.vertex.data_store_id}"
