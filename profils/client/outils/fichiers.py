"""Fichiers — dépôt et rappel de fichiers/images dans le sous-cerveau Argus.

OBJECTIF
--------
Le client dit « stocke-moi ce fichier / cette image, tu me le ressortiras plus
tard ». Ce module gère un dépôt de fichiers rattaché au sous-cerveau (vault) :

    <VAULT>/60_FICHIERS/<id>-<slug>.<ext>   (le fichier)
    <VAULT>/60_FICHIERS/_INDEX.json          (l'index : métadonnées + mots-clés)

L'index est la « mémoire » : chaque fichier y porte un id, un titre, une
description, des mots-clés, sa date, sa source et son type. Pour « ressortir »
un fichier, l'agent CHERCHE dans l'index (par mot-clé/texte) puis lit le chemin.

POURQUOI L'INDEX (et pas juste un dossier)
------------------------------------------
Un dossier brut ne permet pas à l'agent de « se souvenir » du fichier : il ne
sait pas qu'il existe ni à quoi il sert. L'index donne des métadonnées
cherchables -> l'agent retrouve le bon fichier à partir d'une question.

VAULT
-----
Le chemin du vault est /data/vault dans le conteneur (montage), surchargeable
par ARGUS_VAULT_DIR. Le sous-dossier est 60_FICHIERS.

CONTRAT CLI
-----------
  python3 outils/fichiers.py deposer --chemin /tmp/photo.jpg --titre "Vitrine Lyon 6"
      --description "photo de la vitrine du local rue Sully" --mots-cles vitrine,local,sully
  python3 outils/fichiers.py chercher --q sully
  python3 outils/fichiers.py lister
  python3 outils/fichiers.py montrer <id>        # renvoie le chemin réel du fichier

Sortie : enveloppe §4.1 (JSON). Échec : {"erreur": ...} + code 2.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import unicodedata
import uuid
from datetime import date, datetime

VAULT_DEFAUT = os.environ.get("ARGUS_VAULT_DIR", "/data/vault")
SOUS_DOSSIER = "60_FICHIERS"

# Types de fichiers qu'on accepte de déposer (garde-fou doux : on prévient
# pour le reste, mais on n'interdit pas).
EXT_IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".heic", ".bmp"}
EXT_DOCS = {".pdf", ".txt", ".md", ".csv", ".json", ".doc", ".docx", ".xls", ".xlsx", ".odt"}


class FichierError(RuntimeError):
    """Erreur claire du dépôt de fichiers (jamais un crash silencieux)."""


def _vault() -> str:
    return os.environ.get("ARGUS_VAULT_DIR", VAULT_DEFAUT)


def _dossier() -> str:
    return os.path.join(_vault(), SOUS_DOSSIER)


def _index_path() -> str:
    return os.path.join(_dossier(), "_INDEX.json")


def _slug(texte: str) -> str:
    texte = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode()
    texte = re.sub(r"[^\w\s-]", "", texte).strip().lower()
    return re.sub(r"[\s_]+", "-", texte)[:50] or "fichier"


def _lire_index() -> dict:
    p = _index_path()
    if not os.path.exists(p):
        return {"fichiers": []}
    try:
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise FichierError(f"Index illisible ({p}): {exc}") from exc
    d.setdefault("fichiers", [])
    return d


def _ecrire_index(d: dict) -> None:
    p = _index_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def deposer(*, chemin: str, titre: str, description: str = "",
            mots_cles: list[str] | None = None, source: str = "",
            type_fichier: str | None = None) -> dict:
    """Copie un fichier dans le vault et l'indexe.

    Le fichier source n'est PAS supprimé (on copie). Retourne l'entrée d'index.
    """
    if not chemin or not os.path.isfile(chemin):
        raise FichierError(f"fichier introuvable : {chemin!r}")
    if not titre or not titre.strip():
        raise FichierError("titre vide : refuse d'indexer un fichier sans titre.")

    os.makedirs(_dossier(), exist_ok=True)
    ext = os.path.splitext(chemin)[1].lower()
    ident = uuid.uuid4().hex[:8]
    nom_cible = f"{ident}-{_slug(titre)}{ext}"
    cible = os.path.join(_dossier(), nom_cible)

    try:
        shutil.copy2(chemin, cible)
    except OSError as exc:
        raise FichierError(f"copie impossible vers le vault : {exc}") from exc

    if type_fichier is None:
        type_fichier = "image" if ext in EXT_IMAGES else ("document" if ext in EXT_DOCS else "autre")

    entree = {
        "id": ident,
        "titre": titre.strip(),
        "description": (description or "").strip(),
        "mots_cles": [m.strip().lower() for m in (mots_cles or []) if m.strip()],
        "type": type_fichier,
        "ext": ext,
        "fichier": nom_cible,
        "chemin": cible,
        "taille_octets": os.path.getsize(cible),
        "source": source or "client",
        "depose_le": datetime.now().replace(microsecond=0).isoformat(),
    }
    d = _lire_index()
    d["fichiers"].append(entree)
    _ecrire_index(d)
    return {
        "tache": "fichiers-deposer",
        "statut": "ok",
        "resultat": {"fichier": entree, "dossier": _dossier()},
        "sources": ["vault Argus (/60_FICHIERS)"],
        "erreurs": [],
        "date": date.today().isoformat(),
    }


def _score(entree: dict, mots: list[str]) -> int:
    """Score de pertinence simple : compte les mots trouvés dans les champs."""
    champs = " ".join([
        entree.get("titre", ""), entree.get("description", ""),
        " ".join(entree.get("mots_cles", [])), entree.get("type", ""),
        entree.get("source", ""),
    ]).lower()
    champs = unicodedata.normalize("NFKD", champs).encode("ascii", "ignore").decode()
    return sum(1 for m in mots if m and m in champs)


def chercher(*, q: str, limite: int = 20) -> dict:
    """Cherche des fichiers par mots-clés / texte libre dans l'index."""
    if not q or not q.strip():
        raise FichierError("chercher : requête vide.")
    mots = [unicodedata.normalize("NFKD", m).encode("ascii", "ignore").decode().lower()
            for m in re.split(r"\W+", q) if m]
    d = _lire_index()
    scores = [(_score(e, mots), e) for e in d["fichiers"]]
    trouves = [(s, e) for s, e in scores if s > 0]
    trouves.sort(key=lambda t: -t[0])
    resultats = [e for _, e in trouves[:limite]]
    return {
        "tache": "fichiers-chercher",
        "statut": "ok",
        "entree": {"q": q, "limite": limite},
        "resultat": {"fichiers": resultats, "nb": len(resultats),
                     "rappel": "le champ 'chemin' est le fichier réel à lire/afficher."},
        "sources": ["vault Argus (/_INDEX.json)"],
        "erreurs": [],
        "date": date.today().isoformat(),
    }


def lister(*, limite: int = 100) -> dict:
    d = _lire_index()
    fichiers = list(reversed(d["fichiers"]))[:limite]
    return {
        "tache": "fichiers-lister",
        "statut": "ok",
        "resultat": {"fichiers": fichiers, "nb": len(d["fichiers"])},
        "sources": ["vault Argus (/_INDEX.json)"],
        "erreurs": [],
        "date": date.today().isoformat(),
    }


def montrer(*, id: str) -> dict:
    """Renvoie le chemin réel d'un fichier indexé (pour le lire/afficher)."""
    d = _lire_index()
    for e in d["fichiers"]:
        if e.get("id") == id:
            existe = os.path.isfile(e.get("chemin", ""))
            return {
                "tache": "fichiers-montrer",
                "statut": "ok" if existe else "partiel",
                "resultat": {"fichier": e, "existe": existe},
                "sources": ["vault Argus (/_INDEX.json)"],
                "erreurs": [] if existe else [{"etape": "montrer",
                                               "erreur": "fichier absent du disque"}],
                "date": date.today().isoformat(),
            }
    raise FichierError(f"id inconnu : {id!r}")


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Dépôt/rappel de fichiers du sous-cerveau Argus.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("deposer", help="copier un fichier dans le vault + l'indexer")
    d.add_argument("--chemin", required=True)
    d.add_argument("--titre", required=True)
    d.add_argument("--description", default="")
    d.add_argument("--mots-cles", default="", help="séparés par des virgules")
    d.add_argument("--source", default="")
    d.add_argument("--type", dest="type_fichier", default=None)

    c = sub.add_parser("chercher", help="chercher un fichier dans l'index")
    c.add_argument("--q", required=True)
    c.add_argument("--limite", type=int, default=20)

    l = sub.add_parser("lister", help="lister les fichiers déposés")
    l.add_argument("--limite", type=int, default=100)

    m = sub.add_parser("montrer", help="chemin réel d'un fichier par id")
    m.add_argument("id")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "deposer":
            mk = [x for x in args.mots_cles.split(",") if x.strip()]
            out = deposer(chemin=args.chemin, titre=args.titre,
                          description=args.description, mots_cles=mk,
                          source=args.source, type_fichier=args.type_fichier)
        elif args.cmd == "chercher":
            out = chercher(q=args.q, limite=args.limite)
        elif args.cmd == "lister":
            out = lister(limite=args.limite)
        elif args.cmd == "montrer":
            out = montrer(id=args.id)
        else:
            raise FichierError(f"commande inconnue : {args.cmd}")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    except FichierError as exc:
        print(json.dumps({"erreur": str(exc), "etape": "fichiers"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(_main())
