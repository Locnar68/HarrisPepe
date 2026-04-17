"""
REST helpers for Google APIs.

Important patterns enforced here (all from Phase 1/2 POC learnings):

* Every request carries ``Authorization: Bearer <access-token>`` from
  ``gcloud auth print-access-token``.
* Every request also sets ``X-Goog-User-Project`` — required for some services
  (notably Discovery Engine) when using user credentials.
* ``poll_operation()`` treats a 404 during polling as *success* — Google's
  LRO records are garbage-collected after the operation completes and the
  SDK sometimes catches the 404 during the final poll.
* All Vertex AI Search / Discovery Engine calls must use the ``v1alpha``
  endpoint when ``documentProcessingConfig`` is involved (Layout Parser).
* 5xx errors are retried with exponential backoff (max 3 retries).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import requests

from installer.utils.shell import run as sh_run

log = logging.getLogger(__name__)

DEFAULT_DISCOVERY_HOST = "https://discoveryengine.googleapis.com"
DEFAULT_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

_token_cache: dict[str, tuple[str, float]] = {}
_TOKEN_TTL_SEC = 50 * 60  # gcloud access tokens last ~1h; refresh at 50min


def get_access_token() -> str:
    """Return a current access token from ``gcloud auth print-access-token``."""
    cached = _token_cache.get("token")
    if cached and cached[1] > time.time():
        return cached[0]
    result = sh_run(["gcloud", "auth", "print-access-token"], timeout=30)
    tok = result.stdout.strip()
    if not tok:
        raise RuntimeError(
            "gcloud returned an empty access token. "
            "Run `gcloud auth login` and try again."
        )
    _token_cache["token"] = (tok, time.time() + _TOKEN_TTL_SEC)
    return tok


# ---------------------------------------------------------------------------
# Base request
# ---------------------------------------------------------------------------

def _headers(project_id: Optional[str], extra: Optional[dict] = None) -> dict:
    h = {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
    }
    if project_id:
        h["X-Goog-User-Project"] = project_id
    if extra:
        h.update(extra)
    return h


def request(
    method: str,
    url: str,
    *,
    project_id: Optional[str] = None,
    json_body: Any = None,
    params: Optional[dict] = None,
    timeout: int = DEFAULT_TIMEOUT,
    extra_headers: Optional[dict] = None,
    expected_ok: tuple[int, ...] = (200, 201),
    allow_404: bool = False,
) -> requests.Response:
    """Perform an HTTP request against a Google API with automatic retry on 5xx.

    Args:
        allow_404: if True, a 404 is returned without raising. Use for the
            "resource exists?" check pattern (GET first, create if 404).
    
    Retries up to MAX_RETRIES times on 5xx errors with exponential backoff.
    """
    headers = _headers(project_id, extra_headers)
    
    for attempt in range(MAX_RETRIES + 1):
        log.debug("%s %s (attempt %d/%d)", method, url, attempt + 1, MAX_RETRIES + 1)
        
        resp = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=json_body,
            params=params,
            timeout=timeout,
        )
        
        # Handle 404 if allowed
        if resp.status_code == 404 and allow_404:
            return resp
        
        # Success case
        if resp.status_code in expected_ok:
            return resp
        
        # Retry on 5xx errors (server-side transient issues)
        if 500 <= resp.status_code < 600 and attempt < MAX_RETRIES:
            backoff = RETRY_BACKOFF_BASE ** attempt
            try:
                body = resp.json()
            except Exception:  # noqa: BLE001
                body = resp.text
            
            log.warning(
                "HTTP %s for %s %s: %s — retrying in %ss (attempt %d/%d)",
                resp.status_code, method, url, body, backoff, attempt + 1, MAX_RETRIES
            )
            time.sleep(backoff)
            continue
        
        # Non-retryable error or exhausted retries
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            body = resp.text
        
        log.error("HTTP %s for %s %s: %s", resp.status_code, method, url, body)
        resp.raise_for_status()
    
    # Should never reach here, but for type safety
    raise RuntimeError(f"Request to {url} failed after {MAX_RETRIES} retries")


# ---------------------------------------------------------------------------
# Long-running operation polling (with 404=success handling)
# ---------------------------------------------------------------------------

def poll_operation(
    op_name: str,
    *,
    project_id: str,
    host: str = DEFAULT_DISCOVERY_HOST,
    api_version: str = "v1alpha",
    interval_sec: int = 5,
    timeout_sec: int = 1800,
) -> dict:
    """Poll a long-running operation until it completes.

    Handles the POC lesson: a 404 during polling is NOT an error. It means
    the operation record was garbage-collected after success.
    """
    url = f"{host}/{api_version}/{op_name}"
    started = time.time()
    while True:
        if time.time() - started > timeout_sec:
            raise TimeoutError(f"Operation {op_name} did not complete within "
                               f"{timeout_sec}s.")
        try:
            resp = request("GET", url, project_id=project_id, allow_404=True)
        except requests.HTTPError as e:
            # Some transient 5xx — back off and retry
            log.warning("Operation poll transient error: %s — retrying", e)
            time.sleep(interval_sec)
            continue

        if resp.status_code == 404:
            log.info("Operation %s returned 404 — treating as success "
                     "(LRO record garbage-collected).", op_name)
            return {"done": True, "implicit_success": True}

        body = resp.json()
        if body.get("done"):
            if "error" in body:
                raise RuntimeError(f"Operation {op_name} failed: {body['error']}")
            return body

        log.debug("Operation %s not done; sleeping %ss", op_name, interval_sec)
        time.sleep(interval_sec)


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

def get(url: str, **kwargs) -> requests.Response:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs) -> requests.Response:
    return request("POST", url, **kwargs)


def patch(url: str, **kwargs) -> requests.Response:
    return request("PATCH", url, **kwargs)


def delete(url: str, **kwargs) -> requests.Response:
    return request("DELETE", url, expected_ok=(200, 204), **kwargs)
