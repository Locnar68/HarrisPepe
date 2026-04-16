"""Vertex AI Search Data Store — ensure it exists, create if missing."""
from __future__ import annotations

from google.api_core import exceptions as gax

from core import data_store_client
from core.config import Config


def ensure_data_store(cfg: Config, log=print) -> None:
    from google.cloud import discoveryengine_v1 as de

    client = data_store_client(cfg)
    try:
        client.get_data_store(name=cfg.data_store_name)
        log(f"  [skip] data store {cfg.data_store_id} (already exists)")
        return
    except gax.NotFound:
        pass

    data_store = de.DataStore(
        display_name=cfg.data_store_display_name,
        industry_vertical=getattr(de.IndustryVertical, cfg.industry_vertical),
        solution_types=[getattr(de.SolutionType, s) for s in cfg.solution_types],
        content_config=getattr(de.DataStore.ContentConfig, cfg.content_config),
    )
    log(f"  [...] creating data store {cfg.data_store_id} (~60s)")
    op = client.create_data_store(
        parent=cfg.collection_parent,
        data_store=data_store,
        data_store_id=cfg.data_store_id,
    )
    op.result(timeout=600)
    log(f"  [ok]   {cfg.data_store_id}")
