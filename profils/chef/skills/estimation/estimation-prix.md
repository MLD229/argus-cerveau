---
name: estimation-prix
description: >-
  Estimer la valeur d'un bien immobilier à partir de son adresse, sa surface et
  sa commune, en s'appuyant sur les VENTES RÉELLES (base DVF) et le DPE (ADEME).
  Utiliser quand un client demande « ça vaut combien ? », « c'est un bon prix ? »
  ou « je peux négocier combien ? ». Rend une FOURCHETTE sourcée, jamais un
  chiffre unique inventé.
version: 1.0.0
author: Rin (argus-immo)
license: MIT
metadata:
  hermes:
    tags: [estimation, prix, dvf, dpe, comparables, immobilier]
    category: estimation
---

# Skill — ESTIMATION DE PRIX

> Procédure métier chargée par le CHEF (aucun process) — suivie telle quelle.

## 1. Quand l'utiliser

Le client dit :
- « ça vaut combien, ce bien / cet appart ? »
- « c'est un bon prix à 350 000 € pour 62 m² ? »
- « je peux négocier combien sur cette annonce ? »
- « c'est combien au m² par ici ? »

C'est le skill de la **valeur**. Il répond avec des **ventes réelles**
(DVF), pas avec une intuition.

## 2. Ce qu'il reçoit (entrées)

| Entrée | Obligatoire | Note |
|--------|-------------|------|
| adresse | oui | pour localiser (géocodage BAN) |
| code postal ou commune | oui | cible du calcul DVF |
| surface (m²) | oui | pour convertir €/m² → prix total |
| type de bien (`appartement`, `maison`) | non | filtre DVF |
| prix affiché (si annonce) | non | pour comparer et dire si c'est cher/bon |

Si `surface` manque → l'estimation reste en **€/m²** et il faut le dire.

## 3. Ce qu'il fait (étapes)

1. **Géocoder** l'adresse pour confirmer la commune (code INSEE) :
   ```bash
   python3 outils/geocode.py "25 rue Notre-Dame 69006 Lyon"
   ```
2. **Récupérer les ventes réelles comparables** (DVF) dans la commune :
   ```bash
   python3 outils/dvf.py --commune 69386 --annees 2024 --type Appartement --surface 62
   ```
   - Garder les ventes de **moins de 5 ans**, **surface comparable (±20 %)**.
   - Calculer : **nombre**, **médiane €/m²**, min, max.
3. **Connaître le DPE** du bien (impact sur la valeur, surtout passoire
   énergétique F/G) :
   ```bash
   python3 outils/dpe.py --adresse "21 Rue Dussaussoy 69006 Lyon"
   ```
4. **Construire une fourchette** : appliquer la médiane €/m² à la surface, avec
   une marge ±5 % (état, étage, DPE). **Jamais un chiffre unique.**
5. **Comparer** au prix affiché si fourni → « au-dessus / en-dessous du marché ».

## 4. Ce qu'il rend (sortie)

```json
{
  "tache": "estimation-prix",
  "statut": "ok | partiel | echec",
  "entree": { "adresse": "...", "surface": 62, "commune": "69386" },
  "resultat": {
    "fourchette_prix": {
      "valeur": [290000, 320000],
      "source": "DVF Etalab (ventes réelles, Lyon 6e, 2024)",
      "fiabilite": "verifie",
      "date": "2026-10-08"
    },
    "prix_median_m2": {
      "valeur": 4654,
      "source": "DVF Etalab (296 ventes, Lyon 6e, 2024)",
      "fiabilite": "verifie",
      "date": "2026-10-08"
    },
    "nb_comparables": 18,
    "dpe": { "classe_energie": "C", "classe_ges": "A", "fiabilite": "verifie" },
    "comparaison_annonce": "Le prix affiché (350 000 €) est ~11 % au-dessus de la fourchette : marge de négociation possible.",
    "methode": "médiane des ventes réelles < 5 ans, surface ±20 %, même commune, marge ±5 %",
    "reserves": ["le DPE F/G peut baisser la valeur de 5–15 %"],
    "date_detection": "2026-10-08"
  },
  "sources": ["DVF Etalab", "BAN api-adresse", "ADEME data-fair"],
  "erreurs": [],
  "date": "2026-10-08"
}
```

## 5. Outils appelés

| Outil | Fonction | Rôle |
|-------|----------|------|
| `outils/geocode.py` | `geocoder(adresse)` | adresse → coords + INSEE |
| `outils/dvf.py` | `ventes_comparables(code_commune, ...)` | ventes réelles → stats €/m² |
| `outils/dpe.py` | `dpe_par_adresse(adresse)` | classe énergie/GES |

> ⚠ Le calcul de la fourchette est un **calcul** : il se fait dans `outils/`
> (ou par arithmétique simple du CHEF sur les valeurs DVF). **Jamais** un LLM
> qui « devine » un prix.

## 6. Règles de fiabilité

- DVF = ventes **réelles enregistrées** → fiabilité `verifie` (source officielle).
- DPE = donnée officielle ADEME → `verifie` ; repli par code postal → `a_verifier`.
- Nombre de comparables **faible** (< 5) → le signaler, fourchette plus large.
- L'estimation reste une **fourchette indicative**, jamais une garantie.
- Toujours donner l'**année** des ventes utilisées (le marché bouge).

## 7. Interdits

- **Ne jamais** rendre un prix unique présenté comme certain.
- **Ne jamais** inventer un €/m² quand DVF ne rend rien → dire « pas assez de
  ventes comparables sur cette commune ».
- **Ne pas** ignorer un DPE F/G (impact réel sur la valeur).
- Ne pas utiliser les **prix d'annonce** comme preuve de valeur (ce sont des
  prix demandés, `annonce` — pas des prix de vente).

## 8. Vérification (« fini quand »)

- Il y a une **fourchette** (bornes min/max), pas un chiffre unique.
- Chaque valeur porte sa **source** et sa **date**.
- Le **nombre de comparables** est donné.
- Le **DPE** est mentionné (ou `a_verifier`).
- Si trop peu de ventes → c'est **dit** explicitement (statut `partiel`).

## 9. Suite

- Pour la fiche complète d'un bien (adresse, parcelle, copro…) → `fiche-bien`.
- Pour comprendre un quartier (tendances, équipements) → `analyse-quartier`.
