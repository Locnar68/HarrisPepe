"""Client factories for every Google API we touch.

All functions lazy-import so importing core is cheap even if you only
need one backend."""
from __future__ import annotations

from .config import Config


# -------- Discovery Engine --------

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


def search_client(cfg: Config):
    from google.cloud import discoveryengine_v1 as de
    return de.SearchServiceClient(client_options=_de_options(cfg))


def conversational_client(cfg: Config):
    from google.cloud import discoveryengine_v1 as de
    return de.ConversationalSearchServiceClient(client_options=_de_options(cfg))


# -------- Storage --------

def storage_client(cfg: Config):
    from google.cloud import storage
    return storage.Client(project=cfg.project_id)


# -------- Service Usage (for enabling APIs) --------

def service_usage_client():
    from google.cloud import service_usage_v1
    return service_usage_v1.ServiceUsageClient()


# -------- Drive --------

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def drive_service():
    """Build a Drive v3 client with explicit drive.readonly scope.

    Works with either SA key (set GOOGLE_APPLICATION_CREDENTIALS) or user ADC
    that includes the drive scope. For personal Gmail, only the SA path works
    because Google blocks drive.readonly on gcloud's shared OAuth client.
    """
    import google.auth
    from googleapiclient.discovery import build

    creds, _ = google.auth.default(scopes=DRIVE_SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


# -------- Gmail (Phase 2) --------

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def gmail_service():
    """Build a Gmail v1 client. Requires domain-wide delegation when using
    a service account against a Workspace account, or per-user OAuth for
    personal Gmail. See documents/04-CONNECTOR_GUIDE.md."""
    import google.auth
    from googleapiclient.discovery import build

    creds, _ = google.auth.default(scopes=GMAIL_SCOPES)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)
