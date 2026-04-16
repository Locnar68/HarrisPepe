"""Register filterable metadata fields on the Data Store schema."""
from __future__ import annotations

from google.api_core import exceptions as gax
from core import schema_client
from core.config import Config

STRUCT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "property":  {"type": "string", "retrievable": True, "indexable": True, "dynamicFacetable": True, "searchable": True},
        "category":  {"type": "string", "retrievable": True, "indexable": True, "dynamicFacetable": True, "searchable": True},
        "doc_type":  {"type": "string", "retrievable": True, "indexable": True, "dynamicFacetable": True, "searchable": True},
        "filename":  {"type": "string", "retrievable": True, "searchable": True},
        "subpath":   {"type": "string", "retrievable": True},
        "updated":   {"type": "string", "retrievable": True},
    },
}


def ensure_schema(cfg: Config, log=print) -> None:
    from google.cloud import discoveryengine_v1 as de

    client = schema_client(cfg)
    schema_name = f"{cfg.data_store_name}/schemas/default_schema"

    schema_obj = de.Schema(name=schema_name, struct_schema=STRUCT_SCHEMA)

    try:
        log("  [...] updating data store schema (filterable metadata fields)")
        request = de.UpdateSchemaRequest(schema=schema_obj)
        op = client.update_schema(request=request)
        op.result(timeout=300)
        log("  [ok]   schema updated — property, doc_type, category are now filterable")
    except gax.NotFound:
        log("  [...] creating data store schema")
        request = de.CreateSchemaRequest(
            parent=cfg.data_store_name,
            schema=schema_obj,
            schema_id="default_schema",
        )
        op = client.create_schema(request=request)
        op.result(timeout=300)
        log("  [ok]   schema created")
    except gax.AlreadyExists:
        log("  [ok]   schema already exists")
