# Architecture technique — argus-immo (Voie C)

> Statut : **spécification validée**. Ce document est la référence de
> l'architecture. Tout écart doit être justifié ici avant d'être codé.
> Auteur : Rin (agent de code). Vérification : profil `veille` + Asuka.

## 1. Le problème mesuré (v1 → v2)

### v1 : hiérarchie en cascade (26 profils Hermes)

```
CHEF → RESPONSABLE (de pôle) → exécutants + VÉRIFICATEUR → Auditeur → CHEF
```

| Chemin | Latence mesurée |
|--------|-----------------|
| Appel direct à un agent | **~22 s** |
| Cascade à 3 niveaux (v1) | **~11 min** |

Cause : **chaque profil Hermes est un process séparé**. Un `delegate_task` vers
un profil déclenche un **démarrage à froid** : boot des plugins + chargement du
modèle ≈ **40 s**. Trois sauts ⇒ 3 boots + 3 générations LLM en série.

Une cascade ne parallélise rien par défaut : elle **additionne** les latences.

### v2 : un seul cerveau, des outils, des jetables

```
CHEF (1 process) ──┬── SKILL   : procédure (0 process, juste un prompt chargé)
                   ├── OUTIL   : Python pur (0 process LLM, ~1 s)
                   ├── DELEGUE : sous-agent temporaire (process court, jetable)
                   └── VEILLE  : profil isolé (1 process réutilisé, long)
```

Ce qui a changé :

| v1 | v2 | Gain |
|----|----|------|
| Un profil par métier | **skills** (procédures) | 0 boot Hermes |
| Scraping par un LLM | **Python pur** | ~1 s, déterministe, légal |
| Cascade à 3 niveaux | **1 seul CHEF** | ~1 boot total |
| Agents permanents à vérifier | **sous-agents jetables** | pas d'état à maintenir |

## 2. Les quatre étages (et quand chacun s'active)

### Étage 0 — LE CHEF (`hermes --profile chef`)

- **Un seul process Hermes** dans toute l'architecture interactive.
- C'est l'interface : il parle au client en français simple.
- Il **route** (voir `docs/routage.md`) vers un skill, un outil ou une
  délégation. Il ne scrape pas, il ne calcule pas lui-même.
- Modèle : rapide (le CHEF doit répondre vite). C'est le **seul** process qui
  parle au client.

### Étage 1 — SKILLS (procédures)

- Un skill = un fichier `.md` = un **prompt chargé**, **aucun process**.
- Coût en latence : ~0 (le texte est injecté dans le contexte du CHEF).
- Usage : toute procédure répétable (collecter, estimer, rédiger une fiche).
- Emplacement : `skills/<cat>/<nom>.md` (ex. `skills/estimation/estimation-prix.md`).

### Étage 2 — OUTILS PYTHON (`outils/`)

- Python **stdlib** au maximum (`urllib`, `json`, `csv`, `gzip`).
- **Jamais** de LLM pour collecter ou calculer : c'est déterministe, rapide
  (~1 s), vérifiable et légal (pas de « créativité » sur des chiffres).
- Un outil **ne décide pas** : il rend un **JSON structuré** (voir
  `docs/contrat-outils.md`). La décision appartient au CHEF.
- Emplacement : `outils/*.py`, appelables en CLI (`python3 outils/x.py ...`) ou
  en bibliothèque (`from x import ...`).

### Étage 3 — SOUS-AGENTS TEMPORAIRES (`delegate_task`)

- Un sous-agent = un process **court** lancé par `delegate_task` natif, puis
  **jeté**. Aucun profil à créer, aucun état à maintenir.
- Usage : **volume** (N biens à traiter), **parallélisme** (N quartiers à la
  fois), **tâche unique à contexte lourd** (isoler un gros résultat).
- Il ne voit pas la conversation : le CHEF doit tout lui passer dans le brief.
- Détail et critères de choix : `docs/sous-agents-temporaires.md`.

### Étage 4 — PROFIL `veille` (isolé, réutilisable)

- **Le seul profil Hermes en plus du CHEF.** Il tourne à la demande, pour la
  **recherche longue et réutilisable** (veille de marché, surveillance d'un
  secteur, compilation d'un référentiel).
- Il **ne fait pas partie du chemin interactif** : le CHEF ne l'attend pas pour
  répondre. Il travaille en arrière-plan (cron) et dépose son résultat.
- Justification : une tâche de recherche longue **mérite** un process dédié
  qu'on réutilise, plutôt que de tout refaire à chaque appel. Un par métier =
  on retombe dans v1.
- Détail : `docs/sous-agents-temporaires.md` § « profil veille ».

## 3. Budget de latence cible

| Opération | Cible | Chemin |
|-----------|-------|--------|
| Question simple au CHEF | **< 20 s** | 1 process, réponse directe |
| Collecte d'annonces (Bien'ici) | **~2–5 s** | CHEF → `outils/bienici.py` |
| Fiche bien enrichie | **~2 s** | CHEF → `outils/moteur.py` (chaîne open data) |
| Traiter 20 quartiers | **~temps de 1** (parallèle) | CHEF → N sous-agents jetables |
| Veille mensuelle d'un secteur | hors chemin interactif | cron → profil `veille` |

Règle : **aucune opération interactive ne doit booter plus d'un process Hermes**.

## 4. Arborescence

```
argus-immo/
├── README.md                    # présentation + démarrage
├── AGENT.md                     # LE CHEF : identité, ton, mission, routage
├── .gitignore                   # protège secrets/caches
├── corps/
│   ├── chef.md                  # contrat d'identité du profil Hermes `chef`
│   └── veille.md                # contrat d'identité du profil Hermes `veille`
├── docs/
│   ├── architecture.md          # CE DOCUMENT : la Voie C
│   ├── routage.md               # table de routage complète (besoin → agent)
│   ├── contrat-outils.md        # modules Python, signatures, JSON partagé
│   └── sous-agents-temporaires.md  # delegate_task vs profil veille
├── skills/                      # PROCÉDURES métier (0 process, prompt chargé)
│   ├── recherche/collecte-annonces.md   # trouver les annonces
│   ├── estimation/estimation-prix.md    # estimer un bien
│   ├── analyse/analyse-quartier.md      # analyser un quartier
│   └── fiche/fiche-bien.md              # fiche complète d'un bien
├── outils/
│   ├── _http.py                 # helper HTTP partagé (retries, gzip, UA honnête)
│   ├── bienici.py               # annonces Bien'ici (flux JSON ouvert, voie n°1)
│   ├── dvf.py                   # ventes réelles (DVF Etalab) → comparables
│   ├── dpe.py                   # DPE/GES (ADEME data-fair)
│   ├── geocode.py               # adresse → coords + INSEE (BAN)
│   └── moteur.py                # orchestrateur : chaîne les outils → fiche JSON
├── deploy/                      # déploiement ISOLÉ (conteneur Docker)
│   ├── Dockerfile               # image Hermes isolée (profil chef/veille)
│   ├── docker-compose.yml       # monte projet (:ro) + vault (:rw) dans le conteneur
│   └── sync-projet.sh           # pousse profils + skills + projet dans le conteneur
└── tests/
    ├── verify-squelette.sh      # vérifie que l'arborescence existe
    ├── verify-outils.sh         # vérifie les outils Python (exécution réelle)
    └── verify-docs.sh           # vérifie la cohérence des documents
```

Le **sous-cerveau** (vault Obsidian) vit HORS du repo, monté dans le conteneur :
`~/Obsidian/ArgusImmoVault/` (isolé du vault perso de l'opérateur).

## 5. Ce qui est INTERDIT (conformité)

1. **Leboncoin** : robots interdit les robots, test réel = HTTP 403 + DataDome.
   **Ne jamais tenter**, même avec un navigateur. Seule voie : alerte email.
2. **Contourner** un blocage (403 / CAPTCHA / anti-bot / CGU) = violation de la
   charte. Un navigateur ne change **pas** la légalité.
3. **Inventer une donnée.** Absent → `a_verifier`. Échec → erreur claire. Jamais
   de valeur devinée par un LLM sur un chiffre (prix, surface, DPE).
4. **Un LLM pour collecter/calculer.** Collecte et calcul = Python pur.

## 6. Ce que cette architecture NE fait PAS

- Elle ne crée pas de profil par métier (ce serait v1 déguisé).
- Elle ne met pas de LLM dans la boucle de collecte (lent + non fiable).
- Elle ne fait pas attendre le client devant une cascade : si une tâche est
  longue, elle part en arrière-plan (cron / profil `veille`) et le CHEF rend
  la main avec un statut.

## 7. Critères de réussite (vérifiables)

- [ ] `hermes --profile chef -z "qui es-tu ?"` répond en **< 20 s**.
- [ ] `python3 outils/bienici.py zone "Lyon"` rend un zoneId réel.
- [ ] `python3 outils/moteur.py --adresse ... --cp ... --surface ...` rend une
      fiche JSON avec `champs` + `etapes` + `erreurs`.
- [ ] Traiter 3 quartiers en parallèle prend ≈ le temps d'un seul.
- [ ] Aucun fichier ne mentionne une source interdite comme utilisable.
