"""DVF — ventes immobilières réelles (Etalab / DGFiP). Source officielle, sans clé.

- ventes_comparables(code_commune, annees, type_bien, surface) -> stats de prix.

Pièges connus :
- Les fichiers DVF sont PAR DÉPARTEMENT (~2 Mo gz), pas par commune : on
  télécharge le dept et on filtre côté client.
- L'URL redirige (302) vers un S3 : le helper suit la redirection.
- Cache local sous DVF_CACHE_DIR (défaut /tmp/argus-immo-dvf-cache).
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import os
import statistics
import sys
from datetime import date

from _http import ConnectorError, http_get_bytes, json_error

DVF_URL = "https://files.data.gouv.fr/geo-dvf/latest/csv/{annee}/departements/{dep}.csv.gz"
CACHE_DIR = os.environ.get("DVF_CACHE_DIR", "/tmp/argus-immo-dvf-cache")

# Bornes de crédibilité d'un prix au m² de logement (€/m²). Hors de cet
# intervalle, la valeur est aberrante (erreur de saisie, terrain, lots
# multiples…) : on l'écarte pour garder une fourchette min/max crédible.
PPM2_MIN = 500.0
PPM2_MAX = 25000.0


def _now() -> str:
    return date.today().isoformat()


def _fetch_dep_file(annee: int, dep: str) -> str:
    """Télécharge (ou lit le cache) le CSV.gz des ventes d'un département."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"dvf-{annee}-{dep}.csv.gz")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    url = DVF_URL.format(annee=annee, dep=dep)
    try:
        raw = http_get_bytes(url, timeout=90, retries=2)
    except ConnectorError as exc:
        raise ConnectorError(f"DVF indisponible pour {dep}/{annee}: {exc}", url=url) from exc
    with open(path, "wb") as fh:
        fh.write(raw)
    return path


def _iter_rows(path: str):
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        yield from csv.DictReader(fh)


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def ventes_comparables(code_commune: str, annees: list[int] | None = None, *,
                       type_bien: str | None = None,
                       surface: float | None = None,
                       tolerance_surface: float = 0.20) -> dict:
    """Ventes réelles DVF dans une commune -> statistiques de prix.

    code_commune : code INSEE ('69386'). Le département est déduit des 2 premiers
                   chiffres (69386 -> '69').
    Retour : nb_ventes, mediane_m2, min_m2, max_m2, et la liste des ventes.

    Anti-pollution de la fourchette (pièges connus) :
    - Les mutations MULTI-LOTS (immeubles, plusieurs lignes rattachées au même
      id_mutation) sont EXCLUES : leur valeur_fonciere globale est répétée sur
      chaque ligne, ce qui produit un €/m² absurde (ex. 75 000 €/m²).
    - Les €/m² hors bornes crédibles (PPM2_MIN..PPM2_MAX) sont écartés.
    Le nombre d'écarts est renvoyé dans `exclusions`.
    """
    code_commune = str(code_commune).strip()
    dep = code_commune[:2]
    if annees is None:
        annees = [date.today().year - 1]

    exclusions = {"multi_lots": 0, "hors_bornes": 0, "hors_surface": 0}

    def _ligne_valide(r: dict, *, filtrer_surface: bool) -> bool:
        """Pré-filtre ligne : nature, type, surface/valeur exploitables.

        `filtrer_surface=False` sert à compter les lots d'une mutation AVANT
        d'appliquer la contrainte de surface : un immeuble reste un immeuble
        même si seul un de ses lots tombe dans la fourchette de surface.
        """
        if r.get("nature_mutation") != "Vente":
            return False
        tb = r.get("type_local")
        if type_bien and tb and tb.lower() != type_bien.lower():
            return False
        surf = _to_float(r.get("surface_reelle_bati"))
        valeur = _to_float(r.get("valeur_fonciere"))
        if not surf or not valeur or surf <= 0:
            return False
        if filtrer_surface and surface:
            lo = surface * (1 - tolerance_surface)
            hi = surface * (1 + tolerance_surface)
            if not (lo <= surf <= hi):
                return False
        return True

    ventes: list[dict] = []
    for annee in annees:
        path = _fetch_dep_file(annee, dep)
        # 1. Regrouper par mutation : une mutation multi-lots (immeuble vendu
        #    en bloc) ne doit PAS alimenter le prix au m² du logement.
        par_mutation: dict[str, list[dict]] = {}
        for r in _iter_rows(path):
            if str(r.get("code_commune")) != code_commune:
                continue
            mid = r.get("id_mutation") or f"_sans_id_{len(par_mutation)}"
            par_mutation.setdefault(mid, []).append(r)

        for mid, lignes in par_mutation.items():
            # 2. Exclusion des mutations multi-lots : on compte les logements
            #    exploitables SANS appliquer le filtre surface (sinon les autres
            #    lots d'un immeuble disparaissent et l'immeuble passerait pour
            #    une vente simple -> compteur menteur).
            lots = [r for r in lignes if _ligne_valide(r, filtrer_surface=False)]
            if len(lots) > 1:
                exclusions["multi_lots"] += 1
                continue
            retenues = [r for r in lots if _ligne_valide(r, filtrer_surface=True)]
            if not retenues:
                if lots:
                    exclusions["hors_surface"] += 1
                continue
            r = retenues[0]
            surf = _to_float(r.get("surface_reelle_bati")) or 0.0
            valeur = _to_float(r.get("valeur_fonciere")) or 0.0
            ppm2 = round(valeur / surf, 2) if surf > 0 else 0.0
            # 3. Bornage : un €/m² aberrant (terrain, erreur) est écarté.
            if not (PPM2_MIN <= ppm2 <= PPM2_MAX):
                exclusions["hors_bornes"] += 1
                continue
            ventes.append({
                "date": r.get("date_mutation"),
                "type": r.get("type_local"),
                "surface": surf,
                "valeur": valeur,
                "prix_m2": ppm2,
                "adresse": r.get("adresse_nom_voie"),
            })

    if not ventes:
        raise ConnectorError(
            f"Aucune vente DVF exploitable pour commune {code_commune} / annees {annees}"
            + (f" / type {type_bien}" if type_bien else ""))

    prix_m2 = [v["prix_m2"] for v in ventes]
    return {
        "code_commune": code_commune,
        "annees": annees,
        "type_bien": type_bien,
        "nb_ventes": len(ventes),
        "mediane_m2": round(statistics.median(prix_m2), 2),
        "min_m2": min(prix_m2),
        "max_m2": max(prix_m2),
        "exclusions": exclusions,
        "ventes": sorted(ventes, key=lambda v: v["date"] or "", reverse=True),
        "fiabilite": "verifie",
        "source": "DVF Etalab",
        "date": _now(),
    }


def _cli() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Ventes réelles DVF (Etalab)")
    p.add_argument("--commune", required=True, help="code INSEE (ex. 69386)")
    p.add_argument("--annees", nargs="+", type=int, default=None)
    p.add_argument("--type", dest="type_bien", default=None,
                   help="Appartement | Maison")
    p.add_argument("--surface", type=float, default=None)
    args = p.parse_args()
    try:
        res = ventes_comparables(args.commune, args.annees, type_bien=args.type_bien,
                                 surface=args.surface)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    except ConnectorError as exc:
        print(json.dumps(json_error(str(exc), url=exc.url), ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(_cli())
