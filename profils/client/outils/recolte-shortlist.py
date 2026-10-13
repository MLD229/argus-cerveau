"""Récolte short-list — balayage des zones des notifications (BRIEF-rin-notifs-recolte).

Zones issues des notifications : Lyon 1, 2, 3, 6, 7.
On interroge Bien'ici (voie n°1) avec la pagination CORRIGÉE + filtre POST-RÉPONSE
adType (aucune cession de bail). On applique ensuite le filtre métier du skill
`chasse-professions-liberales` (30-200 m², priorités RDC / locaux pro) — le tri
métier est calculé ICI, jamais inventé.

Sortie : JSON brut sur stdout (pour inspection), plus un résumé.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
from bienici import chercher_annonces  # noqa: E402

ZONES = ["Lyon 1", "Lyon 2", "Lyon 3", "Lyon 6", "Lyon 7"]

# Types métier : appartements + locaux pro/commerciaux + bureaux (RDC inclus).
TYPES = ["appartement", "bureau", "local commercial"]

# Filtre métier (skill chasse-professions-liberales) : 30-200 m².
SURF_MIN, SURF_MAX = 30, 200


def mot_cle_local(a: dict) -> int:
    """Score de « destination pro » d'après titre + type + description textuelle."""
    titre = (a.get("titre") or "").lower()
    typ = (a.get("type") or "").lower()
    pro = 0
    if typ in ("office", "commercial", "premises", "building"):
        pro += 2
    for kw in ("local", "bureau", "commerce", "cabinet", "murs", "commercial",
               "professionnel", "coworking", "plateau", "restaurant", "épicerie",
               "epicerie", "alimentation", "salon de thé", "boutique"):
        if kw in titre:
            pro += 1
    return pro


def collecter() -> dict:
    tous = []
    par_zone = {}
    for z in ZONES:
        res = chercher_annonces(zone=z, transaction="buy", types=TYPES,
                                surface_min=SURF_MIN, surface_max=SURF_MAX)
        annonces = res["resultat"]["annonces"]
        par_zone[z] = {
            "nb_pages": res["resultat"]["nb_pages"],
            "total_correspondant": res["resultat"]["total_correspondant"],
            "nb_brutes": res["resultat"]["nb_brutes"],
            "nb_exclues_transaction": res["resultat"]["nb_exclues_transaction"],
            "nb_annonces": res["resultat"]["nb_annonces"],
        }
        for a in annonces:
            a["_zone_balayee"] = z
            a["_score_pro"] = mot_cle_local(a)
        tous.extend(annonces)
    # dédoublonnage inter-zones par id
    vus, uniques = set(), []
    for a in tous:
        if a["id"] in vus:
            continue
        vus.add(a["id"])
        uniques.append(a)
    return {"par_zone": par_zone, "annonces": uniques}


if __name__ == "__main__":
    out = collecter()
    print(json.dumps(out, ensure_ascii=False, indent=2))
