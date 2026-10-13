---
name: filtre-recherche
description: >-
  Panneau de critères AVANT toute recherche de biens — c'est le « VISÉE ».
  À utiliser dès que le client demande de trouver / chercher / lister des biens,
  des annonces, des appartements, des locaux ou des cabinets — à Lyon (défaut)
  ou dans toute ville de France nommée — AVANT
  d'appeler le moindre outil de collecte. L'agent affiche d'abord, dans le chat,
  un panneau structuré récapitulant et laissant ajuster : zone /
  arrondissements, surface, budget, type de bien, rez-de-chaussée oui/non,
  priorités, distance aux transports. L'agent choisit lui-même les TITRES des
  questions et leurs OPTIONS. Deux niveaux : l'outil natif `clarify` (boutons à
  choix) pour le discret, et le contrôle RICHE `slider` / `plage` (extension JS
  argus-visee) pour tout ce qui est une VALEUR CONTINUE. Le panneau riche
  s'OUVRE AUTOMATIQUEMENT côté navigateur : l'agent pose un `clarify` dont la
  question porte un marqueur (profil-client/visee_protocole.py) et
  argus-visee-auto.js le détecte puis affiche la carte. Ne PAS l'afficher si
  la demande est déjà complète ou si le client est en mode auto.
version: 2.0.0
author: Argus Immo — profil client
license: MIT
metadata:
  hermes:
    tags: [recherche, panneau, visée, criteres, clarify, slider, filtre, cadrage]
    category: recherche
---

# Skill — VISÉE (panneau filtre : critères avant recherche)

> Règle produit : quand je m'apprête à CHERCHER des biens, je montre D'ABORD un
> petit panneau de critères que le client ajuste d'un clic (ou d'un glissé).
> Sauf demande déjà complète, ou mode auto.
>
> Je choisis moi-même les TITRES des questions et le contenu des OPTIONS : rien
> n'est figé. Ce document donne les gabarits, pas des questions imposées.

## 1. Quand afficher / ne pas afficher

**AFFICHER** — demande de RECHERCHE de biens (« trouve-moi… », « cherche… »,
« montre-moi des… ») ET demande incomplète (zone, budget, surface, type ou RDC
manquant), critères pas encore donnés dans cette conversation.

**NE PAS afficher** —
- demande **complète** (zone + budget + surface + type + RDC présents) → chercher direct ;
- **mode auto / feu vert** (« cherche sans me demander », « débrouille-toi »,
  « comme d'habitude », « ne me demande rien ») → chercher sans panneau ;
- **hors recherche** : estimation d'un bien précis, analyse de quartier, prix au
  m², fiche, DPE, explication, notifications, suivi sur des biens déjà trouvés ;
- un panneau est **déjà en attente** (ne pas en relancer un second) ;
- **suivi immédiat** sur des résultats existants.

## 2. Comment l'afficher — DEUX niveaux

Je choisis le niveau selon la NATURE du critère : CHOIX parmi une liste →
natif ; VALEUR CONTINUE (distance, budget, surface) → riche.

### A. Niveau natif — l'outil `clarify`

Chaque `question` + `choices` devient une rangée cliquable ; le WebUI ajoute
une ligne « Autre ». Le **premier choix est marqué « (Recommended) »** : je mets
donc TOUJOURS en tête l'option que je recommande.

- J'omets un champ déjà compris de la demande.
- **Que des options dans `choices`**, jamais énumérées dans le texte.
- `multi_select: true` pour les réponses multiples (arrondissements, types).
- Maximum 5 questions par appel, 4 choix par question.

### B. Niveau riche — `slider` et `plage` (extension `argus-visee.js`)

`clarify` **ne sait faire NI curseur NI plage** (contrat = `question + choices +
multi_select`). Pour une valeur continue, j'utilise le contrôle riche :
**`slider`** (un nombre, une borne) ou **`plage`** (intervalle min-max). À la
validation, la valeur revient à l'agent **via l'API clarify existante**
(`POST /api/clarify/respond`) sous forme de texte normalisé — je la lis donc
EXACTEMENT comme une réponse de `clarify`. Modèle + sérialisation :
`profil-client/controles.py` (testé par `tests/verify-controles.py`).

| Critère | Contrôle |
|---|---|
| Distance max au métro / arrêt TCL | `slider` (min 100, max 1500, pas 50, m) |
| Budget maximum | `slider` (pas de 25 000 €) |
| Fourchette de budget | `plage` |
| Surface | `plage` (ex. 40-120 m²) |
| Étage souhaité | `slider` (0 = RDC) |

> Règle simple : si je peux répondre d'un curseur (« plus ou moins ») plutôt
> que d'un clic (« oui / non »), c'est un slider ou une plage.

### C. Protocole « panneau riche » — l'ouverture automatique

`clarify` seul ignore qu'un contrôle est riche. Pour que la carte Visée s'ouvre
**toute seule**, on met un MARQUEUR dans la `question` du clarify — **aucun
canal ni route nouveau**.

**En 3 temps :**

1. Je construis le panneau et j'obtiens la question marquée :

   ```python
   import sys; sys.path.insert(0, "profil-client")
   import visee_protocole as V
   args = V.poser(panneau, titre="Visée — affiner la recherche")
   # args = {"question": "⟦VISEE:1:<base64url>⟧ Visée — affiner la recherche",
   #         "choices": [], "panneau": {...}}
   ```

2. Je pose un `clarify` **NORMAL** avec `question = args["question"]` et
   `choices = []`. Ce clarify reste **EN ATTENTE** — condition pour que
   `/api/clarify/respond` accepte la réponse.

   > Panneau mixte (discret + riche) : je pose DEUX choses — le `clarify`
   > marqué **puis** les questions natives à boutons. Répondre à la carte riche
   > suffit à débloquer le clarify en attente.

3. J'attends la réponse. Côté navigateur, `argus-visee-auto.js` polle
   `/api/clarify/pending`, décode le marqueur, ouvre
   `window.argusVisee.presenter(...)`, masque la carte native et, sur
   « Valider », POSTe la réponse normalisée. Je reçois donc un TEXTE comme une
   réponse de `clarify`.

**Le marqueur :** `⟦VISEE:1:<base64url(json {"titre":…, "controles":[…]})>⟧ <titre lisible>`

- Le module `visee_protocole.py` (`encoder_question`, `decoder_question`,
  `est_marquee`, `poser`) est la référence exécutable ; le JS
  `argus-visee-auto.js::decoderMarqueur` est son jumeau navigateur.
- Le texte APRÈS le marqueur reste **lisible** : sans l'extension, le client
  voit une question ordinaire et répond en texte libre.
- Normalisation identique des deux côtés (bornage + arrondi au pas) → l'agent
  reçoit la MÊME valeur.

### Composer le panneau (l'agent décide)

1. Je pars des **champs** ci-dessous, dans cet ordre, et je RETIRE ceux déjà
   donnés par la demande.
2. Je **choisis le TITRE** de chaque champ (français, court, concret). Un titre
   **non vide** est obligatoire — le modèle le refuse sinon.
3. Je **choisis les OPTIONS** des contrôles discrets (jamais figées).
4. Je mélange les niveaux : discrets pour zone/types/RDC, riches pour
   distance/budget/surface. Les contrôles riches ne comptent PAS dans la limite
   des 5 questions de `clarify`.
5. Je garde le panneau COURT : 2 à 4 contrôles natifs + 1 à 3 riches.

**Champs, dans l'ordre :** périmètre/zone (multi) · arrondissements (multi, si
plusieurs) · budget (`slider` ou `plage`) · surface (`plage`) · type de bien
(multi) · distance transports (`slider`) · rez-de-chaussée (choix) · priorités
(choix).

> Si la demande précise déjà la zone, ne PAS poser la question de zone. Gabarits
> prêts à l'emploi : `controles.py :: controles_predefinis()`.

## 3. Après le panneau

1. Je lis les réponses — panneau natif : `responses[].user_response` ; panneau
   riche : la carte POSTe sur `/api/clarify/respond`, je la reçois **exactement
   comme une réponse de clarify**.
2. Un slider / une plage revient en TEXTE normalisé, par ex.
   `Visée — réponses (3) : Distance max au métro = 500 m · Budget maximum =
   425000 € · Surface = 40-120 m²`. Les contrôles non répondus = « peu importe ».
3. Chaque critère répondu remplace/complète le brief (zone, budget, surface,
   type, RDC, distance).
4. « Autre » (texte libre) : je l'interprète simplement.
5. ALORS seulement j'appelle la collecte (`/opt/tools/bienici.py`, skill
   `chasse-professions-liberales`).

## 4. Exemples de panneau

**Natif (repli)** — « trouve-moi un local à Lyon », zone donnée :

```json
{"questions": [
  {"question": "Quel budget maximum ?", "choices": ["400 000 €", "250 000 €", "600 000 €", "Peu importe"]},
  {"question": "Quelle surface ?", "choices": ["30-100 m²", "100-200 m²", "Peu importe (30-200 m²)"]},
  {"question": "Quels types de bien ?", "multi_select": true, "choices": ["Appartement", "Local commercial", "Bureau / local pro"]},
  {"question": "Rez-de-chaussée ?", "choices": ["RDC prioritaire, étages OK", "RDC obligatoire", "Peu importe"]},
  {"question": "Que privilégier ?", "choices": ["Proximité transports", "Prix le plus bas", "Surface", "Calme"]}
]}
```

**Mixte (natif + riche)** — la forme à privilégier si l'extension est active :

```json
{"controles": [
  {"type": "multi", "nom": "zone", "titre": "Zone / arrondissements",
   "options": ["Lyon 3e", "Lyon 6e", "Lyon 7e", "Villeurbanne"]},
  {"type": "slider", "nom": "budget_max", "titre": "Budget maximum",
   "min": 100000, "max": 900000, "pas": 25000, "unite": "€", "defaut": 400000},
  {"type": "plage", "nom": "surface", "titre": "Surface",
   "min": 20, "max": 300, "pas": 5, "unite": "m²", "defaut": [40, 120]},
  {"type": "slider", "nom": "distance_metro", "titre": "Distance max au métro",
   "min": 100, "max": 1500, "pas": 50, "unite": "m", "defaut": 500,
   "pistes": ["à pied", "5 min", "10 min", "15 min"]},
  {"type": "choix", "nom": "rdc", "titre": "Rez-de-chaussée ?",
   "options": ["RDC prioritaire, étages OK", "RDC obligatoire", "Peu importe"]}
]}
```

Validé et sérialisé par `profil-client/controles.py` (`valider_panneau` puis
`rendre_sortie`). Exemple exécutable : `python3 profil-client/controles.py demo`.

## 5. Garde-fous

- Ne jamais bloquer la recherche sur un panneau : si `clarify` est indisponible,
  poser UNE question simple en texte, ou chercher avec le brief par défaut en
  le disant.
- Extension riche absente → repli sur les choix natifs (fourchettes de budget,
  tranches de surface). Le panneau marche dans tous les cas.
- Le panneau cadre la collecte, il ne remplace pas la qualification.
- Ne jamais présenter un prix d'annonce comme vérifié.
- 2 à 4 questions suffisent dans la plupart des cas.

## 6. Vérification (« fini quand »)

- Demande INCOMPLÈTE → un `clarify` AVANT tout appel à la collecte ;
  demande COMPLÈTE ou mode auto → AUCUN `clarify`, collecte directe.
- Un contrôle riche produit une réponse TEXTE normalisée arrivant via
  `/api/clarify/respond`.
- Un panneau posé via `visee_protocole.poser(...)` ouvre la carte
  automatiquement (`tests/verify-visee-auto.sh`, JS sous jsdom) ; sans clarify
  en attente, rien ne s'ouvre.
- Tests : `bash tests/verify-controles.sh` et `bash tests/verify-visee-auto.sh`.
