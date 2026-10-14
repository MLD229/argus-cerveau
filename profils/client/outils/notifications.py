"""Notifications — magasin partagé des événements Argus.

OBJECTIF PRODUIT
----------------
Les événements de veille (nouvelles annonces, baisses de prix, ventes, alertes
portail) doivent devenir des NOTIFICATIONS consultables :
  - par le CLIENT dans l'app web (badge + panneau), et
  - par l'AGENT (« chef, quelles notifications a-t-on reçues ? »).

ARCHITECTURE
------------
Un seul magasin JSON, partagé admin <-> client via le volume Hermes :
  défaut : <ARGUS_NOTIFS_FILE> ou /home/hermeswebui/.hermes/argus-notifications.json
  (surchargeable par la variable d'environnement ARGUS_NOTIFS_FILE, pratique
  pour les tests et côté hôte : ./deploy/notifs.json).

Écriture ATOMIQUE (tmp + os.replace) : un lecteur concurrent ne voit jamais un
fichier à moitié écrit. Chaque notification a un id déterministe (uuid4) et une
clé de dédoublonnage optionnelle (cle_dedup) pour ne pas notifier deux fois le
même fait (ex. même annonce).

CONTRAT CLI (identique aux autres outils)
-----------------------------------------
  python3 outils/notifications.py ajouter --type annonce --titre "..." \
      --corps "..." --source "Bien'ici" [--severite important] [--dedup <cle>]
  python3 outils/notifications.py lister [--non-lues] [--type annonce] [--limite 50]
  python3 outils/notifications.py marquer-lu --id <id> | --tous
  python3 outils/notifications.py resume        # compteurs (pour le badge)
  python3 outils/notifications.py purge --jours 90

Sortie : enveloppe §4.1 (JSON). Échec : {"erreur": ...} + code 2.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from datetime import date, datetime, timedelta

TYPES = ("annonce", "vente", "alerte", "marche", "systeme")
SEVERITES = ("info", "important", "urgent")

# Chemin du magasin, choisi automatiquement selon le contexte :
#   - conteneur : /opt/argus-notifs (bind-mount partagé, uid 1000)
#   - hôte (momo) : ~/.hermes/argus-notifs (même dossier physique via le bind)
#   - sinon : ~/.hermes/argus-notifications.json (repli local)
# Surchargeable par ARGUS_NOTIFS_FILE (tests, scripts).
_HOME = os.path.expanduser("~")


def _fichier_defaut() -> str:
    if os.path.isdir("/opt/argus-notifs"):
        return "/opt/argus-notifs/notifications.json"
    d = os.path.join(_HOME, ".hermes", "argus-notifs")
    if os.path.isdir(d):
        return os.path.join(d, "notifications.json")
    return os.path.join(_HOME, ".hermes", "argus-notifications.json")


FILE_DEFAUT = _fichier_defaut()
MAX_NOTIFS = 2000  # borne de rétention dure (au-delà, on élague les plus vieilles)


class NotifError(RuntimeError):
    """Erreur claire du magasin de notifications."""


def _fichier() -> str:
    return os.environ.get("ARGUS_NOTIFS_FILE", FILE_DEFAUT)


def _lire() -> dict:
    p = _fichier()
    if not os.path.exists(p):
        return {"notifications": [], "vues": {}}
    try:
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise NotifError(f"Magasin illisible ({p}): {exc}") from exc
    d.setdefault("notifications", [])
    d.setdefault("vues", {})
    return d


def _ecrire(d: dict) -> None:
    """Écriture atomique : tmp dans le même dossier puis os.replace."""
    p = _fichier()
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    # élaguer si trop de notifications
    notifs = d.get("notifications", [])
    if len(notifs) > MAX_NOTIFS:
        d["notifications"] = notifs[-MAX_NOTIFS:]
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
        # Le magasin est partagé entre l'agent (uid 1000) et le système : on
        # s'assure qu'il reste LISIBLE (644). Le propriétaire ne peut pas être
        # changé sans privilège, mais si le fichier a été créé par un process
        # root (ex. docker exec), l'agent ne pourrait pas le lire -> on le
        # signale par le mode. Le chown réel est fait au déploiement.
        # Le magasin est partagé entre l'agent (uid 10000) et l'HÔTE (uid 1000,
        # serveur web de l'interface). Un mode 644 rendrait le fichier
        # non inscriptible pour l'autre côté -> on force 666 : c'est un magasin
        # de notifications, aucune donnée sensible, et les deux doivent écrire.
        try:
            os.chmod(p, 0o666)
        except OSError:
            pass
    except OSError as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise NotifError(f"Écriture impossible ({p}): {exc}") from exc


def _maintenant() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


# ---------------------------------------------------------------- API métier
def ajouter(*, type: str, titre: str, corps: str, source: str,
            donnees: dict | None = None, severite: str = "info",
            cle_dedup: str | None = None) -> dict:
    """Ajoute une notification. Idempotent si cle_dedup est fournie.

    Retour : {"ajoutee": bool, "notification": {...}} — si la clé existe déjà,
    ajoutee=False et la notification existante est retournée.
    """
    if type not in TYPES:
        raise NotifError(f"type invalide: {type!r} (attendu: {', '.join(TYPES)})")
    if severite not in SEVERITES:
        raise NotifError(f"severite invalide: {severite!r} (attendu: {', '.join(SEVERITES)})")
    if not titre or not str(titre).strip():
        raise NotifError("titre vide : refuse de créer une notification sans titre.")

    d = _lire()
    if cle_dedup:
        for n in d["notifications"]:
            if n.get("cle_dedup") == cle_dedup:
                return {"ajoutee": False, "notification": n}

    notif = {
        "id": uuid.uuid4().hex[:12],
        "type": type,
        "severite": severite,
        "titre": str(titre).strip(),
        "corps": (corps or "").strip(),
        "source": source,
        "donnees": donnees or {},
        "cle_dedup": cle_dedup,
        "cree_le": _maintenant(),
        "lu": False,
    }
    d["notifications"].append(notif)
    _ecrire(d)
    return {"ajoutee": True, "notification": notif}


def lister(*, non_lues: bool = False, type: str | None = None,
           severite: str | None = None, limite: int = 50) -> dict:
    """Liste les notifications (les plus récentes d'abord)."""
    d = _lire()
    notifs = list(reversed(d["notifications"]))
    if non_lues:
        notifs = [n for n in notifs if not n.get("lu")]
    if type:
        notifs = [n for n in notifs if n.get("type") == type]
    if severite:
        notifs = [n for n in notifs if n.get("severite") == severite]
    total = len(notifs)
    notifs = notifs[:limite]
    return {
        "tache": "notifications-lister",
        "statut": "ok",
        "entree": {"non_lues": non_lues, "type": type, "severite": severite, "limite": limite},
        "resultat": {"notifications": notifs, "nb": total,
                     "nb_non_lues": sum(1 for n in d["notifications"] if not n.get("lu"))},
        "sources": ["magasin local argus-notifications.json"],
        "erreurs": [],
        "date": date.today().isoformat(),
    }


def resume() -> dict:
    """Compteurs pour le badge web + réponse rapide à l'agent."""
    d = _lire()
    notifs = d["notifications"]
    par_type: dict[str, int] = {}
    par_sev: dict[str, int] = {}
    non_lues = 0
    for n in notifs:
        par_type[n.get("type", "?")] = par_type.get(n.get("type", "?"), 0) + 1
        par_sev[n.get("severite", "?")] = par_sev.get(n.get("severite", "?"), 0) + 1
        if not n.get("lu"):
            non_lues += 1
    plus_recente = notifs[-1]["cree_le"] if notifs else None
    return {
        "tache": "notifications-resume",
        "statut": "ok",
        "resultat": {"total": len(notifs), "non_lues": non_lues,
                     "par_type": par_type, "par_severite": par_sev,
                     "plus_recente": plus_recente},
        "sources": ["magasin local argus-notifications.json"],
        "erreurs": [],
        "date": date.today().isoformat(),
    }


def marquer_lu(*, id: str | None = None, tous: bool = False) -> dict:
    """Marque une notification (ou toutes) comme lue."""
    if not id and not tous:
        raise NotifError("marquer-lu : fournir --id <id> ou --tous.")
    d = _lire()
    n_modifs = 0
    for n in d["notifications"]:
        if tous or n.get("id") == id:
            if not n.get("lu"):
                n["lu"] = True
                n["lu_le"] = _maintenant()
                n_modifs += 1
    if id and n_modifs == 0 and not any(n.get("id") == id for n in d["notifications"]):
        raise NotifError(f"notification introuvable: {id}")
    _ecrire(d)
    return {
        "tache": "notifications-marquer-lu",
        "statut": "ok",
        "resultat": {"modifiees": n_modifs},
        "sources": ["magasin local argus-notifications.json"],
        "erreurs": [],
        "date": date.today().isoformat(),
    }


def purge(*, jours: int = 90) -> dict:
    """Supprime les notifications plus vieilles que N jours."""
    d = _lire()
    seuil = (datetime.now() - timedelta(days=jours)).replace(microsecond=0).isoformat()
    avant = len(d["notifications"])
    d["notifications"] = [n for n in d["notifications"] if n.get("cree_le", "") >= seuil]
    _ecrire(d)
    return {
        "tache": "notifications-purge",
        "statut": "ok",
        "resultat": {"supprimees": avant - len(d["notifications"]),
                     "restantes": len(d["notifications"])},
        "sources": ["magasin local argus-notifications.json"],
        "erreurs": [],
        "date": date.today().isoformat(),
    }


# ------------------------------------------------------------------- CLI
def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Magasin de notifications Argus.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ajouter", help="ajouter une notification")
    a.add_argument("--type", required=True, choices=TYPES)
    a.add_argument("--titre", required=True)
    a.add_argument("--corps", default="")
    a.add_argument("--source", required=True)
    a.add_argument("--severite", default="info", choices=SEVERITES)
    a.add_argument("--dedup", default=None, help="clé de dédoublonnage")

    l = sub.add_parser("lister", help="lister les notifications")
    l.add_argument("--non-lues", action="store_true")
    l.add_argument("--type", default=None, choices=TYPES)
    l.add_argument("--severite", default=None, choices=SEVERITES)
    l.add_argument("--limite", type=int, default=50)

    sub.add_parser("resume", help="compteurs (badge)")

    m = sub.add_parser("marquer-lu", help="marquer comme lue")
    m.add_argument("--id", default=None)
    m.add_argument("--tous", action="store_true")

    p = sub.add_parser("purge", help="purger les anciennes")
    p.add_argument("--jours", type=int, default=90)

    args = ap.parse_args(argv)
    try:
        if args.cmd == "ajouter":
            out = ajouter(type=args.type, titre=args.titre, corps=args.corps,
                          source=args.source, severite=args.severite,
                          cle_dedup=args.dedup)
        elif args.cmd == "lister":
            out = lister(non_lues=args.non_lues, type=args.type,
                         severite=args.severite, limite=args.limite)
        elif args.cmd == "resume":
            out = resume()
        elif args.cmd == "marquer-lu":
            out = marquer_lu(id=args.id, tous=args.tous)
        elif args.cmd == "purge":
            out = purge(jours=args.jours)
        else:
            raise NotifError(f"commande inconnue: {args.cmd}")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    except NotifError as exc:
        print(json.dumps({"erreur": str(exc), "etape": "notifications"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(_main())
