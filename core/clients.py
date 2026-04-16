"""Client factories for every Google API we touch."""
from __future__ import annotations

from .config import Config


def _de_options(cfg: Config):
    from google.api_core.client_options import ClientOptions
    if cfg.location == "global":
        return None
    return ClientOptions(api_endpoint=f"{cfg.location}-discoveryengine.googleapis.com")


def data_store_client(cfg: Config):
    from google.cloud import discoveryengine_v1 as de
    return de.DataStoreServiceClient(client_options=_de_options(cfg))


def document_client(cfg: Config):
    from google.cloud import discoveryengine_v1 as de
    return de.DocumentServiceClient(client_options=_de_options(cfg))


def engine_client(cfg: Config):
    from google.cloud import discoveryengine_v1 as de
    return de.EngineServiceClient(client_options=_de_options(cfg))


def schema_client(cfg: Config):
    from google.cloud import discoveryengine_v1 as de
    return de.SchemaServiceClient(client_options=_de_options(cfg))


def search_client(cfg: Config):
    from google.cloud import discoveryengine_v1 as de
    return de.SearchServiceClient(client_options=_de_options(cfg))


def conversational_client(cfg: Config):
    from google.cloud import discoveryengine_v1 as de
    return de.ConversationalSearchServiceClient(client_options=_de_options(cfg))


def storage_client(cfg: Config):
    from google.cloud import storage
    return storage.Client(project=cfg.project_id)


def service_usage_client():
    from google.cloud import service_usage_v1
    return service_usage_v1.ServiceUsageClient()


DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def drive_service():
    """Build a Drive v3 client with explicit drive.readonly scope."""
    import google.auth
    from googleapiclient.discovery import build
    creds, _ = google.auth.default(scopes=DRIVE_SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def gmail_service():
    """Build a Gmail v1 client (Phase 2 stub)."""
    import google.auth
    from googleapiclient.discovery import build
    creds, _ = google.auth.default(scopes=GMAIL_SCOPES)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)
