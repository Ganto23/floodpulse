"""Small HTTP helper with an on-disk JSON cache so demo restarts are instant."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

import requests

from config import CACHE_DIR, HTTP_TIMEOUT_S, USER_AGENT

log = logging.getLogger(__name__)


def _cache_path(namespace: str, key: str):
    digest = hashlib.sha256(key.encode()).hexdigest()[:20]
    return CACHE_DIR / f"{namespace}_{digest}.json"


def cached_request(
    namespace: str,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    retries: int = 2,
) -> tuple[Any, bool]:
    """
    Perform a request, caching the JSON body.

    Returns (payload, from_cache). Raises requests.RequestException if the
    network call fails and nothing is cached.
    """
    key = json.dumps({"m": method, "u": url, "p": params, "d": data}, sort_keys=True)
    path = _cache_path(namespace, key)
    if path.exists():
        try:
            return json.loads(path.read_text()), True
        except json.JSONDecodeError:
            path.unlink(missing_ok=True)

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.request(
                method, url, params=params, data=data,
                timeout=HTTP_TIMEOUT_S, headers={"User-Agent": USER_AGENT},
            )
            if resp.status_code in (429, 502, 503, 504) and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            payload = resp.json()
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload))
            return payload, False
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            log.warning("%s request failed (attempt %d): %s", namespace, attempt + 1, exc)
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    assert last_exc is not None
    raise last_exc
