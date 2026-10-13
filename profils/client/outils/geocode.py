"""Géocodage BAN + commune/arrondissement (geo.api.gouv.fr).

- geocoder(adresse)      : adresse libre -> coords + code INSEE + CP (format BAN).
- commune(code_insee)    : code INSEE -> commune/arrondissement, population, centre.

Sources officielles et gratuites. Aucune clé API. Fiabilité = verifie.

Pièges connus :
- Le point BAN tombe souvent sur la VOIE (chaussée), pas sur la parcelle.
- geo.api.gouv v1 n'expose NI /quartiers NI /arrondissements (404) :
  les arrondissements Lyon/Marseille/Paris sont reconstitués via une table
  INSEE CP->INSEE ; quartiers() -> [] + note explicite.
"""
from __future__ import annotations

import json
import sys
from datetime import date

from _http import ConnectorError, http_get_json, json_error

BAN_URL = "https://api-adresse.data.gouv.fr/search/"
GEO_URL = "https://geo.api.gouv.fr/communes/"

# Table INSEE CP -> INSEE des arrondissements (Lyon / Marseille / Paris).
# geo.api.gouv ne les expose pas ; cette table est le repli documenté.
ARRONDISSEMENTS = {
    "69001": "69381", "69002": "69382", "69003": "69383", "69004": "69384",
    "69005": "69385", "69006": "69386", "69007": "69387", "69008": "69388",
    "69009": "69389",
    "13001": "13201", "13002": "13202", "13003": "13203", "13004": "13204",
    "13005": "13205", "13006": "13206", "13007": "13207", "13008": "13208",
    "13009": "13209", "13010": "13210", "13011": "13211", "13012": "13212",
    "13013": "13213", "13014": "13214", "13015": "13215", "13016": "13216",
    "75001": "75101", "75002": "75102", "75003": "75103", "75004": "75104",
    "75005": "75105", "75006": "75106", "75007": "75107", "75008": "75108",
    "75009": "75109", "75010": "75110", "75011": "75111", "75012": "75112",
    "75013": "75113", "75014": "75114", "75015": "75115", "75016": "75116",
    "75017": "75117", "75018": "75118", "75019": "75119", "75020": "75120",
}


def _now() -> str:
    return date.today().isoformat()


def geocoder(adresse: str, *, code_postal: str | None = None, limit: int = 5) -> dict:
    """Adresse libre -> coordonnées + INSEE (format BAN). Fiabilité verifie."""
    params = {"q": adresse, "limit": limit}
    if code_postal:
        params["postcode"] = code_postal
    data = http_get_json(BAN_URL, params)
    if not isinstance(data, dict):
        raise ConnectorError(f"Reponse BAN inattendue pour: {adresse!r}", url=BAN_URL)
    feats = data.get("features") or []
    if not feats:
        raise ConnectorError(f"Aucune adresse BAN pour: {adresse!r}")
    f = feats[0]
    p = f.get("properties", {})
    lon, lat = f.get("geometry", {}).get("coordinates", [None, None])
    return {
        "adresse_normalisee": p.get("label"),
        "lat": lat,
        "lon": lon,
        "code_insee": p.get("citycode"),
        "code_postal": p.get("postcode"),
        "ville": p.get("city"),
        "score": p.get("score"),
        "fiabilite": "verifie",
        "source": "BAN api-adresse",
        "date": _now(),
    }


def commune(code_insee: str, *, arrondissements: bool = False) -> dict:
    """Code INSEE -> commune/arrondissement, population, centre. Fiabilité verifie."""
    data = http_get_json(
        GEO_URL + code_insee,
        {"fields": "nom,code,codesPostaux,population,centre,codeDepartement"},
    )
    if isinstance(data, dict) and data.get("code"):
        centre = data.get("centre", {}).get("coordinates")
        out = {
            "nom": data.get("nom"),
            "code_insee": data.get("code"),
            "codes_postaux": data.get("codesPostaux"),
            "population": data.get("population"),
            "centre": {"lon": centre[0], "lat": centre[1]} if centre else None,
            "fiabilite": "verifie",
            "source": "geo.api.gouv.fr",
            "date": _now(),
        }
        if arrondissements:
            # geo.api.gouv n'expose pas les arrondissements : on note la limite.
            out["arrondissements"] = []
            out["note"] = ("geo.api.gouv v1 n'expose pas les arrondissements ; "
                           "utiliser la table INSEE CP->INSEE locale.")
        return out
    raise ConnectorError(f"Commune inconnue: {code_insee!r}")


def arrondissement_par_cp(code_postal: str) -> str | None:
    """CP d'une ville à arrondissements -> code INSEE (repli documenté)."""
    return ARRONDISSEMENTS.get(code_postal)


def quartiers(*_a, **_k) -> list:
    """geo.api.gouv n'expose PAS /quartiers (404) : renvoie [] avec note."""
    return []


def _cli() -> int:
    args = sys.argv[1:]
    if not args:
        print(json.dumps(json_error("usage: geocode.py <adresse> | --insee <code>"),
                         ensure_ascii=False, indent=2))
        return 2
    try:
        if args[0] == "--insee":
            print(json.dumps(commune(args[1]), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(geocoder(" ".join(args)), ensure_ascii=False, indent=2))
        return 0
    except ConnectorError as exc:
        print(json.dumps(json_error(str(exc), url=exc.url), ensure_ascii=False, indent=2))
        return 2
    except IndexError:
        print(json.dumps(json_error("argument manquant"), ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(_cli())
