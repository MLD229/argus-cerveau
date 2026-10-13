# Contrat des OUTILS Python — `outils/`

> Règle fondatrice : **collecte et calcul en Python pur** (stdlib au maximum).
> **Jamais** un LLM pour scraper, calculer ou inventer un chiffre.
> Un outil **rend un JSON structuré** ; il ne décide pas.

## 1. Les six modules

| Module | Rôle (1 ligne) | Source | Fiabilité |
|--------|----------------|--------|-----------|
| `_http.py` | helper HTTP partagé (retries, gzip, User-Agent honnête, `ConnectorError`) | — | — |
| `bienici.py` | annonces immobilières du flux JSON **ouvert** de Bien'ici (voie n°1) + SeLoger modéré (**non activé**) | Bien'ici | `annonce` |
| `dvf.py` | **ventes réelles** (prix, surface, date, €/m²) par commune → comparables | DVF Etalab | `verifie` |
| `dpe.py` | **DPE / GES** (classe énergie, GES, date, surface) à une adresse | ADEME data-fair | `verifie` |
| `geocode.py` | adresse → **coordonnées + code INSEE** + commune/arrondissement (BAN + geo.api.gouv) | BAN / geo.api.gouv | `verifie` |
| `alerte_email.py` | **annonces poussées par les alertes e-mail** des portails (voie LÉGALE vers Leboncoin/SeLoger/PAP) | boîte IMAP dédiée | `annonce` |
| `transports.py` | **arrêts de transport les plus proches** d'un point (métro/tram/bus) | OpenStreetMap / Overpass | `verifie` |
| `notifications.py` | **magasin de notifications** partagé (badge app web + lecture agent) | local (volume partagé) | — |
| `fichiers.py` | **dépôt/rappel de fichiers & images** du sous-cerveau (index cherchable) | vault `60_FICHIERS` | — |
| `veille.py` | **sources de notifications** : nouvelles annonces, baisses, ventes DVF | Bien'ici / DVF | `annonce` |
| `veille_config.py` | **config réglable de la veille** : filtre de pertinence + fréquence (pilote l'UI) | fichier JSON partagé | — |
| `moteur.py` | **orchestrateur** : chaîne les outils → fiche enrichie complète | agrégat | mixte |

### Pourquoi ces six-là

- Ils couvrent **tout** ce qu'un particulier demande : *où* (`geocode`), *quoi*
  (`bienici`), *combien* (`dvf`), *quelle énergie* (`dpe`), *tout à la fois*
  (`moteur`).
- Aucune **clé API** n'est requise : tout est open data ou flux public.
- **stdlib uniquement** (`urllib`, `json`, `csv`, `gzip`, `datetime`) : pas de
  dépendance à installer, pas de `pip` nécessaire.

## 2. Signatures des fonctions principales

> Conventions : les paramètres marqués `*` sont obligatoires. Les fonctions de
> bibliothèque **lèvent** `ConnectorError` en cas d'échec définitif ; les
> entrées CLI impriment un JSON `{"erreur": ..., "url": ...}` et sortent en
> code 2 (pas de trace Python brute).

### `_http.py`

```python
UA = "argus-immo-outils/1.0 (contact: momomld904@gmail.com)"
DEFAULT_TIMEOUT = 30

class ConnectorError(RuntimeError):
    """Erreur claire d'un connecteur — jamais un crash silencieux."""
    url: str | None
    status: int | None

def http_get_json(url: str, params: dict | None = None, *,
                  timeout: int = DEFAULT_TIMEOUT, retries: int = 2,
                  extra_headers: dict | None = None) -> dict | list:
    """GET JSON avec retries et gzip. Lève ConnectorError en échec définitif."""

def http_get_bytes(url: str, *, timeout: int = DEFAULT_TIMEOUT, retries: int = 2,
                   extra_headers: dict | None = None) -> bytes:
    """GET brut (gzip géré). Retente sur réseau/5xx ; pas de retry sur 404."""
```

### `bienici.py` — annonces (voie n°1)

```python
def resoudre_zone(texte: str, *, timeout: int = 20) -> list[dict]:
    """Texte libre ('Lyon 6e') -> zones avec zoneIds.
    Retour : [{"name","type","insee_code","postal_codes","zoneIds","population"}]
    ⚠ OBLIGATOIRE avant toute recherche : sans zoneId, le flux renvoie la
      France entière."""

def chercher_annonces(*, zone: str, transaction: str = "buy",
                      types: list[str] | None = None,
                      surface_min: float | None = None,
                      surface_max: float | None = None,
                      prix_min: float | None = None,
                      prix_max: float | None = None,
                      pieces_min: int | None = None,
                      rdc_seulement: bool = False) -> dict:
    annonces Bien'ici filtrées.
    transaction : 'buy' (acheter) | 'rent' (louer).
    types       : libellés FR ou valeurs API — ['appartement','maison','bureau', ...]
                  (traduits en interne : appartement->flat, maison->house,
                  bureau->office). Un type inconnu lève une erreur (jamais 0
                  silencieux). None = tous.
    Retour : {"zone": "...", "zoneId": "-120968", "nb_annonces": N,
              "annonces": [ <annonce normalisée> ]}

def chercher_seloger_playwright(url: str, *, timeout_s: int = 90) -> dict:
    """SeLoger par navigateur — USAGE MODÉRÉ. NON ACTIVÉ pour l'instant :
    lève ConnectorError (voie zone grise, aucun code SeLoger actif)."""

# Raccourci bibliothèque conservé pour compatibilité v1
chercher_bienici = chercher_annonces
```

**Format d'une annonce normalisée** (élément de `annonces`) :

```json
{
  "id": "bienici:12345",
  "titre": "Appartement 3 pièces 62 m²",
  "type": "appartement",
  "transaction": "buy",
  "ville": "Lyon 6e",
  "quartier": null,
  "surface": { "valeur": 62, "source": "Bien'ici", "fiabilite": "annonce", "date": "AAAAMMJJ" },
  "prix":     { "valeur": 349000, "source": "Bien'ici", "fiabilite": "annonce", "date": "AAAAMMJJ" },
  "prix_m2":  { "valeur": 5629, "source": "calcul", "fiabilite": "annonce", "date": "AAAAMMJJ" },
  "etage": 2,
  "ascenseur": true,
  "cave": null,
  "dpe": null,
  "ges": null,
  "charges": null,
  "agence": "Agence X",
  "url_annonce": "https://www.bienici.com/...",
  "source_portail": "Bien'ici",
  "date_modification": "AAAAMMJJ",
  "prix_baisse": false,
  "date_detection": "AAAAMMJJ"
}
```

### `dvf.py` — ventes réelles (comparables)

```python
def ventes_comparables(code_commune: str, annees: list[int] | None = None, *,
                       type_bien: str | None = None,
                       surface: float | None = None,
                       tolerance_surface: float = 0.20) -> dict:
    """Ventes réelles DVF dans une commune -> statistiques de prix.
    code_commune : code INSEE ('69386') — PAS de découpage par commune dans les
                   fichiers DVF : on télécharge le département (~2 Mo gz) et on
                   filtre côté client.
    type_bien    : 'Appartement' | 'Maison' | None.
    surface      : si fourni, ne garde que les ventes ±tolerance_surface.
    Retour : {"code_commune": "...", "annees": [...], "nb_ventes": N,
              "mediane_m2": 4654, "min_m2": ..., "max_m2": ...,
              "exclusions": {"multi_lots": N, "hors_bornes": N, "hors_surface": N},
              "ventes": [ {"date","valeur","surface","prix_m2","type"} ]}
    Anti-pollution : les mutations MULTI-LOTS (immeubles) sont exclues et les €/m²
    hors [500, 25000] écartés, pour une fourchette min/max crédible."""
```

### `dpe.py` — DPE / GES (ADEME)

```python
def dpe_par_adresse(adresse: str, *, dataset: str = DEFAULT_DATASET,
                    size: int = 20) -> dict:
    """DPE à une adresse (format BAN exact préféré).
    Retour : {"adresse": "...", "nb_resultats": N,
              "dpe": {"classe_energie": "C", "classe_ges": "A",
                      "date": "...", "surface": ..., "fiabilite": "verifie"}}"""

def dpe_par_code_insee(code_insee: str, *, dataset: str = DEFAULT_DATASET,
                       size: int = 20) -> dict:
    """DPE d'une commune (repli large, fiabilité a_verifier)."""
```

### `geocode.py` — BAN + commune

```python
def geocoder(adresse: str, *, code_postal: str | None = None,
             limit: int = 5) -> dict:
    """Adresse libre -> coordonnées + INSEE (format BAN).
    ⚠ Le point BAN tombe souvent sur la VOIE (chaussée), pas sur la parcelle :
      les outils en aval doivent prévoir un repli.
    Retour : {"adresse_normalisee": "...", "lat": 45.76, "lon": 4.86,
              "code_insee": "69386", "code_postal": "69006",
              "ville": "Lyon", "fiabilite": "verifie"}"""

def commune(code_insee: str, *, arrondissements: bool = False) -> dict:
    """Code INSEE -> commune/arrondissement, population, centre.
    ⚠ geo.api.gouv v1 n'expose NI /quartiers NI /arrondissements : les
      arrondissements Lyon/Marseille/Paris sont reconstitués via une table
      INSEE CP->INSEE. quartiers() -> [] + note."""
```

### `alerte_email.py` — annonces des alertes e-mail (voie légale Leboncoin/SeLoger/PAP)

```python
def lire_alertes(*, depuis_jours: int = 7, source: str | None = None,
                 limite: int = 200) -> dict:
    """Lit la boîte IMAP dédiée et extrait les annonces des e-mails d'alerte.
    depuis_jours : e-mails des N derniers jours (SINCE IMAP).
    source       : 'leboncoin' | 'seloger' | 'pap' (insensible casse) ou None.
    Retour : enveloppe §4.1. Chaque annonce : id, titre, source_portail,
             expediteur, date_email, url_annonce, prix{fiabilite:'annonce'},
             surface, fiabilite_globale, note.
    ⚠ RADAR (détection), PAS appariement fin : filtres = moteur du portail
      (ville, budget, pièces, surface, type). Pas d'étage/RDC/DPE/travaux.
      Pas de « date de mise en vente ». Le prix est 'annonce' → croiser DVF."""

def tester_connexion() -> dict:
    """Vérifie que la boîte IMAP est joignable et lisible (diagnostic)."""
```

### `transports.py` — arrêts de transport les plus proches (OSM/Overpass)

```python
def arrets_proches(lat: float, lon: float, *, rayon_m: int = 600,
                   limite: int = 5, ttl_cache_s: int = 86400) -> dict:
    """Arrêts TCL (métro/tram/bus) les plus proches d'un point.
    lat/lon : coordonnées du bien (geocode.py ou Bien'ici blurInfo.position).
    Retour : enveloppe §4.1. resultat.arrets = [{nom, categorie, lignes,
      distance_m, lat, lon}] triés par distance (+ distance_approximative=True).
    ⚠ Distance À VOL D'OISEAU (pas d'itinéraire) → marquer « approximatif ».
    Miroirs Overpass + retry borné + cache disque. Échec = ConnectorError
    (statut echec) — JAMAIS de boucle. Un même arrêt est dédoublonné
    (nom, catégorie).
    Motif : ce besoin est déterministe → Python, pas un LLM qui tâtonne
    (un LLM boucle sur Overpass->Wikipedia->Nominatim, cf. session de test)."""
```

### `moteur.py` — orchestrateur (fiche complète)

```python
def enrichir_bien(adresse: str, surface: float | None = None, *,
                  commune: str | None = None,   # code INSEE ou nom
                  code_postal: str | None = None,
                  type_bien: str | None = None,
                  annee_dvf: int | None = None) -> dict:
    """Chaîne : géocodage BAN -> commune/arrondissement -> parcelle IGN
    -> DPE ADEME -> ventes DVF. Un seul appel = une fiche complète.
    Retour : voir §4 (format partagé) — clés 'resultat'/'champs',
             'etapes', 'erreurs', 'meta'. Ne lève pas : collecte les erreurs."""
```

## 3. CLI — usage en ligne de commande

```bash
cd <racine du dépôt argus-cerveau>

# Zone Bien'ici (OBLIGATOIRE avant toute recherche)
python3 outils/bienici.py zone "Lyon 6"

# Annonces Bien'ici (types acceptés en français OU en valeur API)
python3 outils/bienici.py annonces --zone "Lyon 6" --transaction buy \
    --types appartement --surface-min 40 --prix-max 400000

# Ventes réelles DVF
python3 outils/dvf.py --commune 69386 --annees 2024 --type Appartement --surface 62

# DPE
python3 outils/dpe.py --adresse "21 Rue Dussaussoy 69006 Lyon"

# Géocodage
python3 outils/geocode.py "25 rue Notre-Dame 69006 Lyon"

# Fiche complète (bout en bout)
python3 outils/moteur.py --adresse "25 rue Notre-Dame" --cp 69006 \
    --surface 45 --type Appartement --annee 2024

# Alertes e-mail portails (voie LÉGALE vers Leboncoin/SeLoger/PAP)
python3 outils/alerte_email.py test                 # diagnostic connexion IMAP
python3 outils/alerte_email.py lister --depuis 7 --source leboncoin

# Transports (arrêts TCL proches) — par coordonnées ou par adresse
python3 outils/transports.py --lat 45.7670 --lon 4.8594 --rayon 600 --limite 5
python3 outils/transports.py --adresse "25 rue Notre-Dame 69006 Lyon"
```

Chaque script sort du **JSON**. En cas d'échec : JSON `{"erreur": ..., "url": ...}`
et code de sortie **2** (jamais de trace Python brute au client).

## 4. LE FORMAT DE RÉSULTAT STRUCTURÉ PARTAGÉ (JSON)

> C'est le **contrat commun** entre les outils, les skills (et les sous-agents
> temporaires) et le CHEF.
> Tout le monde parle cette langue.

### 4.1 Enveloppe générale (tout résultat d'outil ou de sous-agent)

```json
{
  "tache": "collecte-annonces | estimation-prix | analyse-quartier | fiche-bien | <outil>",
  "statut": "ok | partiel | echec",
  "entree": { "…les paramètres reçus…" },
  "resultat": { "…le cœur du résultat…" },
  "sources": ["DVF Etalab", "BAN api-adresse"],
  "erreurs": [ { "etape": "dvf", "erreur": "HTTP 503", "url": "…" } ],
  "date": "AAAA-MM-JJ"
}
```

- `statut` : `ok` (tout), `partiel` (certaines briques en échec), `echec` (rien).
- `erreurs` : **toujours** la liste des échecs réels (vide si aucun). Jamais
  silencieux.
- `date` : date de production (aujourd'hui).

### 4.2 Le champ unité « donnée horodatée » (la brique de base)

**Chaque valeur chiffrée** est encapsulée ainsi — jamais un nombre nu :

```json
{ "valeur": 4654, "source": "DVF Etalab", "fiabilite": "verifie",
  "date": "2026-10-08", "note": "…optionnel…" }
```

| Champ | Sens |
|-------|------|
| `valeur` | la donnée (nombre, texte, objet, liste) |
| `source` | **d'où** elle vient (BAN, DVF, ADEME, « calcul »…) |
| `fiabilite` | `verifie` \| `annonce` \| `a_verifier` \| `indisponible` |
| `date` | date de la donnée / de la collecte |
| `note` | précision facultative (ex. « repli bbox ±45 m ») |

### 4.3 Échelle de fiabilité (identique partout)

| `fiabilite` | Sens | Sources |
|-------------|------|---------|
| `verifie` | donnée **officielle** | BAN, IGN, ADEME, DVF, geo.api.gouv |
| `annonce` | **prix affiché** par un vendeur | Bien'ici |
| `a_verifier` | **déduite / incomplète** — à confirmer | repli bbox, CP large |
| `indisponible` | la source n'a pas rendu la donnée | — |

### 4.4 Exemple complet — sortie de `moteur.py` (fiche bien)

```json
{
  "tache": "fiche-bien",
  "statut": "partiel",
  "entree": { "adresse": "25 rue Notre-Dame", "cp": "69006", "surface": 45 },
  "resultat": {
    "adresse_normalisee": { "valeur": "25 Rue Notre-Dame 69006 Lyon",
      "source": "BAN api-adresse", "fiabilite": "verifie", "date": "2026-10-08" },
    "coordonnees": { "valeur": {"lat": 45.764614, "lon": 4.868017},
      "source": "BAN api-adresse", "fiabilite": "verifie", "date": "2026-10-08" },
    "commune": { "valeur": "Lyon 6e", "source": "geo.api.gouv.fr",
      "fiabilite": "verifie", "date": "2026-10-08" },
    "parcelle": { "valeur": {"section": "AB", "numero": "0123"},
      "source": "IGN apicarto", "fiabilite": "a_verifier",
      "note": "repli bbox ±45 m", "date": "2026-10-08" },
    "dpe": { "valeur": {"classe_energie": "C", "classe_ges": "A"},
      "source": "ADEME data-fair", "fiabilite": "verifie", "date": "2026-10-08" },
    "prix_marche": { "valeur": {"mediane_m2": 4654, "nb_ventes": 296},
      "source": "DVF Etalab", "fiabilite": "verifie", "date": "2026-10-08" }
  },
  "etapes": { "geocodage_ban": "ok", "commune": "ok",
    "parcelle_cadastre": "partiel", "dpe_ademe": "ok", "dvf": "ok" },
  "erreurs": [],
  "date": "2026-10-08"
}
```

## 5. Erreur explicite — le contrat d'échec

Un outil **ne devine jamais**. Deux cas seulement :

1. **Source indisponible** → `erreurs: [{ "etape": "...", "erreur": "...", "url": "..." }]`,
   le champ correspondant passe à `indisponible` ou `a_verifier`, `statut` = `partiel`.
2. **Échec total** → `statut: "echec"`, `resultat: {}`, au moins une entrée
   dans `erreurs`. Code de sortie CLI = **2**.

Jamais : une valeur inventée, un `null` silencieux non justifié, une trace
Python montrée au client.

## 6. Pièges connus des outils (à respecter dans le code)

1. **Bien'ici** — sans `zoneId` résolu, le flux renvoie la **France entière**
   (~42 000 annonces). Toujours `resoudre_zone()` d'abord.
2. **Bien'ici** — `publicationDate` = 1970-01-01 souvent : ce n'est PAS que
   l'annonce est ancienne ; `date_modification` reste fiable.
3. **DVF** — fichiers **par département** (~2 Mo gz), pas par commune. L'URL
   redirige (302) vers S3 : suivre la redirection. Cache local dans `/tmp`.
3bis. **DVF — mutations multi-lots** — un immeuble vendu en bloc a PLUSIEURS
   lignes rattachées au même `id_mutation`, et la `valeur_fonciere` globale est
   répétée sur chaque ligne → un €/m² absurde (ex. 75 000 €/m²) qui pollue la
   fourchette min/max. `dvf.py` **exclut** ces mutations et borne les €/m²
   hors [500, 25000] (`exclusions` dans le retour).
4. **IGN apicarto** — `/parcelle?code_insee=…` seul ne renvoie **rien** : il
   faut `geom` (point/bbox) ou `section`+`numero`. Ne **pas** combiner `geom`
   ET `code_insee` (renvoie 0).
5. **BAN** — le point géocodé tombe sur la **voie** → 0 parcelle : prévoir un
   repli bbox (±45 m), fiabilité `a_verifier`.
6. **ADEME** — `qs=` filtre **exact** (à utiliser) ; `q=` est **flou** (à
   éviter). Appariement par adresse **exacte** format BAN, sinon repli CP
   (`a_verifier`).
7. **geo.api.gouv** — pas de `/quartiers` ni `/arrondissements` (404).
8. **Leboncoin** — **INTERDIT** (403 + DataDome). Ne jamais coder un appel.
   Seule voie : **alerte e-mail** (`alerte_email.py`).
9. **Transports (Overpass)** — l'instance principale `overpass-api.de` renvoie
   souvent **504** : le module essaie plusieurs miroirs puis échoue proprement
   (jamais de boucle). Il faut passer le corps en `--data-urlencode` (un POST
   brut en `-d` peut renvoyer 500). Ne PAS déléguer ce calcul à un LLM (il
   boucle) : utiliser `transports.py`.

## 7. Variables d'environnement

- `DVF_CACHE_DIR` : cache DVF (défaut `/tmp/argus-immo-dvf-cache`).
- `IMAP_USER` / `IMAP_PASSWORD` : **uniquement** pour la voie alerte email
  (jamais en dur dans le repo — voir `.gitignore`). Boîte dédiée aux alertes.
- `IMAP_HOST` (défaut `imap.gmail.com`), `IMAP_PORT` (défaut `993`),
  `IMAP_FOLDER` (défaut `INBOX`) : surchargeables pour un autre fournisseur.
- `ARGUS_CLIENT_PASSWORD` / `ARGUS_UI_PASSWORD` : mots de passe des UI
  (dans `ui/.env`, jamais commités).

## 8. Vérification d'un outil (« fini quand »)

- `python3 outils/<module>.py --help` répond.
- Un appel réel rend un JSON **valide** avec `date`, `sources`, `erreurs`.
- Aucune valeur inventée : source absente → `a_verifier`/`indisponible`.
- Aucun secret en dur, aucune dépendance externe à installer (stdlib pur).
