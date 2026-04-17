"""Unit tests for installer.config.schema + installer.gcp.data_store._bump_suffix."""

from __future__ import annotations

from installer.config.schema import (
    BusinessConfig, ContactConfig, GCPConfig, ServiceAccountConfig,
    StorageConfig, VertexConfig, ConnectorConfig, PathsConfig, Phase3Config,
)
from installer.gcp.data_store import _bump_suffix


def _minimal_cfg() -> Phase3Config:
    return Phase3Config(
        business=BusinessConfig(
            legal_name="Test LLC",
            display_name="test-co",
            domain="test.com",
            industry="other",
            country="US",
        ),
        contact=ContactConfig(
            full_name="Test User",
            email="user@test.com",
        ),
        gcp=GCPConfig(
            project_id="test-project-1",
            project_number="123456789",
            region="us-central1",
        ),
        service_account=ServiceAccountConfig(
            short_name="test-co-rag-sa",
            email="test-co-rag-sa@test-project-1.iam.gserviceaccount.com",
        ),
        storage=StorageConfig(
            raw_bucket="test-co-rag-raw",
            processed_bucket="test-co-rag-processed",
        ),
        vertex=VertexConfig(
            data_store_id="test-co-ds-v1",
            engine_id="test-co-engine-v1",
        ),
        connectors=[
            ConnectorConfig(name="gmail", enabled=False),
            ConnectorConfig(name="gdrive", enabled=False),
        ],
        paths=PathsConfig(install_path="/tmp/test"),
    )


def test_minimal_config_builds():
    cfg = _minimal_cfg()
    assert cfg.business.display_name == "test-co"


def test_serving_config_path_uses_project_number():
    cfg = _minimal_cfg()
    path = cfg.serving_config_path()
    assert "projects/123456789/" in path
    assert "/engines/test-co-engine-v1/servingConfigs/default_search" in path


def test_data_store_path_shape():
    cfg = _minimal_cfg()
    path = cfg.data_store_path()
    assert path.endswith("/dataStores/test-co-ds-v1")
    assert "/collections/default_collection" in path


def test_connector_lookup():
    cfg = _minimal_cfg()
    assert cfg.connector("gmail") is not None
    assert cfg.connector("nonexistent") is None


def test_round_trip_yaml(tmp_path):
    from installer.config.loader import load_config, save_config
    cfg1 = _minimal_cfg()
    path = tmp_path / "cfg.yaml"
    save_config(cfg1, path)
    cfg2 = load_config(path)
    assert cfg2.business.legal_name == cfg1.business.legal_name
    assert cfg2.vertex.data_store_id == cfg1.vertex.data_store_id


# --- _bump_suffix --------------------------------------------------------

class TestBumpSuffix:
    def test_existing_v1_bumps_to_v2(self):
        assert _bump_suffix("foo-ds-v1", attempt=1) == "foo-ds-v2"

    def test_existing_v2_bumps_to_v3(self):
        assert _bump_suffix("foo-ds-v2", attempt=1) == "foo-ds-v3"

    def test_no_version_appends_v2(self):
        assert _bump_suffix("foo-ds", attempt=1) == "foo-ds-v2"

    def test_multiple_attempts(self):
        assert _bump_suffix("foo-ds-v1", attempt=3) == "foo-ds-v4"
