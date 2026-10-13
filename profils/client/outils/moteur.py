"""MOTEUR — orchestrateur : chaîne les outils -> fiche bien complète.

enrichir_bien(adresse, surface, commune, code_postal, type_bien, annee_dvf)
  enchaîne :
    1. géocodage BAN           (geocode.geocoder)
    2. commune / arrondissement (geocode.commune)
    3. parcelle cadastrale IGN  (cadastre_par_point — repli bbox, a_verifier)
    4. DPE ADEME                (dpe.dpe_par_adresse)
    5. ventes comparables DVF   (dvf.ventes_comparables)

Sortie : le FORMAT PARTAGÉ (docs/contrat-outils.md §4) :
  { tache, statut, entree, resultat: {champ: {valeur,source,fiabilite,date}},
    etapes, erreurs, date }

Règle absolue : aucune donnée inventée. Source en échec -> entrée dans `erreurs`,
champ en `a_verifier`/`indisponible`. Ne lève jamais : collecte les erreurs.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
from datetime import date

from _http import ConnectorError, http_get_json, json_error

IGN_PARCEL = "https://apicarto.ign.fr/api/cadastre/parcelle"


def _now() -> str:
    return date.today().isoformat()


def _champ(valeur, source: str, fiabilite: str, *, note: str | None = None) -> dict:
    d = {"valeur": valeur, "source": source, "fiabilite": fiabilite, "date": _now()}
    if note:
        d["note"] = note
    return d


def parcelle_par_point(lon: float, lat: float) -> dict:
    """Parcelle cadastrale la plus proche d'un point (repli bbox si besoin).

    ⚠ apicarto : `code_insee` seul ne renvoie RIEN ; il faut `geom` (point/bbox).
    Le point BAN tombe sur la VOIE -> repli bbox (±~45 m), fiabilité a_verifier.

    ⚠ Possibilité d'ID de section cadastrale absente du fichier en charge.
      Comme on ne peut pas garantir le rattachement exact, on marque `a_verifier`.
    """
    # Tentative 1 : point exact.
    geom = json.dumps({"type": "Point", "coordinates": [lon, lat]})
    data = http_get_json(IGN_PARCEL, {"geom": geom, "_limit": 1})
    feats = (data or {}).get("features") if isinstance(data, dict) else None
    fiab = "verifie"
    note = None
    if not feats:
        # Tentative 2 : repli bbox (±~45 m) en GeoJSON Polygon.
        # ⚠ apicarto `geom` attend du GeoJSON (Point/Polygon), PAS "lon,lat,...".
        d = 0.0004
        poly = {
            "type": "Polygon",
            "coordinates": [[
                [lon - d, lat - d], [lon + d, lat - d],
                [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d],
            ]],
        }
        data = http_get_json(IGN_PARCEL, {"geom": json.dumps(poly), "_limit": 5})
        feats = (data or {}).get("features") if isinstance(data, dict) else None
        fiab = "a_verifier"
        note = "repli bbox (±45 m) : rattachement a confirmer (point BAN sur la voie)"
    if not feats:
        raise ConnectorError("Aucune parcelle IGN trouvee (point et bbox)", url=IGN_PARCEL)

    f = feats[0]
    p = f.get("properties", {})
    return {
        "section": p.get("section"),
        "numero": p.get("numero"),
        "contenance": p.get("contenance"),
        "commune": p.get("nom_com"),
        "prefixe": p.get("prefixe"),
        "fiabilite": fiab,
        "note": note,
    }


def enrichir_bien(adresse: str, surface: float | None = None, *,
                  commune: str | None = None,
                  code_postal: str | None = None,
                  type_bien: str | None = None,
                  annee_dvf: int | None = None) -> dict:
    """Chaîne la collecte open data -> fiche bien (format partagé)."""
    etapes: dict = {}
    erreurs: list[dict] = []
    resultat: dict = {}

    # --- 1. Géocodage BAN ---------------------------------------------------
    geo = None
    try:
        from geocode import geocoder  # import local (cwd = outils/)
        geo = geocoder(adresse, code_postal=code_postal)
        resultat["adresse_normalisee"] = _champ(
            geo["adresse_normalisee"], "BAN api-adresse", "verifie")
        resultat["coordonnees"] = _champ(
            {"lat": geo["lat"], "lon": geo["lon"]}, "BAN api-adresse", "verifie")
        etapes["geocodage_ban"] = "ok"
    except ConnectorError as exc:
        etapes["geocodage_ban"] = "echec"
        erreurs.append({"etape": "geocodage_ban", "erreur": str(exc), "url": exc.url})

    # --- 2. Commune / arrondissement ---------------------------------------
    insee = (geo or {}).get("code_insee") or commune
    if insee:
        try:
            from geocode import commune as commune_info
            com = commune_info(insee)
            resultat["commune"] = _champ(
                com.get("nom"), "geo.api.gouv.fr", "verifie",
                note=f"code INSEE {com.get('code_insee')}, population {com.get('population')}")
            etapes["commune"] = "ok"
        except ConnectorError as exc:
            etapes["commune"] = "echec"
            erreurs.append({"etape": "commune", "erreur": str(exc), "url": exc.url})
    else:
        etapes["commune"] = "ignore"

    # --- 3. Parcelle cadastrale IGN ----------------------------------------
    if geo:
        try:
            parc = parcelle_par_point(geo["lon"], geo["lat"])
            resultat["parcelle"] = _champ(
                {"section": parc["section"], "numero": parc["numero"],
                 "contenance": parc["contenance"]},
                "IGN apicarto", parc["fiabilite"], note=parc.get("note"))
            etapes["parcelle_cadastre"] = "ok" if parc["fiabilite"] == "verifie" else "partiel"
        except ConnectorError as exc:
            etapes["parcelle_cadastre"] = "echec"
            erreurs.append({"etape": "parcelle_cadastre", "erreur": str(exc), "url": exc.url})
    else:
        etapes["parcelle_cadastre"] = "ignore"

    # --- 4. DPE ADEME -------------------------------------------------------
    if geo:
        try:
            from dpe import dpe_par_adresse
            res_dpe = dpe_par_adresse(geo["adresse_normalisee"])
            d = res_dpe["dpe"]
            resultat["dpe"] = _champ(
                {"classe_energie": d.get("classe_energie"), "classe_ges": d.get("classe_ges")},
                "ADEME data-fair", "verifie")
            etapes["dpe_ademe"] = "ok"
        except ConnectorError as exc:
            etapes["dpe_ademe"] = "echec"
            erreurs.append({"etape": "dpe_ademe", "erreur": str(exc), "url": exc.url})
    else:
        etapes["dpe_ademe"] = "ignore"

    # --- 5. Ventes comparables DVF -----------------------------------------
    if insee:
        try:
            from dvf import ventes_comparables
            annee = annee_dvf or (date.today().year - 1)
            dv = ventes_comparables(str(insee), [annee], type_bien=type_bien, surface=surface)
            resultat["prix_marche"] = _champ(
                {"mediane_m2": dv["mediane_m2"], "nb_ventes": dv["nb_ventes"],
                 "type_bien": type_bien, "annee": annee},
                "DVF Etalab", "verifie")
            etapes["dvf"] = "ok"
        except ConnectorError as exc:
            etapes["dvf"] = "echec"
            erreurs.append({"etape": "dvf", "erreur": str(exc), "url": exc.url})
    else:
        etapes["dvf"] = "ignore"

    # --- Statut global ------------------------------------------------------
    n_ok = sum(1 for v in etapes.values() if v == "ok")
    n_echec = sum(1 for v in etapes.values() if v == "echec")
    if n_echec == 0:
        statut = "ok"
    elif n_ok > 0:
        statut = "partiel"
    else:
        statut = "echec"

    return {
        "tache": "fiche-bien",
        "statut": statut,
        "entree": {"adresse": adresse, "surface": surface, "commune": insee,
                   "code_postal": code_postal, "type_bien": type_bien,
                   "annee_dvf": annee_dvf},
        "resultat": resultat,
        "etapes": etapes,
        "sources": ["BAN api-adresse", "geo.api.gouv.fr", "IGN apicarto",
                    "ADEME data-fair", "DVF Etalab"],
        "erreurs": erreurs,
        "date": _now(),
    }


def _cli() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Fiche bien enrichie (open data)")
    p.add_argument("--adresse", required=True)
    p.add_argument("--cp", dest="code_postal", default=None)
    p.add_argument("--surface", type=float, default=None)
    p.add_argument("--commune", default=None, help="code INSEE (si pas de geocodage)")
    p.add_argument("--type", dest="type_bien", default=None, help="Appartement | Maison")
    p.add_argument("--annee", dest="annee_dvf", type=int, default=None)
    args = p.parse_args()
    try:
        res = enrichir_bien(args.adresse, args.surface, commune=args.commune,
                            code_postal=args.code_postal, type_bien=args.type_bien,
                            annee_dvf=args.annee_dvf)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["statut"] != "echec" else 2
    except Exception as exc:  # garde-fou CLI : jamais de trace brute
        print(json.dumps(json_error(str(exc)), ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(_cli())
