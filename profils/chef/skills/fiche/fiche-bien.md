---
name: fiche-bien
description: >-
  Produire la fiche complète d'un bien immobilier : adresse normalisée,
  coordonnées, commune/arrondissement, parcelle cadastrale, DPE/GES, et prix du
  marché environnant. Utiliser quand un client dit « fais-moi la fiche de ce
  bien », « dis-moi tout sur ce logement », ou quand un bien vient d'être
  collecté et doit être enrichi. S'appuie sur l'outil Python moteur.py.
version: 1.0.0
author: Rin (argus-immo)
license: MIT
metadata:
  hermes:
    tags: [fiche, bien, enrichissement, dvf, dpe, cadastre, geocodage]
    category: fiche
---

# Skill — FICHE BIEN (bien enrichi)

> Procédure métier chargée par le CHEF (aucun process) — suivie telle quelle.

## 1. Quand l'utiliser

Le client dit :
- « fais-moi la fiche complète de ce bien »
- « dis-moi tout sur ce logement : énergie, adresse, prix du marché »
- « on a cette annonce, qu'est-ce qu'on peut en savoir ? »

C'est le skill de l'**enrichissement** : un bien est **déjà en main**
(adresse + surface + commune, par ex. issu de `collecte-annonces`) et il faut
toutes les données officielles autour.

## 2. Ce qu'il reçoit (entrées)

| Entrée | Obligatoire | Note |
|--------|-------------|------|
| adresse | oui | format libre (« 25 rue Notre-Dame ») |
| code postal / commune | oui | ou code INSEE |
| surface (m²) | non | utile pour DVF et prix total |
| type de bien | non | filtre DVF |
| année DVF | non | défaut : dernière année |

## 3. Ce qu'il fait (étapes)

1. **Appeler l'orchestrateur** — un **seul** appel chaîne tout :
   ```bash
   python3 outils/moteur.py --adresse "25 rue Notre-Dame" --cp 69006 \
       --surface 45 --type Appartement --annee 2024
   ```
   `moteur.py` enchaîne dans l'ordre :
   **géocodage BAN → commune/arrondissement → parcelle IGN → DPE ADEME →
   ventes comparables DVF**.
2. **Lire le JSON** : `champs` (chaque valeur + source + fiabilité),
   `etapes` (ok/partiel/echec/ignore par brique), `erreurs` (sources en échec).
3. **Repérer** les champs `a_verifier` (repli dégradé, ex. parcelle par bbox)
   et les rendre **explicitement** comme « à confirmer ».
4. **Traduire** en langage client (le CHEF s'en charge) : pas de JSON brut.

## 4. Ce qu'il rend (sortie)

```json
{
  "tache": "fiche-bien",
  "statut": "ok | partiel | echec",
  "entree": { "adresse": "25 rue Notre-Dame", "cp": "69006", "surface": 45 },
  "resultat": {
    "adresse_normalisee": {
      "valeur": "25 Rue Notre-Dame 69006 Lyon",
      "source": "BAN api-adresse", "fiabilite": "verifie", "date": "2026-10-08"
    },
    "coordonnees": {
      "valeur": { "lat": 45.764614, "lon": 4.868017 },
      "source": "BAN api-adresse", "fiabilite": "verifie", "date": "2026-10-08"
    },
    "commune": {
      "valeur": "Lyon 6e", "code_insee": "69386", "population": 49385,
      "source": "geo.api.gouv.fr", "fiabilite": "verifie", "date": "2026-10-08"
    },
    "parcelle": {
      "valeur": { "section": "AB", "numero": "0123", "contenance": 420 },
      "source": "IGN apicarto", "fiabilite": "a_verifier",
      "note": "repli bbox (±45 m) : rattachement à confirmer", "date": "2026-10-08"
    },
    "dpe": {
      "valeur": { "classe_energie": "C", "classe_ges": "A" },
      "source": "ADEME data-fair", "fiabilite": "verifie", "date": "2026-10-08"
    },
    "prix_marche": {
      "valeur": { "mediane_m2": 4654, "nb_ventes": 296 },
      "source": "DVF Etalab", "fiabilite": "verifie", "date": "2026-10-08"
    }
  },
  "etapes": {
    "geocodage_ban": "ok",
    "commune": "ok",
    "parcelle_cadastre": "partiel",
    "dpe_ademe": "ok",
    "dvf": "ok"
  },
  "erreurs": [],
  "date": "2026-10-08"
}
```

> Le format exact de `resultat` reprend celui du **format partagé**
> (`docs/contrat-outils.md` §4) : chaque champ = `{valeur, source, fiabilite, date}`.

## 5. Outils appelés

| Outil | Fonction | Rôle |
|-------|----------|------|
| `outils/moteur.py` | `enrichir_bien(adresse, surface, commune, ...)` | **orchestrateur** : chaîne tout |
| ↳ `outils/geocode.py` | BAN + commune | géocodage, INSEE |
| ↳ `outils/` (cadastre) | parcelle IGN | section, n°, contenance |
| ↳ `outils/dpe.py` | ADEME | classe énergie/GES |
| ↳ `outils/dvf.py` | Etalab | ventes comparables |

> ⚠ **Un seul appel** à `moteur.py` suffit : ne ré-appelle pas les briques à la
> main (c'est plus lent et tu risques de désynchroniser les dates).

## 6. Règles de fiabilité

- Sources **officielles** (BAN, geo.api.gouv, IGN, ADEME, DVF) → `verifie`.
- Un **repli dégradé** (parcelle par bbox, DPE par code postal) → `a_verifier`,
  avec une `note` explicative.
- Source en échec → dans `erreurs`, **jamais** un silence ni une valeur devinée.
- Chaque champ porte sa **date** (les données vieillissent).

## 7. Interdits

- **Ne jamais** inventer une parcelle, un DPE ou une surface manquants.
- **Ne pas** combiner `geom` **et** `code_insee` sur apicarto IGN (renvoie 0) —
  laisser `moteur.py` gérer la logique.
- **Ne pas** présenter un repli dégradé comme `verifie`.
- Aucun contournement de site bloqué, aucun LLM dans la collecte.

## 8. Vérification (« fini quand »)

- La fiche a **au moins** : adresse normalisée, coordonnées, commune, DPE.
- Chaque valeur a **source + fiabilité + date**.
- Les `erreurs` et les `a_verifier` sont **explicites**.
- Le champ `etapes` indique ok/partiel/echec par brique.
- Aucune valeur inventée.

## 9. Suite

- Pour **volume** (N biens d'un coup) → le CHEF **délègue** en sous-agents
  temporaires (`docs/sous-agents-temporaires.md`).
- Pour la valeur marchande détaillée → `estimation-prix`.
- Pour le contexte du quartier → `analyse-quartier`.
