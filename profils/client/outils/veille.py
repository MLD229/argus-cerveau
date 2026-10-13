"""Veille — SOURCES de notifications Argus.

PRODUIT des notifications à partir de sources gratuites et légales, en appelant
notifications.ajouter(...). Ce module NE STOCKE RIEN lui-même : le magasin est
outils/notifications.py (contrat ajouter(*, type, titre, corps, source, donnees,
severite, cle_dedup) -> {"ajoutee": bool, "notification": {...}}).

SOURCES
-------
1. Nouvelles annonces Bien'ici : outils/bienici.py (flux JSON public). Chaque
   annonce jamais vue -> notification type="annonce". Les IDs vus sont mémorisés
   (état local) pour ne pas renotifier.
2. Baisse de prix : une annonce déjà vue dont le prix baisse -> type="marche",
   severite="important". Une seule baisse par annonce si la baisse est inchangée.
3. Ventes DVF récentes : outils/dvf.py (Etalab). Nouvelles mutations -> type="vente".

CONTRAINTES DURES
-----------------
- stdlib pure (urllib/json/csv/argparse) — aucune dépendance à installer.
- BORNÉ : au plus N annonces traitées, 1 seul retry par source, jamais de boucle.
- Rien n'est inventé : une source qui échoue -> erreur propre dans le rapport
  (statut="partiel"/"erreur"), jamais de crash ni de donnée fabriquée.

ÉTAT LOCAL (anti-renotification)
--------------------------------
Fichier JSON par défaut /tmp/argus-veille-etat.json (surchargeable par
ARGUS_VEILLE_ETAT). Structure :
    {"annonces": {"<id annonce>": {"prix": <int>, "baisse_vue": <prix|null>}},
     "ventes":   {"<cle mutation>": {"date": ..., "prix_m2": ...}}}

CLI
---
  python3 outils/veille.py annonces --zone "Lyon 6" [--limite 40] [--transaction buy]
  python3 outils/veille.py ventes   --commune 69386 [--annee 2024] [--limite 20]
Sortie : enveloppe §4.1 (JSON). Échec : {"erreur": ...} + code 2.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import notifications as notif  # noqa: E402
from _http import ConnectorError  # noqa: E402

ETAT_DEFAUT = "/tmp/argus-veille-etat.json"

# Bornes : jamais de boucle, jamais de traitement illimité.
# Plafond de SÉCURITÉ (pas une fenêtre d'observation) : il borne ce qu'un
# passage peut traiter au pire, il ne restreint PAS la collecte. Le flux public
# Bien'ici rend ~3000 annonces pour les 6 zones surveillées (~4,6 s, 45 Mo) :
# un plafond à 2000 laisse largement de la marge tout en évitant tout emballement.
# AVANT (bug) : 40 -> la veille ne voyait que 4 % du flux, donc ne remontait
# jamais rien (fenêtre figée sur les 40 têtes de liste).
MAX_ANNONCES = 2000  # plafond dur d'annonces traitées par passage
MAX_VENTES = 30     # plafond dur de ventes traitées par passage


class VeilleError(RuntimeError):
    """Erreur claire de la veille (source indisponible, paramètre invalide)."""


def _etat_fichier() -> str:
    return os.environ.get("ARGUS_VEILLE_ETAT", ETAT_DEFAUT)


def _lire_etat() -> dict:
    p = _etat_fichier()
    if not os.path.exists(p):
        return {"annonces": {}, "ventes": {}}
    try:
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, json.JSONDecodeError):
        # État corrompu : on repart de zéro plutôt que de planter la veille.
        return {"annonces": {}, "ventes": {}}
    d.setdefault("annonces", {})
    d.setdefault("ventes", {})
    return d


def _ecrire_etat(d: dict) -> None:
    p = _etat_fichier()
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except OSError as exc:
        raise VeilleError(f"État veille non inscriptible ({p}): {exc}") from exc


def _maintenant() -> str:
    return date.today().isoformat()


def _fmt_prix(v) -> str:
    if not isinstance(v, (int, float)):
        return "n/a"
    return f"{int(v):,}".replace(",", " ") + " €"


def _nettoyer(s) -> str:
    """Décode les entités HTML fréquentes des titres d'annonces (&sup2;, &#39;…).

    Certains titres bruts de Bien'ici contiennent des entités (« 30 m&sup2; »).
    Purement cosmétique : on décode les plus courantes, sans dépendance.
    """
    if not isinstance(s, str):
        return s
    remp = {"&sup2;": "²", "&sup3;": "³", "&nbsp;": " ", "&amp;": "&",
            "&quot;": '"', "&#39;": "'", "&apos;": "'", "&lt;": "<", "&gt;": ">",
            "&eacute;": "é", "&egrave;": "è", "&agrave;": "à", "&deg;": "°"}
    for k, v in remp.items():
        s = s.replace(k, v)
    return s


def _fichier_notifs_effectif() -> str:
    return os.environ.get("ARGUS_NOTIFS_FILE", notif.FILE_DEFAUT)


def _enveloppe(*, tache: str, statut: str, entree: dict, resultat: dict,
               sources: list[str], erreurs: list[str]) -> dict:
    return {"tache": tache, "statut": statut, "entree": entree,
            "resultat": resultat, "sources": sources, "erreurs": erreurs,
            "date": _maintenant()}


# ------------------------------------------------------------------ SOURCE 1+2
def veille_annonces(*, zone: str, transaction: str = "buy",
                    limite: int = MAX_ANNONCES,
                    types: list[str] | None = None,
                    type_vendeur: str = "tous") -> dict:
    """Nouvelles annonces + baisses de prix Bien'ici -> notifications.

    type_vendeur : 'tous' (défaut) | 'particulier' | 'agence'. Filtré en amont
                   par bienici.chercher_annonces. Les PARTICULIERS sont en plus
                   TOUJOURS priorisés (remontent en tête) et notifiés en
                   sévérité 'important' (voir le tri + le compteur 'particuliers').
    Retour : enveloppe avec compteurs (nouvelles, baisses, deja_vues, notifiees,
             particuliers).
    Une source en échec ne lève PAS : le statut passe à "erreur"/"partiel" et
    le message est rangé dans erreurs (jamais de crash).
    """
    if limite > MAX_ANNONCES:
        limite = MAX_ANNONCES
    if limite <= 0:
        raise VeilleError("limite doit être > 0")

    erreurs: list[str] = []
    annonces: list[dict] = []
    statut = "ok"

    # --- collecte : 1 seul retry (borné), erreur propre si indisponible ------
    try:
        import bienici
        # Types métier à la SOURCE : réduit le volume ramené (on ne demande pas
        # les maisons/parkings). Repli sur le raisonnement : si la config ne
        # définit pas de types, on laisse `types` tel quel (None = tous).
        types_source = types
        if types_source is None:
            try:
                import veille_config as _vc
                _cfg_src = _vc.lire().get("filtre", {})
                if _cfg_src.get("actif", True) and _cfg_src.get("types"):
                    # On ne passe à l'API que des libellés qu'elle comprend.
                    _fr = {"flat": "appartement", "office": "bureau",
                           "premises": "local commercial", "commercial": "local commercial",
                           "loft": "appartement"}
                    _vus, _api = set(), []
                    for t in _cfg_src["types"]:
                        v = _fr.get(str(t).lower())
                        if v and v not in _vus:
                            _vus.add(v); _api.append(v)
                    types_source = _api or None
            except Exception:  # noqa: BLE001
                types_source = None
        # PIÈGE API (bug corrigé) : `taille` est la TAILLE DE PAGE passée à
        # `size` dans la requête Bien'ici ; l'API la plafonne (~100). Passer une
        # grande valeur CASSE la pagination et ne rend qu'une page courte
        # (mesuré : size=2000 -> 47 annonces ; size=100 -> 665). On fixe donc une
        # taille de page raisonnable (100) et on laisse `tout=True` (défaut)
        # paginer jusqu'à épuisement. `limite` n'est PLUS la taille de page :
        # c'est le plafond d'observation appliqué APRÈS la collecte complète.
        res = bienici.chercher_annonces(zone=zone, transaction=transaction,
                                        types=types_source, taille=100,
                                        type_vendeur=type_vendeur)
        # On parcourt TOUT le flux paginé, borné par `limite` (sécurité).
        # AVANT : [:40] sur une collecte déjà tronquée -> veille aveugle.
        annonces = list(res.get("resultat", {}).get("annonces", []))[:limite]
    except ConnectorError as exc:
        return _enveloppe(
            tache="veille-annonces", statut="erreur",
            entree={"zone": zone, "transaction": transaction, "limite": limite},
            resultat={"utilisees": 0, "trouvees": 0, "nouvelles": 0,
                      "baisses_prix": 0, "deja_vues": 0, "notifiees": 0,
                      "magasin": _fichier_notifs_effectif()},
            sources=["Bien'ici"], erreurs=[f"source Bien'ici indisponible: {exc}"])
    except Exception as exc:  # garde-fou : jamais de crash brut
        return _enveloppe(
            tache="veille-annonces", statut="erreur",
            entree={"zone": zone, "transaction": transaction, "limite": limite},
            resultat={"utilisees": 0, "trouvees": 0, "nouvelles": 0,
                      "baisses_prix": 0, "deja_vues": 0, "notifiees": 0,
                      "magasin": _fichier_notifs_effectif()},
            sources=["Bien'ici"], erreurs=[f"erreur inattendue Bien'ici: {exc}"])

    etat = _lire_etat()
    vues: dict = etat["annonces"]
    compteurs = {"nouvelles": 0, "baisses_prix": 0, "deja_vues": 0, "notifiees": 0,
                 "filtrees": 0, "particuliers": 0}

    # Filtre de pertinence réglable (config partagée). Conservateur : écarte le
    # gros bruit (parkings, box, boutiques) et les surfaces hors bornes.
    try:
        import veille_config
        cfg = veille_config.lire()
    except Exception:  # noqa: BLE001
        cfg = None

    # PRIORISATION « particuliers » (demande client) : on traite d'ABORD les
    # annonces de particuliers (vente directe, sans agence), pour qu'elles
    # remontent en tête dans la veille. On n'EXCLUT pas les agences : elles
    # suivent. Le tri est stable (l'ordre d'origine est conservé au sein de
    # chaque groupe). Sur le flux public Bien'ici, il n'y a pas de particulier
    # (tout est pro) — le tri est donc neutre aujourd'hui mais prêt et correct.
    annonces.sort(key=lambda a: 0 if a.get("particulier") else 1)

    for a in annonces:
        aid = a.get("id") or a.get("url_annonce")
        if not aid:
            # Sans identifiant stable, pas de dédoublonnage possible -> on saute.
            continue
        # Filtre : on n'ÉTUDIE que les biens pertinents (avant tout dédoublonnage).
        if cfg is not None:
            garder, _raison = veille_config.pertinente(a, cfg)
            if not garder:
                compteurs["filtrees"] += 1
                continue
        prix = (a.get("prix") or {}).get("valeur")
        prix_m2 = (a.get("prix_m2") or {}).get("valeur")
        titre = _nettoyer(a.get("titre")) or f"{a.get('type') or 'bien'} {a.get('ville') or ''}".strip()
        lieu = _nettoyer(" ".join(x for x in (a.get("quartier"), a.get("code_postal"),
                                              a.get("ville")) if x)) or zone

        vue = vues.get(aid)
        # Vendeur lu dans l'annonce normalisée (champ posé par bienici.py :
        # 'particulier' ou 'agence'). Absent -> on ne prétend rien.
        vendeur = a.get("vendeur") or ("particulier" if a.get("particulier") else "agence")
        est_partic = (vendeur == "particulier")
        if est_partic:
            compteurs["particuliers"] += 1

        # --- 2. BAISSE DE PRIX : annonce déjà vue, prix inférieur --------------
        if vue is not None and isinstance(prix, (int, float)) and \
                isinstance(vue.get("prix"), (int, float)) and prix < vue["prix"]:
            # On ne renotifie pas la MÊME baisse (étiquette baisse_vue = prix courant).
            if vue.get("baisse_vue") != prix:
                baisse = vue["prix"] - prix
                pct = round(100 * baisse / vue["prix"], 1) if vue["prix"] else 0
                r = notif.ajouter(
                    type="marche",
                    titre=f"Baisse de prix : {titre}",
                    corps=(f"{lieu} — prix {_fmt_prix(vue['prix'])} -> {_fmt_prix(prix)} "
                           f"(-{_fmt_prix(baisse)}, -{pct} %)."),
                    source="Bien'ici",
                    severite="important",
                    donnees={"id_annonce": aid, "prix_avant": vue["prix"],
                             "prix_apres": prix, "prix_m2": prix_m2, "vendeur": vendeur,
                             "particulier": est_partic,
                             "url_annonce": a.get("url_annonce"), "lieu": lieu},
                    cle_dedup=f"baisse:{aid}:{int(prix)}",
                )
                compteurs["baisses_prix"] += 1
                if r.get("ajoutee"):
                    compteurs["notifiees"] += 1
                vue["baisse_vue"] = prix
            vue["prix"] = prix
            vues[aid] = vue
            continue

        # --- 1. NOUVELLE ANNONCE : id jamais vu --------------------------------
        if vue is None:
            # PRIORISATION : une nouvelle annonce de PARTICULIER remonte en
            # sévérité 'important' (vente directe, souvent la meilleure affaire)
            # et son titre le signale. Les agences restent en 'info'.
            r = notif.ajouter(
                type="annonce",
                titre=(f"{titre} — particulier" if est_partic else titre),
                corps=(f"Nouvelle annonce {lieu} — {a.get('type') or 'bien'}, "
                       f"{a.get('surface', {}).get('valeur') or '?'} m², "
                       f"{_fmt_prix(prix)}."
                       + (" Vendeur : particulier (sans agence)." if est_partic else "")),
                source="Bien'ici",
                severite="important" if est_partic else "info",
                donnees={"id_annonce": aid, "prix": prix, "prix_m2": prix_m2,
                         "type": a.get("type"),
                         "surface": (a.get("surface") or {}).get("valeur"),
                         "pieces": a.get("pieces"), "vendeur": vendeur,
                         "particulier": est_partic,
                         "url_annonce": a.get("url_annonce"), "lieu": lieu},
                cle_dedup=f"annonce:{aid}",
            )
            compteurs["nouvelles"] += 1
            if r.get("ajoutee"):
                compteurs["notifiees"] += 1
            vues[aid] = {"prix": prix, "baisse_vue": None}
            continue

        # --- déjà vue, pas de baisse : rien à faire (pas de renotification) -----
        compteurs["deja_vues"] += 1
        if isinstance(prix, (int, float)):
            vue["prix"] = prix
            vues[aid] = vue

    _ecrire_etat(etat)

    if erreurs:
        statut = "partiel"
    return _enveloppe(
        tache="veille-annonces", statut=statut,
        entree={"zone": zone, "transaction": transaction, "limite": limite},
        resultat={"zone": zone, "trouvees": len(annonces), "utilisees": len(annonces),
                  **compteurs, "magasin": _fichier_notifs_effectif()},
        sources=["Bien'ici", "magasin local argus-notifications.json"], erreurs=erreurs)


# -------------------------------------------------------------------- SOURCE 3
def veille_ventes(*, commune: str, annee: int | None = None,
                  type_bien: str | None = None,
                  limite: int = MAX_VENTES) -> dict:
    """Nouvelles ventes DVF réelles d'une commune -> notifications type="vente".

    commune : code INSEE (ex. 69386 = Lyon 6e). annee : défaut = année en cours.
    Chaque mutation jamais vue est notifiée une fois (clé_dedup stable).
    """
    if limite > MAX_VENTES:
        limite = MAX_VENTES
    if not str(commune or "").strip():
        raise VeilleError("commune (code INSEE) requis")
    annees = [annee] if annee else [date.today().year]

    erreurs: list[str] = []
    ventes: list[dict] = []
    try:
        import dvf
        res = dvf.ventes_comparables(str(commune), annees, type_bien=type_bien)
        ventes = list(res.get("ventes", []))[:limite]
    except ConnectorError as exc:
        return _enveloppe(
            tache="veille-ventes", statut="erreur",
            entree={"commune": commune, "annees": annees, "type_bien": type_bien},
            resultat={"nouvelles": 0, "deja_vues": 0, "notifiees": 0,
                      "magasin": _fichier_notifs_effectif()},
            sources=["DVF Etalab"], erreurs=[f"source DVF indisponible: {exc}"])
    except Exception as exc:  # garde-fou
        return _enveloppe(
            tache="veille-ventes", statut="erreur",
            entree={"commune": commune, "annees": annees, "type_bien": type_bien},
            resultat={"nouvelles": 0, "deja_vues": 0, "notifiees": 0,
                      "magasin": _fichier_notifs_effectif()},
            sources=["DVF Etalab"], erreurs=[f"erreur inattendue DVF: {exc}"])

    etat = _lire_etat()
    vues: dict = etat["ventes"]
    compteurs = {"nouvelles": 0, "deja_vues": 0, "notifiees": 0}

    for v in ventes:
        # Clé stable : date + adresse + surface + valeur (pas d'id fourni par DVF).
        cle = f"{v.get('date')}|{v.get('adresse')}|{v.get('surface')}|{v.get('valeur')}"
        if cle in vues:
            compteurs["deja_vues"] += 1
            continue
        r = notif.ajouter(
            type="vente",
            titre=f"Vente DVF {v.get('type') or 'bien'} — {commune}",
            corps=(f"{v.get('date')} · {v.get('adresse') or 'adresse non précisée'} · "
                   f"{v.get('surface')} m² · {_fmt_prix(v.get('valeur'))} "
                   f"({v.get('prix_m2')} €/m²)."),
            source="DVF Etalab",
            severite="info",
            donnees={"commune": str(commune), "date_mutation": v.get("date"),
                     "type": v.get("type"), "surface": v.get("surface"),
                     "valeur": v.get("valeur"), "prix_m2": v.get("prix_m2"),
                     "adresse": v.get("adresse")},
            cle_dedup=f"vente:{commune}:{cle}",
        )
        compteurs["nouvelles"] += 1
        if r.get("ajoutee"):
            compteurs["notifiees"] += 1
        vues[cle] = {"date": v.get("date"), "prix_m2": v.get("prix_m2")}

    _ecrire_etat(etat)

    return _enveloppe(
        tache="veille-ventes", statut="partiel" if erreurs else "ok",
        entree={"commune": commune, "annees": annees, "type_bien": type_bien},
        resultat={"commune": str(commune), "trouvees": len(ventes), **compteurs,
                  "magasin": _fichier_notifs_effectif()},
        sources=["DVF Etalab", "magasin local argus-notifications.json"],
        erreurs=erreurs)


# ------------------------------------------------------------------------ CLI
def _cli() -> int:
    p = argparse.ArgumentParser(description="Veille Argus — sources de notifications.")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("annonces", help="nouvelles annonces + baisses (Bien'ici)")
    a.add_argument("--zone", required=True, help="ex. \"Lyon 6\"")
    a.add_argument("--transaction", default="buy", choices=["buy", "rent"])
    a.add_argument("--limite", type=int, default=MAX_ANNONCES)
    a.add_argument("--types", nargs="*", default=None)
    a.add_argument("--particuliers-seulement", dest="type_vendeur",
                   action="store_const", const="particulier", default="tous",
                   help="ne veiller que les annonces de particuliers")
    a.add_argument("--type-vendeur", dest="type_vendeur", default=None,
                   choices=["tous", "particulier", "agence"],
                   help="filtre vendeur (prime sur --particuliers-seulement)")

    v = sub.add_parser("ventes", help="nouvelles ventes DVF (Etalab)")
    v.add_argument("--commune", required=True, help="code INSEE (ex. 69386)")
    v.add_argument("--annee", type=int, default=None)
    v.add_argument("--type", dest="type_bien", default=None, help="Appartement | Maison")
    v.add_argument("--limite", type=int, default=MAX_VENTES)

    args = p.parse_args()
    try:
        if args.cmd == "annonces":
            out = veille_annonces(zone=args.zone, transaction=args.transaction,
                                  limite=args.limite, types=args.types,
                                  type_vendeur=args.type_vendeur or "tous")
        else:
            out = veille_ventes(commune=args.commune, annee=args.annee,
                                type_bien=args.type_bien, limite=args.limite)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    except VeilleError as exc:
        print(json.dumps({"erreur": str(exc), "etape": "veille"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(_cli())
