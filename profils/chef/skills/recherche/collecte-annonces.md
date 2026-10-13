---
name: collecte-annonces
description: >-
  Trouver des annonces immobilières (achat/location) via les voies AUTORISÉES —
  Bien'ici (flux JSON ouvert, voie n°1, ACTIVE). SeLoger existe en code mais
  n'est PAS activé pour l'instant (zone grise). Utiliser dès qu'un client dit
  « trouve-moi des biens / des apparts / des annonces à vendre ou à louer ».
  Interdit absolu : Leboncoin (blocage anti-bot) et tout contournement.
version: 1.0.0
author: Rin (argus-immo)
license: MIT
metadata:
  hermes:
    tags: [collecte, annonces, bienici, seloger, immobilier]
    category: collecte
---

# Skill — COLLECTE D'ANNONCES

> Procédure métier chargée par le CHEF (aucun process) — suivie telle quelle.

## 1. Quand l'utiliser

Le client dit (ou veut dire) :
- « trouve-moi des apparts / maisons / locaux à vendre à <ville> »
- « qu'est-ce qui est à louer dans mon budget sur <quartier> ? »
- « montre-moi des biens avec 3 pièces à moins de X € »
- « je cherche <type> autour de <lieu>, <surface> m², <budget> »

C'est le skill de la **découverte** : il part d'un besoin et rend une
**liste de biens** (pas encore enrichis — voir ensuite `fiche-bien`).

## 2. Ce qu'il reçoit (entrées)

| Entrée | Obligatoire | Défaut |
|--------|-------------|--------|
| lieu (ville / quartier / arrondissement) | **oui** | — |
| transaction (`buy` = acheter, `rent` = louer) | **oui** | `buy` |
| types de bien (`appartement`, `maison`, `bureau`…) | non | tous |
| budget max / min (€) | non | aucun |
| surface min / max (m²) | non | aucun |
| nb de pièces min | non | aucun |
| spécifique (RDC, ascenseur…) | non | aucun |

Si `lieu` ou `transaction` manque → **demander** (une question, pas tout d'un coup).

## 3. Ce qu'il fait (étapes)

1. **Résoudre la zone Bien'ici — PIÈGE N°1, obligatoire.**
   Sans `zoneId` résolu, le flux ignore le filtre et renvoie la **France
   entière** (~42 000 annonces). Toujours appeler d'abord :
   ```bash
   python3 outils/bienici.py zone "Lyon 6"
   # → {"zoneIds": ["-120968"], ...}
   ```
2. **Interroger Bien'ici** (voie n°1, ACTIVE) avec les filtres :
   ```bash
   python3 outils/bienici.py annonces --zone "Lyon 6" --transaction buy \
       --types appartement --surface-min 40 --prix-max 400000
   ```
   Les types s'écrivent en **français** (`appartement`, `maison`, `bureau`…) —
   l'outil les traduit vers l'API. Un type inconnu **lève une erreur**, il ne
   renvoie jamais 0 annonce en silence.
3. **SeLoger : NON ACTIVÉ pour l'instant** (`python3 outils/bienici.py seloger`
   échoue proprement). Ne pas s'appuyer dessus ; c'est une zone grise laissée
   de côté. *Il n'y a **pas** d'« API Notaires » : aucune source ouverte gratuite
   n'existe — ne pas la promettre.*
4. **Fusionner + dédupliquer** les lots (clé : URL ; sinon ville+prix+surface+type).
5. **Normaliser** chaque annonce au format partagé (§4).

## 4. Ce qu'il rend (sortie)

```json
{
  "tache": "collecte-annonces",
  "statut": "ok | partiel | echec",
  "entree": { "lieu": "...", "transaction": "buy", "filtres": { } },
  "resultat": {
    "nb_annonces": 12,
    "annonces": [
      {
        "id": "bienici:12345",
        "titre": "Appartement 3 pièces 62 m²",
        "type": "appartement",
        "transaction": "buy",
        "ville": "Lyon 6e",
        "quartier": null,
        "surface": { "valeur": 62, "source": "Bien'ici", "fiabilite": "annonce", "date": "2026-10-08" },
        "prix":    { "valeur": 349000, "source": "Bien'ici", "fiabilite": "annonce", "date": "2026-10-08" },
        "prix_m2": { "valeur": 5629, "source": "calcul", "fiabilite": "annonce", "date": "2026-10-08" },
        "etage": 2,
        "ascenseur": true,
        "dpe": null,
        "url_annonce": "https://www.bienici.com/...",
        "source_portail": "Bien'ici",
        "agence": "Agence X",
        "date_modification": "2026-10-05",
        "prix_baisse": false,
        "date_detection": "2026-10-08"
      }
    ]
  },
  "sources": ["Bien'ici"],
  "erreurs": [],
  "date": "2026-10-08"
}
```

## 5. Outils appelés

| Outil | Fonction | Rôle |
|-------|----------|------|
| `outils/bienici.py` | `resoudre_zone(texte)` | obtenir le `zoneId` (obligatoire) |
| `outils/bienici.py` | `chercher_annonces(zone, transaction, ...)` | lister les annonces |
| `outils/bienici.py` | `chercher_seloger_playwright(url)` | SeLoger — **non activé** (échoue proprement) |
| `outils/_http.py` | `http_get_json(...)` | transport HTTP partagé |

> ⚠ **Aucun LLM ne lit une page web.** La collecte est faite par `bienici.py`.
> Le skill décrit seulement *quand* et *avec quels filtres*.

## 6. Règles de fiabilité

- Toute donnée issue d'une **annonce** = fiabilité `annonce` (**pas** `verifie`) :
  c'est un prix **affiché**, pas un prix de vente réel.
- Champ absent → `a_verifier`, jamais inventé.
- `date_detection` = jour de la collecte (toujours connu).
- `date_mise_en_vente` souvent absente sur Bien'ici → `a_verifier`
  (ne PAS en déduire que l'annonce est ancienne ; `date_modification` est fiable).
- `prix_baisse = true` (`priceHasDecreased`) = **marge de négociation** à signaler.

## 7. Interdits

- **Leboncoin** : robots interdit les robots ; test réel = HTTP 403 + DataDome.
  **Ne jamais tenter**, même avec un navigateur. Seule voie : alerte email.
- **Logic-Immo** : DataDome, idem.
- **Contourner** un blocage (403 / CAPTCHA / anti-bot / CGU) = violation de la
  charte. Un navigateur ne change **pas** la légalité.
- Inventer une annonce, un prix ou une surface.

## 8. Vérification (« fini quand »)

- Chaque annonce a : **URL**, **prix**, **source**, **fiabilité**, **date de
  détection**.
- Les lots des différentes voies sont **fusionnés et dédupliqués**.
- La `zone` a été **résolue** (pas de « France entière »).
- Un blocage éventuel est signalé comme **échec propre** (voies tentées + raison),
  sans aucune donnée inventée.

## 9. Suite

- Pour enrichir un bien trouvé (DPE, parcelle, prix du marché) → `fiche-bien`
  ou `estimation-prix`.
- Pour un volume (> ~5 biens) → le CHEF **délègue** en sous-agents temporaires
  (`docs/sous-agents-temporaires.md`).
