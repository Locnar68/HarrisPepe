"""Config loader. Single source of truth — every module reads from here."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "config.yaml"

load_dotenv(REPO_ROOT / ".env")


@dataclass(frozen=True)
class Config:
    project_id: str
    location: str

    bucket: str
    mirror_prefix: str
    manifest_prefix: str

    sa_email: str | None
    sa_key_path: str | None

    data_store_id: str
    data_store_display_name: str
    industry_vertical: str
    solution_types: list[str]
    content_config: str

    engine_id: str
    engine_display_name: str
    search_tier: str
    search_add_ons: list[str]

    category_folders: dict[str, str]
    properties: list[str]

    connectors: dict[str, dict]            # {"drive": {...}, "gmail": {...}, ...}

    raw: dict[str, Any] = field(repr=False)

    # Resource-name helpers --------------------------------------------------
    @property
    def collection_parent(self) -> str:
        return (
            f"projects/{self.project_id}/locations/{self.location}"
            f"/collections/default_collection"
        )

    @property
    def data_store_name(self) -> str:
        return f"{self.collection_parent}/dataStores/{self.data_store_id}"

    @property
    def branch_name(self) -> str:
        return f"{self.data_store_name}/branches/default_branch"

    @property
    def engine_name(self) -> str:
        return f"{self.collection_parent}/engines/{self.engine_id}"

    @property
    def search_serving_config(self) -> str:
        return f"{self.engine_name}/servingConfigs/default_search"

    # GCS helpers ------------------------------------------------------------
    def gcs_mirror_uri(self) -> str:
        return f"gs://{self.bucket}/{self.mirror_prefix}"

    def gcs_manifest_uri(self, filename: str = "manifest.jsonl") -> str:
        return f"gs://{self.bucket}/{self.manifest_prefix}/{filename}"

    # Connector helpers ------------------------------------------------------
    def enabled_connectors(self) -> list[str]:
        return [n for n, c in self.connectors.items() if c.get("enabled")]

    def connector_cfg(self, name: str) -> dict:
        return self.connectors.get(name, {})


def load_config(path: Path | None = None) -> Config:
    path = path or CONFIG_PATH
    if not path.exists():
        sys.exit(
            f"config file not found: {path}\n"
            "Run .\\install.ps1 to generate one."
        )
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    try:
        cfg = Config(
            project_id=raw["project"]["id"],
            location=raw["project"]["location"],
            bucket=raw["gcs"]["bucket"],
            mirror_prefix=raw["gcs"]["mirror_prefix"].strip("/"),
            manifest_prefix=raw["gcs"]["manifest_prefix"].strip("/"),
            sa_email=(raw.get("service_account") or {}).get("email"),
            sa_key_path=(raw.get("service_account") or {}).get("key_path"),
            data_store_id=raw["data_store"]["id"],
            data_store_display_name=raw["data_store"]["display_name"],
            industry_vertical=raw["data_store"]["industry_vertical"],
            solution_types=raw["data_store"]["solution_types"],
            content_config=raw["data_store"]["content_config"],
            engine_id=raw["engine"]["id"],
            engine_display_name=raw["engine"]["display_name"],
            search_tier=raw["engine"]["search_tier"],
            search_add_ons=raw["engine"]["search_add_ons"],
            category_folders=(raw.get("metadata") or {}).get("category_folders", {}),
            properties=(raw.get("metadata") or {}).get("properties", []) or [],
            connectors=raw.get("connectors") or {},
            raw=raw,
        )
    except KeyError as e:
        sys.exit(f"config.yaml is missing required key: {e}")

    if cfg.location not in {"global", "us", "eu"}:
        sys.exit(f"project.location must be one of global|us|eu, got: {cfg.location!r}")

    env_project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if env_project and env_project != cfg.project_id:
        print(
            f"[warn] config project={cfg.project_id!r} but "
            f"GOOGLE_CLOUD_PROJECT={env_project!r}",
            file=sys.stderr,
        )
    return cfg
