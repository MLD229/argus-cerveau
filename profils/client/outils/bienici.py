"""Bien'ici — annonces immobilières via le flux JSON PUBLIC (voie n°1, autorisée).

- resoudre_zone(texte)         : texte -> zones avec zoneIds (OBLIGATOIRE d'abord).
- chercher_annonces(zone, ...) : annonces normalisées pour une zone.
- chercher_seloger_playwright(url) : SeLoger par navigateur — USAGE MODÉRÉ.

Pourquoi Bien'ici en n°1 : flux JSON public, non bloqué, robots permissif.
Fiabilité : 'annonce' (prix AFFICHÉ, non vérifié) — croiser avec DVF pour le
prix réel du marché.

INTERDIT (ne jamais tenter, même avec Playwright) :
  - LEBONCOIN : robots interdit les robots ; test réel = HTTP 403 + DataDome.
  - LOGIC-IMMO : DataDome. Contourner = violation de la charte projet.
"""
from __future__ import annotations

import json
import sys
from datetime import date

from _http import ConnectorError, http_get_json, json_error

BIENICI_SUGGEST = "https://res.bienici.com/suggest.json"
BIENICI_SEARCH = "https://www.bienici.com/realEstateAds.json"
SELOGER_PRO_LYON = ("https://www.seloger.com/recherche/achat/locaux-professionnels/"
                    "auvergne-rhone-alpes/lyon-69000/ad08fr28808")

# Types de transaction (champ BRUT `adType`) qui correspondent à une vraie
# VENTE classique. Constaté réellement sur le flux Bien'ici (Lyon 6, test
# 2026-10-10) : les valeurs renvoyées sont 'buy', 'leaseback',
# 'businessTakeOver', 'prestige'. Seul 'buy' (et 'prestige', une vente haut de
# gamme) sont de vraies ventes de murs.
#
# ⚠ LE PIÈGE : le paramètre de requête `filterType: "buy"` ne garantit PAS que
# toutes les annonces renvoyées soient des ventes de murs. Une CESSION DE BAIL
# revient avec `adType == "leaseback"` (ou `businessTakeOver` pour un fonds de
# commerce / une reprise d'activité) alors même qu'on a demandé `--transaction
# buy`. Il faut donc filtrer POST-RÉPONSE sur le champ RENVOYÉ `adType`.
AD_TYPES_VENTE = ("buy", "prestige")
AD_TYPES_EXCLUS_VENTE = ("leaseback", "businessTakeOver", "rent")

# --- VENDEUR : particulier vs professionnel ---------------------------------
# CONSTAT RÉEL (flux JSON public, vérifié le 2026-10-10 sur Lyon 6e + France
# entière) : chaque annonce porte un champ BRUT `accountType` et un booléen
# BRUT `adCreatedByPro`. Valeurs PROFESSIONNELLES observées : 'agency'
# (agence), 'mandatary' (mandataire type iad/Capifrance), 'developer'
# (promoteur), 'broker', 'builder'. Le flux `realEstateAds.json` ne contient
# QUE des annonces pro (`adCreatedByPro == true` partout, 967 214 annonces
# France entière incluses) : les PARTICULIERS n'y sont PAS exposés.
#
# On ne DEVINE donc pas le vendeur : on lit `accountType`/`adCreatedByPro`
# renvoyés par l'API. `particulier` est VRAI seulement si l'annonce n'est pas
# marquée pro (adCreatedByPro faux) OU si son accountType est explicitement un
# type particulier. Sinon FAUX (pro/agence).
COMPTES_PRO = ("agency", "mandatary", "developer", "broker", "builder",
               "promoter", "professional")
COMPTES_PARTICULIER = ("privateIndividual", "private", "individual", "owner",
                       "particular", "particulier")

# Plafond de sûreté de pagination : nombre max de pages balayées quand tout=True
# (le total Bien'ici par zone reste largement sous 50 pages de 40 = 2000).
PAGES_MAX = 50

# Types Bien'ici acceptés par le flux. 'flat'=appartement, 'house'=maison,
# 'office'=bureau, 'commercial'=local commercial.
TYPES_VALIDES = ("flat", "house", "office", "commercial", "building", "parking")

# Traduction libellés FR (ou variantes usuelles) -> valeurs attendues par l'API.
# Le client et le CHEF raisonnent en français : on accepte donc les deux formes
# et on ramène tout à la valeur interne Bien'ici AVANT l'appel réseau.
TYPES_ALIAS = {
    "appartement": "flat", "appartements": "flat", "appart": "flat", "apparts": "flat",
    "flat": "flat", "flats": "flat",
    "maison": "house", "maisons": "house", "house": "house",
    "bureau": "office", "bureaux": "office", "office": "office",
    "local commercial": "commercial", "locaux commerciaux": "commercial",
    "commercial": "commercial", "commerce": "commercial",
    "immeuble": "building", "immeubles": "building", "building": "building",
    "parking": "parking", "garage": "parking", "stationnement": "parking",
}


def traduire_types(types: list[str] | None) -> list[str] | None:
    """Traduit les libellés FR (appartement, maison, bureau…) en valeurs API.

    Lève ConnectorError sur un type inconnu (jamais de 0 silencieux).
    """
    if not types:
        return None
    connus = ", ".join(TYPES_VALIDES)
    traduits: list[str] = []
    for t in types:
        cle = str(t).strip().lower()
        val = TYPES_ALIAS.get(cle)
        if val is None:
            raise ConnectorError(
                f"Type de bien inconnu : {t!r}. Types acceptes (FR ou API) : "
                f"{connus} — ex. 'appartement' (=flat), 'maison' (=house), 'bureau' (=office).")
        if val not in traduits:
            traduits.append(val)
    return traduits


def _now() -> str:
    return date.today().isoformat()


def est_particulier(brute: dict) -> bool:
    """Vrai si l'annonce BRUTE vient d'un PARTICULIER (pas d'une agence/pro).

    Décision basée UNIQUEMENT sur les champs renvoyés par l'API, jamais devinée :
      - `adCreatedByPro` == False        -> particulier (source la plus fiable) ;
      - sinon `accountType` explicite particulier -> particulier ;
      - sinon -> professionnel (agence/mandataire/promoteur…).
    Sur le flux `realEstateAds.json` actuel, TOUT est pro (voir note plus haut) :
    cette fonction renvoie donc False partout, ce qui est le constat honnête.
    """
    if brute.get("adCreatedByPro") is False:
        return True
    compte = str(brute.get("accountType") or "").strip().lower()
    if compte in COMPTES_PARTICULIER:
        return True
    return False


def _champ(valeur, source: str, fiabilite: str = "annonce") -> dict:
    """Enveloppe « donnée horodatée » du format partagé."""
    return {"valeur": valeur, "source": source, "fiabilite": fiabilite, "date": _now()}


def resoudre_zone(texte: str, *, timeout: int = 20) -> list[dict]:
    """Texte ('Lyon', 'Lyon 3e', '69003') -> zones candidates avec zoneIds.

    ⚠ OBLIGATOIRE avant toute recherche : sans zoneId, le flux Bien'ici ignore le
    filtre et renvoie la FRANCE ENTIÈRE (~42 000 annonces).
    """
    data = http_get_json(BIENICI_SUGGEST, params={
        "q": texte,
        "type": "city,delegated-city,department,postalCode,region,arrondissement",
    }, timeout=timeout)
    zones = []
    for z in (data if isinstance(data, list) else []):
        if not isinstance(z, dict):
            continue
        zones.append({
            "name": z.get("name"),
            "type": z.get("type"),
            "insee_code": z.get("insee_code"),
            "inner_codes": z.get("insee_codes"),
            "postal_codes": z.get("postalCodes"),
            "zoneIds": z.get("zoneIds"),
            "population": z.get("population"),
        })
    if not zones:
        raise ConnectorError(f"Aucune zone trouvee pour {texte!r}", url=BIENICI_SUGGEST)
    return zones


# Ordre de préférence des types de zone. Un ARRONDISSEMENT (delegated-city /
# arrondissement) est plus précis qu'une ville entière : si l'utilisateur écrit
# « Lyon 6e »/« Lyon 6 », il veut l'arrondissement, pas Lyon en entier. On passe
# donc arrondissement > city > postalCode > département > région.
_PREF_ZONE = {"delegated-city": 0, "arrondissement": 0, "city": 1,
              "postalCode": 2, "department": 3, "region": 4}


def _score_nom(nom: str | None, texte: str) -> int:
    """Pertinence d'un nom de zone vis-à-vis du texte saisi.

    Plus le texte ressemble au nom, plus le score est BAS (tri croissant).
    Évite qu'« arrondissement » correct (Lyon 6e) soit battu par un autre
    arrondissement plus peuplé (Lyon 3e) lors d'une recherche « Lyon 6 ».
    """
    if not nom:
        return 99
    n, t = nom.lower().strip(), texte.lower().strip()
    if n == t:
        return 0                      # correspondance exacte
    if n.startswith(t) or t.startswith(n):
        return 1                      # l'un préfixe l'autre
    # Sinon : nombre de mots/tokens partagés, pénalité sur la longueur d'écart.
    tokens_n, tokens_t = set(n.split()), set(t.split())
    communs = len(tokens_n & tokens_t)
    return 5 - communs


def _premier_zone_id(texte: str) -> str:
    """Meilleur zoneId pour un texte : bon arrondissement > ville > CP.

    Règles :
    - Si le texte vise un arrondissement (contient un numéro, ex. « Lyon 6 »),
      on privilégie l'arrondissement dont le nom colle au texte.
    - Sinon (« Lyon », « Marseille »), on privilégie la ville entière.
    - Départage final par pertinence du nom puis population décroissante.
    Évite et la dilution (« Lyon » entier pour « Lyon 6 ») et l'arrondissement
    erroné (« Lyon 3e » pour « Lyon 6 »).
    """
    zones = [z for z in resoudre_zone(texte) if z.get("zoneIds")]
    if not zones:
        raise ConnectorError(f"Zone {texte!r} sans zoneId exploitable", url=BIENICI_SUGGEST)

    vise_arrondissement = any(c.isdigit() for c in texte)

    def cle(z: dict):
        t = z.get("type")
        if t in ("delegated-city", "arrondissement") and not vise_arrondissement:
            pref = 2          # arrondissement dépriorisé si aucun numéro saisi
        else:
            pref = _PREF_ZONE.get(t, 9)
        return (pref, _score_nom(z.get("name"), texte), -(z.get("population") or 0))

    zones.sort(key=cle)
    return zones[0]["zoneIds"][0]


def _date_ok(v) -> str | None:
    """Bien'ici met parfois 1970-01-01 (date d'origine absente) -> None."""
    if not v:
        return None
    s = str(v)[:10]
    return None if s.startswith("1970") else s


def _normaliser(a: dict) -> dict:
    """Réduit une annonce Bien'ici à la fiche normalisée (format partagé)."""
    prix = a.get("price")
    if isinstance(prix, list):
        prix = prix[0] if prix else None
    if not isinstance(prix, (int, float)):
        prix = None
    surf = a.get("surfaceArea")
    if not isinstance(surf, (int, float)):
        surf = None
    prix_m2 = round(prix / surf, 1) if (prix and surf) else None
    dist = a.get("district") or {}
    ville = a.get("city")
    slug = (str(ville or "").lower().replace(" ", "-")
            .replace("è", "e").replace("é", "e").replace("'", "-"))
    trans = "location" if a.get("adType") == "rent" else "vente"
    aid = a.get("id")
    url = f"https://www.bienici.com/annonce/{trans}/{slug}/{aid}" if aid else None
    quartier = dist.get("libelle") if isinstance(dist, dict) else None
    return {
        "id": f"bienici:{aid}" if aid else None,
        "titre": a.get("title"),
        "type": a.get("propertyType"),
        "transaction": a.get("adType"),
        "ville": ville,
        "code_postal": a.get("postalCode"),
        "quartier": quartier,
        "surface": _champ(surf, "Bien'ici") if surf is not None else
                   {"valeur": None, "source": None, "fiabilite": "a_verifier", "date": _now()},
        "prix": _champ(prix, "Bien'ici") if prix is not None else
                {"valeur": None, "source": None, "fiabilite": "a_verifier", "date": _now()},
        "prix_m2": _champ(prix_m2, "calcul") if prix_m2 is not None else None,
        "pieces": a.get("roomsQuantity"),
        "etage": a.get("floor"),
        "rdc": a.get("floor") == 0,
        "ascenseur": a.get("hasElevator"),
        "cave": a.get("hasCellar"),
        "dpe": a.get("energyClassification"),
        "ges": a.get("greenhouseGazClassification"),
        "charges": a.get("charges"),
        "agence": a.get("accountDisplayName"),
        "compte_type": a.get("accountType"),
        "vendeur": "particulier" if est_particulier(a) else "agence",
        "particulier": est_particulier(a),
        "url_annonce": url,
        "source_portail": "Bien'ici",
        "date_modification": _date_ok(a.get("modificationDate")),
        "date_mise_en_vente": _date_ok(a.get("publicationDate")),
        "prix_baisse": bool(a.get("priceHasDecreased")),
        "date_detection": _now(),
    }


def chercher_annonces(*, zone: str, transaction: str = "buy",
                      types: list[str] | None = None,
                      surface_min: float | None = None,
                      surface_max: float | None = None,
                      prix_min: float | None = None,
                      prix_max: float | None = None,
                      pieces_min: int | None = None,
                      rdc_seulement: bool = False,
                      type_vendeur: str = "tous",
                      taille: int = 40, offset: int = 0,
                      pages: int | None = None,
                      tout: bool = True,
                      filtrer_transaction: bool = True) -> dict:
    """Annonces Bien'ici filtrées pour une zone (nom/CP/arrondissement).

    transaction : 'buy' (vente) | 'rent' (location).
    types       : ['appartement','maison','bureau', ...] — libellés FR ou
                  valeurs API ('flat','house','office', ...) (None = tous).
                  Un type inconnu lève ConnectorError (jamais 0 silencieux).
    type_vendeur: 'tous' | 'particulier' | 'agence'. Filtre POST-RÉPONSE sur le
                  vendeur lu dans `accountType`/`adCreatedByPro` (jamais deviné).
                  ⚠ Le flux public Bien'ici ne renvoie que des PROS : avec
                  'particulier' le résultat est donc généralement VIDE (constat
                  honnête — voir docs/prioriser-particuliers.md). Les particuliers
                  arrivent par la voie alerte e-mail (outils/alerte_email.py).

    PAGINATION (correction P1) :
      Le flux ne rend qu'une page (`taille`, défaut 40). On BOUCLE désormais
      sur `from` (= offset + n*taille) pour agréger TOUT le résultat.
      - tout=True (défaut)  : balaie toutes les pages jusqu'à épuisement du
                              `total` annoncé par l'API (plafond de sûreté).
      - tout=False          : ne lit qu'une seule page (compat ancien comportement).
      - pages=N             : force un nombre maximal de pages (prime sur `tout`).
      - offset              : page de départ (from initial), pour reprendre.
      Une BOUCLE à résultat vide répétée est bornée et détectée (anti-boucle).

    FILTRE POST-RÉPONSE (correction P2) :
      Même avec `filterType: 'buy'`, l'API renvoie des cessions de bail
      (`adType == 'leaseback'`) et des reprises de fonds (`businessTakeOver`).
      Quand transaction == 'buy' et filtrer_transaction=True, on EXCLUT
      post-réponse tout ce qui n'est pas une vraie vente (voir AD_TYPES_VENTE).
      Pour transaction == 'rent', on ne garde que `adType == 'rent'`.

    Retour      : enveloppe partagée (tache/statut/resultat/sources/erreurs/date).
    """
    if transaction not in ("buy", "rent"):
        raise ConnectorError("transaction doit etre 'buy' ou 'rent'")
    if type_vendeur not in ("tous", "particulier", "agence"):
        raise ConnectorError(
            "type_vendeur doit etre 'tous', 'particulier' ou 'agence'")
    types_api = traduire_types(types)
    zone_id = _premier_zone_id(zone)

    def _page(from_: int) -> dict:
        filtres: dict = {
            "size": taille, "from": from_, "filterType": transaction,
            "onTheMarket": [True], "zoneIdsByTypes": {"zoneIds": [zone_id]},
        }
        if types_api:
            filtres["propertyType"] = types_api
        if prix_min is not None:
            filtres["minPrice"] = prix_min
        if prix_max is not None:
            filtres["maxPrice"] = prix_max
        if surface_min is not None:
            filtres["minArea"] = surface_min
        if surface_max is not None:
            filtres["maxArea"] = surface_max
        if pieces_min is not None:
            filtres["minRooms"] = pieces_min
        data = http_get_json(BIENICI_SEARCH, params={
            "filters": json.dumps(filtres, separators=(",", ":")),
        }, timeout=30)
        if not isinstance(data, dict):
            raise ConnectorError("Reponse Bien'ici inattendue", url=BIENICI_SEARCH)
        return data

    # --- PAGINATION -------------------------------------------------------
    if pages is not None:
        max_pages = max(1, pages)
    elif tout:
        max_pages = PAGES_MAX          # plafond de sûreté (balayage complet)
    else:
        max_pages = 1                  # compat : une seule page

    def _garde_transaction(a: dict) -> bool:
        """Vrai si l'annonce BRUTE correspond bien à la transaction demandée."""
        if not filtrer_transaction:
            return True
        adtype = a.get("adType")
        if transaction == "buy":
            return adtype in AD_TYPES_VENTE
        return adtype == "rent"        # rent

    brutes: list[dict] = []
    total_declare = None
    nb_brutes_exclues = 0
    from_ = offset
    page_no = 0
    while page_no < max_pages:
        data = _page(from_)
        if total_declare is None:
            total_declare = data.get("total")
        ads = data.get("realEstateAds") or []
        if not ads:
            break                       # épuisé
        brutes.extend(ads)
        page_no += 1
        from_ += taille
        # Stop si on a atteint le total annoncé (évite une page vide en trop).
        if isinstance(total_declare, int) and len(brutes) >= total_declare:
            break
        if len(ads) < taille:
            break                       # dernière page partielle

    # --- FILTRE POST-RÉPONSE sur adType/transaction RENVOYÉ ---------------
    annonces = []
    nb_brutes_exclues = 0
    nb_particuliers = 0
    nb_agences = 0
    for a in brutes:
        if not _garde_transaction(a):
            nb_brutes_exclues += 1
            continue
        if rdc_seulement and a.get("floor") != 0:
            continue
        est_partic = est_particulier(a)
        if est_partic:
            nb_particuliers += 1
        else:
            nb_agences += 1
        if type_vendeur == "particulier" and not est_partic:
            continue
        if type_vendeur == "agence" and est_partic:
            continue
        annonces.append(_normaliser(a))

    notes = ["Prix AFFICHE (declare) — croiser avec DVF pour le prix reel du marche."]
    if tout or pages is not None:
        notes.append(f"Pagination : {page_no} page(s) balayee(s), "
                     f"{len(brutes)} annonces brutes agregees.")
    if filtrer_transaction:
        notes.append(
            "Filtre POST-REPONSE sur adType : ventes de murs uniquement "
            f"({', '.join(AD_TYPES_VENTE)}). "
            f"{nb_brutes_exclues} annonce(s) ecartee(s) (cession de bail "
            "leaseback / reprise businessTakeOver / location).")
    if rdc_seulement:
        notes.append("Filtre RDC applique en local (floor == 0).")
    if type_vendeur != "tous":
        notes.append(
            f"Filtre VENDEUR '{type_vendeur}' applique en local (champ accountType/"
            "adCreatedByPro). "
            f"{nb_particuliers} annonce(s) particulier(e), {nb_agences} agence(s)/pro "
            "parmi les annonces retenues par transaction.")
        if type_vendeur == "particulier" and nb_particuliers == 0:
            notes.append(
                "AUCUN particulier dans cette zone : le flux public Bien'ici "
                "n'expose que des annonces PRO (constat verifie). Pour cibler "
                "les particuliers, utiliser l'alerte e-mail (outils/alerte_email.py).")

    return {
        "tache": "collecte-annonces",
        "statut": "ok" if annonces else "partiel",
        "entree": {"zone": zone, "zone_id": zone_id, "transaction": transaction,
                   "types": types, "surface_min": surface_min, "surface_max": surface_max,
                   "prix_min": prix_min, "prix_max": prix_max, "rdc_seulement": rdc_seulement,
                   "type_vendeur": type_vendeur,
                   "pages": page_no, "tout": tout, "offset": offset},
        "resultat": {
            "zone": zone, "zone_id": zone_id,
            "total_correspondant": total_declare,
            "nb_pages": page_no,
            "nb_brutes": len(brutes),
            "nb_exclues_transaction": nb_brutes_exclues,
            "nb_particuliers": nb_particuliers,
            "nb_agences": nb_agences,
            "nb_annonces": len(annonces),
            "annonces": annonces,
        },
        "sources": ["Bien'ici"],
        "erreurs": [],
        "notes": notes,
        "date": _now(),
    }


# Alias bibliothèque (compatibilité avec le nom du contrat v1).
chercher_bienici = chercher_annonces


def chercher_seloger_playwright(url: str = SELOGER_PRO_LYON, *, timeout_s: int = 90) -> dict:
    """SeLoger par navigateur — USAGE MODÉRÉ (robots restrictif). Jamais de martèlement.

    ⚠ N'EST PAS UTILISÉ en voie n°1. Bien'ici (flux JSON) suffit dans la majorité
    des cas. Ce chemin exige Playwright (dépendance externe, non stdlib).
    """
    raise ConnectorError(
        "SeLoger via Playwright : voie moderee, non activee par defaut "
        "(installer Playwright dans un venv dedie avant usage).",
        url=url)


def _cli() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Annonces Bien'ici (flux JSON public)")
    sub = p.add_subparsers(dest="cmd")

    pz = sub.add_parser("zone", help="resoudre une zone -> zoneIds")
    pz.add_argument("texte")

    pa = sub.add_parser("annonces", help="chercher des annonces")
    pa.add_argument("--zone", required=True)
    pa.add_argument("--transaction", default="buy", choices=["buy", "rent"])
    pa.add_argument("--types", nargs="*", default=None)
    pa.add_argument("--surface-min", type=float, default=None)
    pa.add_argument("--surface-max", type=float, default=None)
    pa.add_argument("--prix-min", type=float, default=None)
    pa.add_argument("--prix-max", type=float, default=None)
    pa.add_argument("--pieces-min", type=int, default=None)
    pa.add_argument("--rdc", action="store_true")
    pa.add_argument("--particuliers-seulement", dest="type_vendeur",
                    action="store_const", const="particulier", default="tous",
                    help="ne garder QUE les annonces de particuliers (hors agence)")
    pa.add_argument("--type-vendeur", dest="type_vendeur", default=None,
                    choices=["tous", "particulier", "agence"],
                    help="filtre vendeur explicite (prime sur --particuliers-seulement)")
    # Pagination : par défaut on balaie TOUT (multi-pages agrégées).
    pa.add_argument("--pages", type=int, default=None,
                    help="nombre max de pages de 40 à balayer (prime sur --tout)")
    pa.add_argument("--une-page", dest="tout", action="store_false", default=True,
                    help="ne lire qu'une seule page (40 annonces) — ancien comportement")
    pa.add_argument("--offset", type=int, default=0,
                    help="index de départ (from) pour reprendre un balayage")
    pa.add_argument("--sans-filtre-transaction", dest="filtrer_transaction",
                    action="store_false", default=True,
                    help="ne PAS filtrer post-réponse sur adType (garder leaseback etc.)")

    sub.add_parser("seloger", help="SeLoger (usage modere, non active)")

    args = p.parse_args()
    try:
        if args.cmd == "zone":
            print(json.dumps(resoudre_zone(args.texte), ensure_ascii=False, indent=2))
        elif args.cmd == "annonces":
            type_vendeur = args.type_vendeur or "tous"
            res = chercher_annonces(
                zone=args.zone, transaction=args.transaction, types=args.types,
                surface_min=args.surface_min, surface_max=args.surface_max,
                prix_min=args.prix_min, prix_max=args.prix_max,
                pieces_min=args.pieces_min, rdc_seulement=args.rdc,
                type_vendeur=type_vendeur,
                pages=args.pages, tout=args.tout, offset=args.offset,
                filtrer_transaction=args.filtrer_transaction)
            print(json.dumps(res, ensure_ascii=False, indent=2))
        elif args.cmd == "seloger":
            print(json.dumps(chercher_seloger_playwright(), ensure_ascii=False, indent=2))
        else:
            p.print_help()
            return 2
        return 0
    except ConnectorError as exc:
        print(json.dumps(json_error(str(exc), url=exc.url), ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(_cli())
