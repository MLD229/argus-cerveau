"""DPE / GES — base ADEME (data-fair). Source officielle, gratuite, sans clé.

- dpe_par_adresse(adresse)  : DPE à une adresse (appariement exact préféré).
- dpe_par_code_insee(insee) : DPE d'une commune (repli large, a_verifier).

Pièges connus :
- data-fair : `qs=` filtre EXACT (à utiliser) ; `q=` est FLOU (à éviter).
- L'appariement par adresse exacte (format BAN) est fiable ; un repli par code
  postal est LARGE -> fiabilité a_verifier.
"""
from __future__ import annotations

import json
import sys
from datetime import date

from _http import ConnectorError, http_get_json, json_error

# Jeu de données DPE « logements existants » (ADEME, data-fair).
DEFAULT_DATASET = "dpe03existant"
FAIR_BASE = "https://data.ademe.fr/data-fair/api/v1/datasets/{ds}/lines"


def _now() -> str:
    return date.today().isoformat()


def _norm(r: dict) -> dict:
    """Normalise une ligne ADEME en DPE compact."""
    return {
        "classe_energie": r.get("etiquette_dpe") or r.get("classe_consommation_energie"),
        "classe_ges": r.get("etiquette_ges") or r.get("classe_estimation_ges"),
        "date_etablissement": r.get("date_etablissement_dpe"),
        "surface": r.get("surface_habitable_logement") or r.get("surface_habitable"),
        "adresse": r.get("adresse_ban") or r.get("adresse_brut"),
    }


def _query(dataset_id: str, qs: str, size: int = 20) -> dict:
    url = FAIR_BASE.format(ds=dataset_id)
    # qs = filtre exact (pas de flou) ; size = nombre de lignes.
    data = http_get_json(url, {"qs": qs, "size": size})
    if not isinstance(data, dict):
        raise ConnectorError("Reponse ADEME inattendue", url=url)
    return data


def dpe_par_adresse(adresse: str, *, dataset: str = DEFAULT_DATASET,
                    size: int = 20) -> dict:
    """DPE à une adresse (format BAN exact préféré). Fiabilité verifie."""
    data = _query(dataset, f'adresse_ban:"{adresse}"', size=size)
    rows = data.get("results") or []
    if not rows:
        # Repli : recherche exacte non concluante -> a_verifier, on ne devine pas.
        raise ConnectorError(f"Aucun DPE pour l'adresse exacte: {adresse!r}")
    dpe = _norm(rows[0])
    dpe.update({
        "fiabilite": "verifie",
        "source": "ADEME data-fair",
        "date": _now(),
        "nb_resultats": len(rows),
    })
    return {"adresse": adresse, "nb_resultats": len(rows), "dpe": dpe,
            "fiabilite": "verifie", "source": "ADEME data-fair", "date": _now()}


def dpe_par_code_insee(code_insee: str, *, dataset: str = DEFAULT_DATASET,
                       size: int = 20) -> dict:
    """DPE d'une commune (repli LARGE, fiabilité a_verifier)."""
    data = _query(dataset, f'code_insee_ban:"{code_insee}"', size=size)
    rows = data.get("results") or []
    if not rows:
        raise ConnectorError(f"Aucun DPE pour le code INSEE: {code_insee!r}")
    return {
        "code_insee": code_insee,
        "nb_resultats": len(rows),
        "dpe": [_norm(r) for r in rows],
        "fiabilite": "a_verifier",
        "note": "repli par commune (large) : adresse exacte non confirmée",
        "source": "ADEME data-fair",
        "date": _now(),
    }


def _cli() -> int:
    import argparse

    p = argparse.ArgumentParser(description="DPE / GES (base ADEME data-fair)")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--adresse", help="adresse (format BAN) ou texte libre")
    grp.add_argument("--insee", dest="code_insee",
                     help="code INSEE de la commune (repli large, a_verifier)")
    args = p.parse_args()
    try:
        if args.code_insee:
            res = dpe_par_code_insee(args.code_insee)
        else:
            adresse = (args.adresse or "").strip()
            if not adresse:
                print(json.dumps(json_error("adresse vide : fournir --adresse <texte>"),
                                 ensure_ascii=False, indent=2))
                return 2
            res = dpe_par_adresse(adresse)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    except ConnectorError as exc:
        print(json.dumps(json_error(str(exc), url=exc.url), ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(_cli())
