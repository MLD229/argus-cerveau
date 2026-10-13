"""Alerte e-mail des portails — la SEULE voie légale vers Leboncoin / SeLoger / PAP.

Pourquoi ce module existe
-------------------------
Leboncoin (et Logic-Immo) sont **interdits** en extraction directe : robots.txt
interdit les robots ET DataDome bloque (403 réel). Contourner = violation de la
charte projet (docs/legal.md) et exposition juridique pour le client.

La voie légale et gratuite : l'utilisateur crée une **recherche sauvegardée**
sur le portail avec « alerte e-mail » activée ; le portail *pousse* chaque
nouvelle annonce par e-mail vers une adresse dédiée ; ce module lit la boîte
IMAP et en extrait les annonces.

Nature de la donnée (à dire au client, sans surpromettre)
---------------------------------------------------------
- C'est un RADAR (détecter qu'une annonce est parue), PAS un appariement fin.
  Les filtres sont ceux du moteur du portail (ville/quartier, budget, pièces,
  surface, type) ; on NE PEUT PAS filtrer sur étage/RDC/DPE/travaux.
- Format = e-mail (HTML/texte), pas de schéma stable : le parseur est fragile
  et casse quand le portail change son gabarit.
- Pas de « date de mise en vente » exploitable dans l'e-mail.
- Fiabilité des champs extraits : 'annonce' (le portail déclare le prix).
  Un lien direct vers l'annonce est toujours fourni pour vérification humaine.

Sources d'e-mails reconnues (par domaine d'expéditeur)
------------------------------------------------------
- leboncoin : alerte@leboncoin.fr / *@leboncoin.fr
- seloger   : *@seloger.com
- pap       : *@pap.fr
Un expéditeur inconnu reste listé (source 'inconnu') pour ne rien perdre.

Contrat CLI (identique aux autres outils)
-----------------------------------------
  python3 outils/alerte_email.py lister --depuis 7
  python3 outils/alerte_email.py annonces --depuis 7 --source leboncoin
  python3 outils/alerte_email.py test        # vérifie la connexion IMAP

Sortie : JSON structuré (enveloppe §4.1 du contrat des outils) ou, en échec,
JSON {"erreur": ..., ...} + code de sortie 2. Aucune valeur inventée.

Variables d'environnement (JAMAIS en dur dans le repo)
------------------------------------------------------
- IMAP_USER     : adresse de la boîte dédiée aux alertes
- IMAP_PASSWORD : mot de passe / mot de passe d'application
- IMAP_HOST     : défaut 'imap.gmail.com' (surchargeable : outlook, free…)
- IMAP_PORT     : défaut 993 (SSL)
- IMAP_FOLDER   : défaut 'INBOX'
"""
from __future__ import annotations

import argparse
import email
import email.message
import email.policy
import email.utils
import html
import imaplib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

# --- Domaines d'expéditeurs connus (portail -> libellé) -----------------------
SOURCES = {
    "leboncoin.fr": "Leboncoin",
    "seloger.com": "SeLoger",
    "pap.fr": "PAP",
}

# --- Gabarits de liens d'annonce par portail (pour extraire l'URL directe) ----
LIEN_MOTIFS = (
    re.compile(r"https?://[^\s\"'<>]*leboncoin\.fr/(?:ad/|annonces/)[^\s\"'<>]+"),
    re.compile(r"https?://[^\s\"'<>]*seloger\.com/[^\s\"'<>]+"),
    re.compile(r"https?://[^\s\"'<>]*pap\.fr/[^\s\"'<>]+"),
)

# Extraction « prix » (€ / euros) dans le texte de l'e-mail.
PRIX_MOTIF = re.compile(r"(\d[\d\s\.\u00a0]{2,})\s*(?:€|EUR|euros?)", re.IGNORECASE)
# Extraction « surface » (m²).
SURFACE_MOTIF = re.compile(r"(\d{1,4}(?:[.,]\d{1,2})?)\s*m(?:²|2|\b)", re.IGNORECASE)


class AlerteError(RuntimeError):
    """Erreur claire du connecteur alerte-email."""


def _identifiants() -> tuple[str, str]:
    user = os.environ.get("IMAP_USER")
    pwd = os.environ.get("IMAP_PASSWORD")
    if not user or not pwd:
        raise AlerteError(
            "IMAP_USER et IMAP_PASSWORD sont requis. Configurez la boîte dédiée "
            "aux alertes portail (voir README §Alerte e-mail). Jamais en dur dans le repo."
        )
    return user, pwd


def _source_de(expediteur: str) -> str:
    """Déduit la source (portail) depuis l'adresse d'expéditeur."""
    m = re.search(r"@([\w\.\-]+)", expediteur or "")
    domaine = (m.group(1).lower() if m else "")
    for suffixe, libelle in SOURCES.items():
        if domaine.endswith(suffixe):
            return libelle
    return "inconnu"


def _texte_du_message(msg: email.message.Message) -> str:
    """Rend le corps lisible (texte/plain prioritaire, sinon HTML dé-taggé)."""
    plain, htm = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain" and not plain:
                plain = _payload(part)
            elif ctype == "text/html" and not htm:
                htm = _payload(part)
    else:
        ctype = msg.get_content_type()
        if ctype == "text/html":
            htm = _payload(msg)
        else:
            plain = _payload(msg)

    if plain.strip():
        return plain
    if htm:
        return _html_vers_texte(htm)
    return ""


def _payload(part: email.message.Message) -> str:
    try:
        contenu = part.get_content()
        if isinstance(contenu, bytes):
            return contenu.decode(part.get_content_charset() or "utf-8", "ignore")
        return str(contenu)
    except Exception:
        payload = part.get_payload(decode=True) or b""
        if isinstance(payload, str):
            return payload
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, "ignore")


def _html_vers_texte(htm: str) -> str:
    texte = re.sub(r"(?is)<(script|style).*?</\1>", " ", htm)
    # garder les href des liens (URLs d'annonce)
    texte = re.sub(r'(?is)<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                   r" \2 \1 ", texte)
    texte = re.sub(r"(?s)<[^>]+>", " ", texte)
    texte = html.unescape(texte)
    texte = re.sub(r"[ \t\u00a0]+", " ", texte)
    texte = re.sub(r"\n\s*\n+", "\n", texte)
    return texte.strip()


def _nettoyer_prix(brut: str) -> int | None:
    chiffres = re.sub(r"[^\d]", "", brut)
    if not chiffres:
        return None
    try:
        return int(chiffres)
    except ValueError:
        return None


def _extraire_annonces(texte: str, expediteur: str, sujet: str,
                       date_iso: str, source: str) -> list[dict]:
    """Extrait les annonces repérables dans le texte d'un e-mail d'alerte.

    On ne devine pas : chaque champ absent reste None. Le lien direct est
    essentiel (permet la vérification humaine).
    """
    liens: list[str] = []
    for motif in LIEN_MOTIFS:
        liens.extend(motif.findall(texte))
    # dédoublonner en conservant l'ordre
    vus: set[str] = set()
    liens = [u for u in liens if not (u in vus or vus.add(u))]

    prix = PRIX_MOTIF.findall(texte)
    prix_valeurs = [p for p in (_nettoyer_prix(x) for x in prix) if p]
    surface = SURFACE_MOTIF.findall(texte)

    if not liens:
        # E-mail sans lien d'annonce reconnu : on garde quand même la trace,
        # marquée 'a_verifier' — jamais perdue en silence.
        return [{
            "id": f"alerte:{source}:{date_iso}:{abs(hash(sujet)) % 10**8}",
            "titre": sujet or "(sans sujet)",
            "source_portail": source,
            "expediteur": expediteur,
            "date_email": date_iso,
            "url_annonce": None,
            "prix": {"valeur": prix_valeurs[0] if prix_valeurs else None,
                     "source": source, "fiabilite": "a_verifier",
                     "date": date_iso,
                     "note": "extrait du texte de l'e-mail d'alerte"},
            "surface": {"valeur": float(surface[0].replace(",", ".")) if surface else None,
                        "source": source, "fiabilite": "a_verifier", "date": date_iso},
            "fiabilite_globale": "a_verifier",
        }]

    annonces = []
    for url in liens:
        annonces.append({
            "id": f"alerte:{source}:{_id_depuis_url(url)}",
            "titre": sujet or "(sans sujet)",
            "source_portail": source,
            "expediteur": expediteur,
            "date_email": date_iso,
            "url_annonce": url,
            "prix": {"valeur": prix_valeurs[0] if prix_valeurs else None,
                     "source": source, "fiabilite": "annonce", "date": date_iso},
            "surface": {"valeur": float(surface[0].replace(",", ".")) if surface else None,
                        "source": source, "fiabilite": "annonce", "date": date_iso},
            "fiabilite_globale": "annonce",
            "note": "RADAR (détection) — à qualifier; croiser le prix avec DVF.",
        })
    return annonces


def _id_depuis_url(url: str) -> str:
    p = urlparse(url)
    dernier = (p.path.rstrip("/").rsplit("/", 1)[-1] or p.path) or str(abs(hash(url)))
    return re.sub(r"[^\w\-]", "", dernier)[:32] or "inconnu"


def _connexion() -> imaplib.IMAP4_SSL:
    user, pwd = _identifiants()
    host = os.environ.get("IMAP_HOST", "imap.gmail.com")
    port = int(os.environ.get("IMAP_PORT", "993"))
    try:
        imap = imaplib.IMAP4_SSL(host, port)
        imap.login(user, pwd)
    except imaplib.IMAP4.error as exc:
        raise AlerteError(f"Connexion IMAP échouée ({host}:{port}) : {exc}") from exc
    except OSError as exc:
        raise AlerteError(f"Réseau IMAP injoignable ({host}:{port}) : {exc}") from exc
    return imap


def _depuis_date(depuis_jours: int) -> str:
    d = date.today() - timedelta(days=depuis_jours)
    return d.strftime("%d-%b-%Y")  # format IMAP : 08-Oct-2026


def lire_alertes(*, depuis_jours: int = 7, source: str | None = None,
                 limite: int = 200) -> dict:
    """Lit la boîte IMAP et extrait les annonces des e-mails d'alerte.

    depuis_jours : ne lit que les e-mails des N derniers jours (SINCE IMAP).
    source       : filtre sur un portail ('leboncoin'/'seloger'/'pap'), insensible
                   à la casse. None = tous.
    Retour : enveloppe §4.1 (tache/statut/resultat/sources/erreurs/date).
    """
    folder = os.environ.get("IMAP_FOLDER", "INBOX")
    erreurs: list[dict] = []
    annonces: list[dict] = []
    mails_lus = 0

    imap = _connexion()
    try:
        imap.select(folder)
        typ, data = imap.search(None, f'(SINCE "{_depuis_date(depuis_jours)}")')
        if typ != "OK":
            raise AlerteError(f"Recherche IMAP refusée dans '{folder}'.")
        ids = (data[0].split() if data and data[0] else [])
        for num in ids[-limite:]:
            typ, raw = imap.fetch(num, "(RFC822)")
            if typ != "OK" or not raw or not raw[0]:
                erreurs.append({"etape": "fetch", "erreur": f"message {num!r} illisible"})
                continue
            msg = email.message_from_bytes(raw[0][1], policy=email.policy.default)
            expediteur = str(msg.get("From", ""))
            sujet = str(msg.get("Subject", ""))
            date_hdr = msg.get("Date")
            try:
                date_iso = email.utils.parsedate_to_datetime(date_hdr).date().isoformat() \
                    if date_hdr else date.today().isoformat()
            except Exception:
                date_iso = date.today().isoformat()

            src = _source_de(expediteur)
            if source and src.lower() != source.lower():
                continue
            mails_lus += 1
            texte = _texte_du_message(msg)
            annonces.extend(_extraire_annonces(texte, expediteur, sujet, date_iso, src))
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    statut = "ok" if not erreurs else ("partiel" if annonces else "echec")
    return {
        "tache": "alerte-email",
        "statut": statut,
        "entree": {"depuis_jours": depuis_jours, "source": source, "dossier": folder},
        "resultat": {"nb_mails": mails_lus, "nb_annonces": len(annonces),
                     "annonces": annonces,
                     "rappel": "RADAR (détection), pas appariement fin. "
                               "Filtres = ceux du moteur du portail ; pas d'étage/RDC/DPE. "
                               "Croiser le prix (annonce) avec DVF (vérifié)."},
        "sources": ["boîte IMAP dédiée aux alertes portail"],
        "erreurs": erreurs,
        "date": date.today().isoformat(),
    }


def tester_connexion() -> dict:
    """Vérifie juste que la boîte IMAP est joignable et lisible."""
    folder = os.environ.get("IMAP_FOLDER", "INBOX")
    imap = _connexion()
    try:
        typ, data = imap.select(folder)
        nb = int(data[0]) if typ == "OK" and data and data[0] else 0
        typ2, _ = imap.search(None, "ALL")
        return {
            "tache": "alerte-email-test",
            "statut": "ok",
            "resultat": {"dossier": folder, "nb_messages": nb,
                         "connecte": True,
                         "hote": os.environ.get("IMAP_HOST", "imap.gmail.com")},
            "sources": ["IMAP"],
            "erreurs": [],
            "date": date.today().isoformat(),
        }
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Connecteur alerte e-mail des portails (voie légale).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("lister", help="lister les annonces des e-mails d'alerte")
    p_list.add_argument("--depuis", type=int, default=7, help="jours en arrière (défaut 7)")
    p_list.add_argument("--source", default=None, help="leboncoin|seloger|pap")
    p_list.add_argument("--limite", type=int, default=200, help="nb max d'e-mails lus")

    p_ann = sub.add_parser("annonces", help="alias de lister")
    p_ann.add_argument("--depuis", type=int, default=7)
    p_ann.add_argument("--source", default=None)
    p_ann.add_argument("--limite", type=int, default=200)

    sub.add_parser("test", help="tester la connexion IMAP")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "test":
            out = tester_connexion()
        else:
            out = lire_alertes(depuis_jours=args.depuis, source=args.source,
                               limite=args.limite)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    except AlerteError as exc:
        print(json.dumps({"erreur": str(exc), "etape": "alerte-email"},
                         ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(_main())
