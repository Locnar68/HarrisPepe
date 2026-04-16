"""Search Engine — ensure it exists, attached to the Data Store."""
from __future__ import annotations

from google.api_core import exceptions as gax

from core import engine_client
from core.config import Config


def ensure_engine(cfg: Config, log=print) -> None:
    from google.cloud import discoveryengine_v1 as de

    client = engine_client(cfg)
    try:
        client.get_engine(name=cfg.engine_name)
        log(f"  [skip] engine {cfg.engine_id} (already exists)")
        return
    except gax.NotFound:
        pass

    search_config = de.Engine.SearchEngineConfig(
        search_tier=getattr(de.SearchTier, cfg.search_tier),
        search_add_ons=[getattr(de.SearchAddOn, a) for a in cfg.search_add_ons],
    )
    engine = de.Engine(
        display_name=cfg.engine_display_name,
        solution_type=de.SolutionType.SOLUTION_TYPE_SEARCH,
        industry_vertical=getattr(de.IndustryVertical, cfg.industry_vertical),
        data_store_ids=[cfg.data_store_id],
        search_engine_config=search_config,
    )
    log(f"  [...] creating engine {cfg.engine_id}")
    op = client.create_engine(
        parent=cfg.collection_parent,
        engine=engine,
        engine_id=cfg.engine_id,
    )
    op.result(timeout=600)
    log(f"  [ok]   {cfg.engine_id}")
