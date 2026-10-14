"""HTTP helper partagé par tous les outils argus-immo.

Stdlib uniquement (urllib). Gère : timeout, retries, User-Agent honnête, JSON,
gzip, suivi des redirections. Aucune donnée inventée : en cas d'échec, on lève
ConnectorError (erreur claire), jamais un fallback silencieux.
"""
from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "argus-immo-outils/1.0 (contact: argus-outils@noreply.github.com)"
DEFAULT_TIMEOUT = 30


class ConnectorError(RuntimeError):
    """Erreur claire et explicite d'un outil (jamais un crash silencieux)."""

    def __init__(self, message: str, *, url: str | None = None, status: int | None = None):
        self.url = url
        self.status = status
        super().__init__(message)


def http_get_json(url: str, params: dict | None = None, *, timeout: int = DEFAULT_TIMEOUT,
                  retries: int = 2, extra_headers: dict | None = None) -> dict | list:
    """GET JSON avec retries. Lève ConnectorError en cas d'échec définitif."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    raw = http_get_bytes(url, timeout=timeout, retries=retries, extra_headers=extra_headers)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConnectorError(f"Reponse non-JSON depuis {url}: {exc}", url=url) from exc


def http_get_bytes(url: str, *, timeout: int = DEFAULT_TIMEOUT, retries: int = 2,
                   extra_headers: dict | None = None) -> bytes:
    """GET brut (bytes), gère gzip + redirections. Retries avec backoff sur réseau/5xx."""
    headers = {"User-Agent": UA, "Accept-Encoding": "gzip"}
    if extra_headers:
        headers.update(extra_headers)

    last: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as exc:
            # 404 = ressource absente (inutile de retenter). 429/5xx = on retente.
            if exc.code == 404:
                raise ConnectorError(f"HTTP 404 sur {url}", url=url, status=404) from exc
            last = ConnectorError(f"HTTP {exc.code} sur {url}", url=url, status=exc.code)
            if exc.code < 500 and exc.code != 429:
                raise last
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = ConnectorError(f"Erreur reseau sur {url}: {exc}", url=url)

        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))

    assert last is not None
    raise last


def json_error(erreur: str, *, url: str | None = None, etape: str | None = None) -> dict:
    """Enveloppe d'erreur CLI : JSON propre, jamais une trace Python brute."""
    out: dict = {"erreur": erreur}
    if url:
        out["url"] = url
    if etape:
        out["etape"] = etape
    return out
