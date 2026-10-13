"""Sélection short-list — filtre métier (skill chasse-professions-liberales).

À partir du JSON de recolte-shortlist.py, sélectionne les biens les plus
INTÉRESSANTS pour une chasse « signature libérale » :
  P1  locaux pro / commerciaux / bureaux 30-200 m² (destination pro avérée)
  P2  rez-de-chaussée (etage == 0) toutes destinations
  P3  appartements 30-99 m² en étage hypercentre
On privilégie les DÉCOTES (prix_baisse == true) et les prix/m² bas vs médiane
de la zone balayée.

Sortie : texte tabulé (pour construire le markdown) sur stdout.
"""
from __future__ import annotations

import json
import statistics
import sys

d = json.load(open("/tmp/recolte.json"))
ads = d["annonces"]


def prix_m2(a):
    ch = a.get("prix_m2")
    return ch["valeur"] if ch else None


def surface(a):
    ch = a.get("surface")
    return ch["valeur"] if ch else None


def prix(a):
    ch = a.get("prix")
    return ch["valeur"] if ch else None


def priorite(a):
    typ = (a.get("type") or "").lower()
    etage = a.get("etage")
    s = surface(a) or 0
    if typ in ("office", "commercial", "premises", "building") and 30 <= s <= 200:
        return 1
    if etage == 0:
        return 2
    if 30 <= s <= 99:
        return 3
    return 9


# score d'intérêt : décote + prix/m2 faible + type pro + RDC
def interet(a):
    p = priorite(a)
    sc = {1: 60, 2: 55, 3: 40, 9: 10}[p]
    if a.get("prix_baisse"):
        sc += 20
    if a.get("_score_pro", 0) >= 2:
        sc += 15
    if a.get("ascenseur"):
        sc += 3
    return sc


for a in ads:
    a["_prio"] = priorite(a)
    a["_interet"] = interet(a)

cand = [a for a in ads if a["_prio"] in (1, 2, 3)]
cand.sort(key=lambda a: (-a["_interet"], prix_m2(a) or 1e9))

# dédoublonnage visuel par (ville, prix, surface, type de base)
vus, short = set(), []
for a in cand:
    base = (a.get("type"), prix(a), surface(a))
    if base in vus:
        continue
    vus.add(base)
    short.append(a)

print(f"# candidats prio 1-3 : {len(cand)}, après dédoublonnage : {len(short)}")
print()
for a in short[:35]:
    s = surface(a)
    p = prix(a)
    m2 = prix_m2(a)
    print("\t".join([
        f"P{a['_prio']}",
        f"sc{a['_interet']}",
        a.get("_zone_balayee") or "",
        str(a.get("type")),
        f"{s}m2" if s else "?m2",
        f"{p}eur" if p else "?eur",
        f"{m2}eur/m2" if m2 else "?",
        f"et={a.get('etage')}",
        "BAISSE" if a.get("prix_baisse") else "-",
        (a.get("titre") or "")[:60].replace("\t", " "),
        a.get("url_annonce") or "",
    ]))
