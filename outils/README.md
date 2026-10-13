# outils/ — modules Python purs (collecte & calcul)

> **Règle fondatrice** : collecte et calcul en **Python pur** (stdlib au
> maximum). **Jamais** un LLM pour scraper, calculer ou inventer un chiffre.
> Chaque module rend un **JSON structuré** (voir `docs/contrat-outils.md`).
> Aucune clé API requise — tout est open data ou flux public.

## Les 6 modules

| Fichier | Rôle | Source | Fiabilité |
|---------|------|--------|-----------|
| `_http.py` | helper HTTP partagé (retries, gzip, User-Agent honnête, `ConnectorError`) | — | — |
| `bienici.py` | **annonces** Bien'ici (flux JSON public, voie n°1) + SeLoger modéré (**non activé**) | Bien'ici | `annonce` |
| `dvf.py` | **ventes réelles** (prix, surface, €/m²) par commune | DVF Etalab | `verifie` |
| `dpe.py` | **DPE / GES** (classe énergie) à une adresse | ADEME data-fair | `verifie` |
| `geocode.py` | adresse → **coordonnées + INSEE** + commune | BAN / geo.api.gouv | `verifie` |
| `moteur.py` | **orchestrateur** : chaîne tout → fiche bien complète | agrégat | mixte |

## Usage rapide

```bash
cd /home/momo/projects/argus-immo

# Zone Bien'ici (OBLIGATOIRE avant toute recherche d'annonces)
python3 outils/bienici.py zone "Lyon 6"

# Annonces
python3 outils/bienici.py annonces --zone "Lyon 6" --transaction buy \
    --types flat --surface-min 40 --prix-max 400000

# Ventes réelles
python3 outils/dvf.py --commune 69386 --annees 2024 --type Appartement --surface 45

# DPE
python3 outils/dpe.py --adresse "25 Rue Notre-Dame 69006 Lyon"

# Géocodage
python3 outils/geocode.py "25 rue Notre-Dame 69006 Lyon"

# Fiche complète (un seul appel, chaîne tout)
python3 outils/moteur.py --adresse "25 rue Notre-Dame" --cp 69006 \
    --surface 45 --type Appartement --annee 2024
```

Chaque script sort du **JSON**. En cas d'échec : JSON `{"erreur": ..., "url": ...}`
et code de sortie **2** (jamais de trace Python brute).

## En bibliothèque (Python)

```python
import sys; sys.path.insert(0, "outils")
from bienici import resoudre_zone, chercher_annonces
from dvf import ventes_comparables
from moteur import enrichir_bien

zones = resoudre_zone("Lyon 6")               # -> zoneIds
ann = chercher_annonces(zone="Lyon 6", transaction="buy", types=["flat"])
ventes = ventes_comparables("69386", [2024], type_bien="Appartement", surface=45)
fiche = enrichir_bien("25 rue Notre-Dame", 45, code_postal="69006",
                      type_bien="Appartement", annee_dvf=2024)
```

## Tests réels

```bash
bash tests/verify-outils.sh    # appels réseau réels (Bien'ici, BAN, DVF, ADEME, IGN)
```

## Pièges connus (à ne pas oublier)

1. **Bien'ici** : sans `zoneId` résolu, le flux renvoie la FRANCE ENTIÈRE.
   Toujours `bienici.py zone` d'abord.
2. **DVF** : fichiers **par département** (~2 Mo gz), pas par commune.
3. **IGN apicarto** : `code_insee` seul ne renvoie rien ; `geom` attend du
   **GeoJSON** (Point/Polygon), pas une chaîne de coordonnées.
4. **BAN** : le point tombe sur la VOIE → repli bbox (±45 m), `a_verifier`.
5. **ADEME** : `qs=` (exact) à utiliser ; `q=` (flou) à éviter.
6. **Leboncoin** : INTERDIT (403 + DataDome). Ne jamais coder d'appel.

Détail complet : `docs/contrat-outils.md`.
