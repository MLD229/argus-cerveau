# Conformité — ce qu'on a le droit de faire

Règle fondatrice du projet : **gratuit et légal d'abord**. On refuse tout ce qui viole des
CGU ou contourne un anti-bot. Vérifié le 2026-10-07 (voir `docs/recherche-veille.md` pour
les sources).

## Portails d'annonces

| Portail | État | Comment on y accède |
|---|---|---|
| **Bien'ici** | ✅ OUVERT | Flux JSON public. **Voie n°1.** Zone via `suggest.json` sinon le filtre zone est ignoré. |
| **SeLoger** | ⚠️ MODÉRÉ | Nécessite Playwright. **Non activé pour l'instant** (zone grise, aucun code actif). |
| **Leboncoin** | ⛔ INTERDIT | 403 + DataDome. **Ne jamais l'utiliser.** |

Tout autre portail : à vérifier au cas par cas (robots.txt + CGU) AVANT d'écrire une ligne
de code.

## Données ouvertes (légales, licence ouverte)

| Source | Usage | Ce qu'on en tire |
|---|---|---|
| **DVF** (Demandes de Valeurs Foncières) | Transactions immobilières réelles | Prix comparables → estimation |
| **DPE ADEME** | Diagnostic de performance énergétique | État énergétique du bien |
| **BAN** (Base Adresse Nationale) | Géocodage | Adresse → coordonnées |
| **INSEE** | Statistiques | Données socio-démographiques du quartier |
| **Cadastre IGN** | Parcelles | Contour/surface |

## Les 9 routes de collecte autorisées

1. Flux/API publics officiels (open data)
2. Alertes email pro → lecture de sa propre boîte
3. API partenaires (quand elles existent et sont ouvertes)
4. saisie manuelle d'une info fournie par un humain (capture d'écran, papier)
5. … *(complété au fil du projet, cf. `docs/recherche-veille.md`)*

## La règle qui tranche : "qui va chercher la page ?"

- Un **humain** fournit une capture d'écran → l'agent lit une image = **autorisé** (= saisie manuelle).
- Un **agent** va automatiquement chercher la page → **interdit** (= scraping) si le site l'exige.

## Règle d'or

Si un doute subsiste sur un site : **on ne l'utilise pas** et on cherche une voie ouverte.
Jamais de contournement d'anti-bot, jamais de produit "API" qui est en fait du scraping
déguisé.
