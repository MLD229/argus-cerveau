---
name: analyse-quartier
description: >-
  Analyser un quartier ou une commune pour un particulier : niveau de prix réel
  des ventes (DVF), dynamique du marché, adresse administrative (commune,
  arrondissement, population). Utiliser quand un client demande « c'est bien
  comme quartier ? », « les prix montent ici ? », « c'est quel arrondissement ? ».
  Rend une note de quartier sourcée.
version: 1.0.0
author: Rin (argus-immo)
license: MIT
metadata:
  hermes:
    tags: [quartier, analyse, dvf, geocode, marche, immobilier]
    category: analyse
---

# Skill — ANALYSE DE QUARTIER

> Procédure métier chargée par le CHEF (aucun process) — suivie telle quelle.

## 1. Quand l'utiliser

Le client dit :
- « c'est bien comme quartier, <nom / rue> ? »
- « les prix montent ou baissent ici ? »
- « c'est quel arrondissement / c'est où exactement ? »
- « je veux comparer deux quartiers »

C'est le skill du **contexte géographique**. Il ne dit pas si un quartier
est « sympa » (subjectif) : il donne des **faits sourcés** (prix, dynamique,
adresse administrative) et laisse le client juger.

## 2. Ce qu'il reçoit (entrées)

| Entrée | Obligatoire | Note |
|--------|-------------|------|
| lieu (quartier / rue / commune) | oui | à localiser |
| surface de référence (m²) | non | sinon analyse en €/m² |
| années à comparer | non | défaut : 2 dernières années DVF |
| périmètre | non | défaut : commune entière |

## 3. Ce qu'il fait (étapes)

1. **Géocoder / localiser** le lieu → coords, code INSEE, commune :
   ```bash
   python3 outils/geocode.py "quartier Monplaisir Lyon 8"
   ```
2. **Confirmer le statut administratif** (commune / arrondissement, population)
   via l'outil de commune (dans `geocode.py` ou `geo_commune`).
   ⚠ Piège connu : `geo.api.gouv` n'expose **ni quartiers ni arrondissements**
   directement → les arrondissements de Lyon/Marseille/Paris sont reconstitués
   via une **table INSEE CP→INSEE**.
3. **Récupérer les ventes réelles** sur **plusieurs années** (DVF) pour voir la
   **tendance** :
   ```bash
   python3 outils/dvf.py --commune 69388 --annees 2023 2024 --type Appartement
   ```
4. **Calculer** : médiane €/m² par année, **évolution** (hausse/baisse %),
   nombre de ventes (activité du marché), min/max.
5. **Résumer** en langage clair, avec les sources. Distinguer **fait** et
   **ressenti** (« je ne juge pas si c'est agréable, voici les chiffres »).

## 4. Ce qu'il rend (sortie)

```json
{
  "tache": "analyse-quartier",
  "statut": "ok | partiel | echec",
  "entree": { "lieu": "Monplaisir, Lyon 8", "annees": [2023, 2024] },
  "resultat": {
    "localisation": {
      "commune": "Lyon 8e",
      "code_insee": "69388",
      "population": 82158,
      "fiabilite": "verifie",
      "source": "geo.api.gouv.fr"
    },
    "prix_median_m2_par_an": [
      { "annee": 2023, "valeur": 4100, "source": "DVF Etalab", "fiabilite": "verifie" },
      { "annee": 2024, "valeur": 4220, "source": "DVF Etalab", "fiabilite": "verifie" }
    ],
    "evolution": { "valeur_pct": 2.9, "sens": "hausse", "periode": "2023→2024" },
    "activite_marche": { "nb_ventes_2024": 540, "note": "marché actif" },
    "resume": "Les ventes réelles à Lyon 8e sont passées d'environ 4 100 à 4 220 €/m² entre 2023 et 2024, soit +2,9 %. Le marché est actif (540 ventes en 2024).",
    "limites": ["le quartier exact dans la commune n'est pas isolable dans DVF (données communales)"],
    "date_detection": "2026-10-08"
  },
  "sources": ["DVF Etalab", "geo.api.gouv.fr", "BAN api-adresse"],
  "erreurs": [],
  "date": "2026-10-08"
}
```

## 5. Outils appelés

| Outil | Fonction | Rôle |
|-------|----------|------|
| `outils/geocode.py` | `geocoder(adresse)` | localiser lieu → INSEE |
| `outils/geocode.py` | `commune(code_insee)` | commune/arrondissement, population |
| `outils/dvf.py` | `ventes_comparables(code_commune, annees)` | prix réels + tendance |

> ⚠ Les **équipements** (écoles, transports) ne sont **pas** dans ces outils.
> Si le client les demande, le CHEF les traite en **connaissance générale** et
> **précise** que ce n'est pas vérifié par une source officielle ici.

## 6. Règles de fiabilité

- DVF = ventes réelles → `verifie`. Commune/population (geo.api.gouv) → `verifie`.
- L'**évolution de prix** est calculée sur la médiane annuelle : la signaler
  comme **indication** (échantillons annuels différents).
- **Ne pas** juger la qualité de vie (subjectif) — donner des faits.
- DVF est **communal** : le « quartier » n'est pas isolable → le **dire**
  (limite), ne pas prétendre à une précision infra-communale.

## 7. Interdits

- **Ne jamais** présenter un jugement subjectif (« c'est un bon quartier »)
  comme un fait.
- **Ne jamais** inventer une donnée de sécurité, d'école ou de transport sans
  source officielle vérifiée.
- Ne pas confondre **prix affiché** (annonce) et **prix de vente réel** (DVF).
- Aucun contournement de site bloqué.

## 8. Vérification (« fini quand »)

- La **localisation** est confirmée (commune, INSEE, population).
- Il y a au moins **2 années** de prix réels comparés → une tendance chiffrée.
- Le **nombre de ventes** (activité) est donné.
- Les **limites** (précision communale) sont explicitées.
- Chaque chiffre a sa source + date.

## 9. Suite

- Pour estimer un bien précis dans ce quartier → `estimation-prix`.
- Pour la fiche complète d'un bien → `fiche-bien`.
- Pour **comparer 5 quartiers en parallèle** → le CHEF **délègue** (sous-agents
  temporaires).
