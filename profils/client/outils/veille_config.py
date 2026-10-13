"""Veille — configuration réglable (filtre de pertinence + fréquence).

OBJECTIF
--------
Permettre de régler, SANS toucher au code, ce que la veille notifie et à quelle
fréquence — piloté depuis un panneau dans l'interface. La config vit dans un
fichier JSON partagé (comme le magasin de notifications) :

    <ARGUS_VEILLE_CONFIG> ou ~/.hermes/argus-notifs/veille-config.json

CONTENU
-------
{
  "intervalle_s": 300,                  # fréquence du service (secondes)
  "zones": ["Lyon 1", ...],             # zones surveillées
  "limite": 40,                         # annonces max par zone et par passe
  "filtre": {
      "actif": true,                    # appliquer ou non le filtre de pertinence
      "exclure_mots": ["parking", "garage", "box", "boutique", "fonds de commerce",
                       "cession de bail", "droit au bail", "restaurant"],
      "surface_min": 30,
      "surface_max": 200,
      "rdc_prioritaire": true
  }
}

Le filtre est CONSERVATEUR : il ne rejette un bien que s'il matche un mot exclu
OU sort des bornes de surface. Il ne prétend pas qualifier finement (ça, c'est
l'agent) — il évite juste le gros bruit (parkings, box, boutiques).

Aucune dépendance. Écriture atomique. Repli : si le fichier est absent ou
illisible, on renvoie une config par défaut (jamais d'échec bloquant).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unicodedata
from datetime import date

CONFIG_DEFAUT = {
    "intervalle_s": 300,
    "zones": ["Lyon 1", "Lyon 2", "Lyon 3", "Lyon 6", "Lyon 7", "Villeurbanne"],
    "limite": 2000,
    "filtre": {
        "actif": True,
        # Types de bien RETENUS — valeurs RÉELLES renvoyées par Bien'ici
        # (constatées : flat, office, premises, loft, shop). `premises` = locaux
        # professionnels/commerciaux (68 sur un échantillon), `shop` = boutique.
        # On EXCLUT : house (maison), parking, programme (neuf), terrain,
        # building (immeuble entier), unknown — hors cible « cabinet ».
        "types": ["flat", "office", "premises", "loft", "shop"],
        "exclure_mots": ["parking", "garage", "box", "boutique", "fonds de commerce",
                         "cession de bail", "droit au bail", "restaurant", "local commercial vide"],
        "surface_min": 30,
        "surface_max": 200,
        "rdc_prioritaire": True,
    },
}


class ConfigError(RuntimeError):
    """Erreur claire de configuration (jamais un crash silencieux)."""


def _fichier() -> str:
    return os.environ.get(
        "ARGUS_VEILLE_CONFIG",
        os.path.expanduser("~/.hermes/argus-notifs/veille-config.json"),
    )


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", (t or "").lower()).encode("ascii", "ignore").decode()


def lire() -> dict:
    """Lit la config ; repli sur la config par défaut si absente/illisible.

    Fusionne avec les défauts pour ne jamais manquer une clé.
    """
    p = _fichier()
    base = json.loads(json.dumps(CONFIG_DEFAUT))  # copie profonde
    if not os.path.exists(p):
        return base
    try:
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return base
    if isinstance(d, dict):
        for k, v in d.items():
            if k == "filtre" and isinstance(v, dict):
                base["filtre"].update(v)
            else:
                base[k] = v
    return base


def ecrire(cfg: dict) -> dict:
    """Écrit la config (fusionnée avec les défauts), atomiquement."""
    base = lire()
    for k, v in (cfg or {}).items():
        if k == "filtre" and isinstance(v, dict):
            base["filtre"].update(v)
        else:
            base[k] = v
    p = _fichier()
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(base, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except OSError as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise ConfigError(f"écriture config impossible ({p}): {exc}") from exc
    return base


def pertinente(annonce: dict, cfg: dict | None = None) -> tuple[bool, str]:
    """Un bien est-il dans le périmètre de la veille ? (filtre conservateur)

    Retour : (garder, raison). Raison vide si gardé.

    Le filtre s'appuie sur DEUX signaux :
    - le champ `type` de l'annonce (fiable, jamais vide côté Bien'ici) ;
    - le texte (titre/type/quartier/ville) pour les mots exclus.
    AVANT : seul le texte était testé -> un parking à titre vide passait, et les
    maisons/T5 hors cible aussi. On filtre désormais par TYPE métier d'abord.
    """
    cfg = cfg or lire()
    f = cfg.get("filtre", {})
    if not f.get("actif", True):
        return True, ""

    # --- 1. TYPE de bien : filtre principal, fiable -------------------------
    types_ok = [str(t).strip().lower() for t in f.get("types", []) if str(t).strip()]
    if types_ok:
        t = str(annonce.get("type") or "").strip().lower()
        if t and t not in types_ok:
            return False, f"type « {t} » hors cible"

    texte = _norm(" ".join(str(x) for x in (
        annonce.get("titre"), (annonce.get("type") or ""),
        annonce.get("quartier"), annonce.get("ville"),
    ) if x))

    # --- 2. MOTS EXCLUS : borne le bruit résiduel ---------------------------
    for mot in f.get("exclure_mots", []):
        if _norm(mot) in texte:
            return False, f"mot exclu « {mot} »"

    # --- 3. SURFACE : bornes métier ----------------------------------------
    surf = (annonce.get("surface") or {}).get("valeur")
    if isinstance(surf, (int, float)):
        smin, smax = f.get("surface_min", 0), f.get("surface_max", 10**9)
        if surf < smin or surf > smax:
            return False, f"surface {surf} hors [{smin},{smax}]"

    return True, ""


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Config de la veille Argus (filtre + fréquence).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("lire", help="afficher la config courante")
    sub.add_parser("defauts", help="afficher les défauts")

    e = sub.add_parser("ecrire", help="mettre à jour la config (JSON partiel)")
    e.add_argument("--json", required=True, help="JSON à fusionner, ex. '{\"intervalle_s\":600}'")

    p = sub.add_parser("pertinente", help="tester le filtre sur une annonce (JSON)")
    p.add_argument("--annonce", required=True, help="JSON d'une annonce normalisée")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "lire":
            out = {"tache": "veille-config", "statut": "ok", "resultat": lire(),
                   "sources": [_fichier()], "erreurs": [], "date": date.today().isoformat()}
        elif args.cmd == "defauts":
            out = {"tache": "veille-config", "statut": "ok", "resultat": CONFIG_DEFAUT,
                   "sources": [], "erreurs": [], "date": date.today().isoformat()}
        elif args.cmd == "ecrire":
            maj = json.loads(args.json)
            out = {"tache": "veille-config", "statut": "ok", "resultat": ecrire(maj),
                   "sources": [_fichier()], "erreurs": [], "date": date.today().isoformat()}
        elif args.cmd == "pertinente":
            annonce = json.loads(args.annonce)
            garder, raison = pertinente(annonce)
            out = {"tache": "veille-filtre", "statut": "ok",
                   "resultat": {"garder": garder, "raison": raison},
                   "sources": [], "erreurs": [], "date": date.today().isoformat()}
        else:
            raise ConfigError(f"commande inconnue : {args.cmd}")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    except (ConfigError, json.JSONDecodeError) as exc:
        print(json.dumps({"erreur": str(exc), "etape": "veille-config"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(_main())
