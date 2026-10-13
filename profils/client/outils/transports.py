"""Transports — distance d'un point aux arrêts TCL via OpenStreetMap (Overpass).

POURQUOI CET OUTIL EXISTE
-------------------------
Lors d'une session de test réelle, l'IA client a voulu calculer les distances
aux transports et a **tâtonné sans fin** (Overpass saturé -> Wikipedia ->
Nominatim, station par station) : jamais de borne, stream bloqué >10 min.
Ce besoin est simple et déterministe : il doit être du Python pur, pas du LLM.

Ce module rend, en UN appel borné, les arrêts de transport les plus proches
d'un point (métro, tram, bus), triés par distance, avec le nom et la ligne
quand disponibles. En cas d'échec, il lève ConnectorError (échec propre) —
il NE boucle PAS et NE devine rien.

Source : OpenStreetMap via Overpass API (open data, ODbL). Plusieurs miroirs,
retry borné, cache disque. Aucune clé requise.

LIMITE ASSUMÉE : la distance est à vol d'oiseau (distance réelle non
calculée). Marquer « approximatif » côté rédaction.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

UA = "argus-immo-outils/1.0 (contact: momomld904@gmail.com)"
DEFAULT_TIMEOUT = 25

# Miroirs Overpass (essayés dans l'ordre ; le premier sature souvent).
MIROIRS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://map.osm-osmose.de/api/interpreter",
)

CACHE_DIR = os.environ.get("TRANSPORTS_CACHE_DIR", "/tmp/argus-immo-transports-cache")


class ConnectorError(RuntimeError):
    """Erreur claire et explicite d'un outil (jamais un crash silencieux)."""

    def __init__(self, message: str, *, url: str | None = None, status: int | None = None):
        self.url = url
        self.status = status
        super().__init__(message)


# --- Décodage de la catégorie/ ligne d'un arrêt OSM ---------------------------
def _categorie(tags: dict) -> str:
    if tags.get("railway") == "station" or tags.get("station") == "subway":
        return "métro/fleuve" if tags.get("subway") == "yes" else "métro/rail"
    if tags.get("railway") in ("tram_stop",) or tags.get("tram") == "yes":
        return "tram"
    if tags.get("highway") == "bus_stop":
        return "bus"
    if tags.get("public_transport") == "stop_position":
        return "arrêt"
    return "transport"


def _lignes(tags: dict) -> str | None:
    for cle in ("line", "route_ref", "ref", "network"):
        if tags.get(cle):
            return str(tags[cle])
    return None


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _cache_path(lat: float, lon: float, rayon: int) -> str:
    return os.path.join(CACHE_DIR, f"{lat:.5f}_{lon:.5f}_{rayon}.json")


def _lire_cache(lat: float, lon: float, rayon: int, ttl_s: int) -> dict | None:
    p = _cache_path(lat, lon, rayon)
    try:
        if time.time() - os.path.getmtime(p) < ttl_s:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
    except OSError:
        pass
    return None


def _ecrire_cache(lat: float, lon: float, rayon: int, data: dict) -> None:
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(_cache_path(lat, lon, rayon), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
    except OSError:
        pass


def _requete_overpass(lat: float, lon: float, rayon: int) -> list[dict]:
    """Interroge Overpass (miroirs + retry borné). Lève ConnectorError en échec.

    JAMAIS de boucle : au plus len(MIROIRS) tentatives, une par miroir.
    """
    q = (
        f"[out:json][timeout:{DEFAULT_TIMEOUT}];"
        "("
        f'node(around:{rayon},{lat},{lon})["railway"="station"];'
        f'node(around:{rayon},{lat},{lon})["railway"="tram_stop"];'
        f'node(around:{rayon},{lat},{lon})["highway"="bus_stop"];'
        f'node(around:{rayon},{lat},{lon})["public_transport"="stop_position"];'
        ");"
        "out body 40;"
    )
    data = urllib.parse.urlencode({"data": q}).encode()
    derniere = None
    for miroir in MIROIRS:
        req = urllib.request.Request(miroir, data=data,
                                     headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT + 10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                return payload.get("elements", [])
        except urllib.error.HTTPError as exc:
            derniere = ConnectorError(f"HTTP {exc.code} sur {miroir}", url=miroir, status=exc.code)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            derniere = ConnectorError(f"Échec réseau sur {miroir}: {exc}", url=miroir)
    assert derniere is not None
    raise derniere


def arrets_proches(lat: float, lon: float, *, rayon_m: int = 600,
                   limite: int = 5, ttl_cache_s: int = 86400) -> dict:
    """Arrêts de transport les plus proches d'un point.

    lat/lon    : coordonnées du bien (ex. depuis geocode.py ou Bien'ici).
    rayon_m    : rayon de recherche (défaut 600 m).
    limite     : nb d'arrêts rendus (défaut 5).
    Retour (enveloppe §4.1) : resultat.arrets = [{nom, categorie, lignes,
      distance_m, lat, lon}] triés par distance, + distance_approximative=True.
    Échec : statut='echec', erreurs=[...] (miroirs injoignables) — pas de boucle.
    """
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ConnectorError(f"Coordonnées invalides: lat={lat}, lon={lon}")

    cache = _lire_cache(lat, lon, rayon_m, ttl_cache_s)
    if cache is not None:
        elements = cache.get("elements", [])
        depuis_cache = True
    else:
        elements = _requete_overpass(lat, lon, rayon_m)
        _ecrire_cache(lat, lon, rayon_m, {"elements": elements})
        depuis_cache = False

    arrets = []
    for e in elements:
        if e.get("type") != "node":
            continue
        tags = e.get("tags", {})
        d = _haversine_m(lat, lon, e["lat"], e["lon"])
        arrets.append({
            "nom": tags.get("name") or "(arrêt sans nom)",
            "categorie": _categorie(tags),
            "lignes": _lignes(tags),
            "distance_m": round(d),
            "lat": e["lat"],
            "lon": e["lon"],
            "source": "OpenStreetMap (Overpass)",
            "fiabilite": "verifie",
        })
    arrets.sort(key=lambda a: a["distance_m"])
    # Dédoublonner : un même arrêt expose plusieurs « nœuds » OSM (quais,
    # stop_position, bus_stop au même endroit). On ne garde que le plus proche
    # par couple (nom, catégorie).
    uniques: list[dict] = []
    vus: set[tuple[str, str]] = set()
    for a in arrets:
        cle = (a["nom"], a["categorie"])
        if cle in vus:
            continue
        vus.add(cle)
        uniques.append(a)
    arrets = uniques[:limite]

    return {
        "tache": "transports",
        "statut": "ok",
        "entree": {"lat": lat, "lon": lon, "rayon_m": rayon_m, "limite": limite},
        "resultat": {
            "arrets": arrets,
            "nb_arrets": len(arrets),
            "distance_approximative": True,
            "note": "Distance à vol d'oiseau (pas de calcul d'itinéraire). "
                    "Marquer « approximatif ». En cas de 0 arrêt, élargir le rayon.",
            "depuis_cache": depuis_cache,
        },
        "sources": ["OpenStreetMap (Overpass API, ODbL)"],
        "erreurs": [],
        "date": date.today().isoformat(),
    }


def _main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Arrêts de transport les plus proches (OSM/Overpass).")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--rayon", type=int, default=600)
    ap.add_argument("--limite", type=int, default=5)
    ap.add_argument("--adresse", help="adresse → géocodée via geocode.py (prioritaire sur lat/lon)")
    args = ap.parse_args(argv)

    lat, lon = args.lat, args.lon
    if args.adresse:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from geocode import geocoder  # noqa: E402
            g = geocoder(args.adresse)
            lat, lon = g["lat"], g["lon"]
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"erreur": f"Géocodage impossible: {exc}",
                              "etape": "transports"}, ensure_ascii=False))
            return 2

    try:
        out = arrets_proches(lat, lon, rayon_m=args.rayon, limite=args.limite)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    except ConnectorError as exc:
        print(json.dumps({"erreur": str(exc), "url": exc.url,
                          "etape": "transports"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(_main())
