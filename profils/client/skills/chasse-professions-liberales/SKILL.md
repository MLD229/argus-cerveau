---
name: chasse-professions-liberales
description: >-
  Procédure de chasse « Signature Libérale » — trouver en France des biens
  pouvant accueillir des professions libérales (cabinets médicaux,
  paramédicaux, avocats…). Lyon est la zone par défaut ; toute ville de
  France est couverte si le client la nomme. À utiliser dès que le client
  demande des biens, des locaux, des appartements en RDC ou en étage
  susceptibles de devenir ou d'être déjà un cabinet. Sources autorisées :
  Bien'ici (flux JSON public), recherche web, DVF. Interdit absolu :
  Leboncoin, Logic-Immo, tout contournement anti-bot. Inclut la procédure
  technique des outils /opt/tools
  (bienici.py, dvf.py, dpe.py, geocode.py, moteur.py) et la référence flux
  `references/bienici-flux.md`.
version: 2.0.0
author: Argus Immo — profil client
license: MIT
metadata:
  hermes:
    tags: [chasse, professions-liberales, rdc, lyon, bienici, cabinet]
    category: recherche
---

# Skill — CHASSE SIGNATURE LIBÉRALE

> Procédure métier du profil client. Règle fondamentale : chercher le
> POTENTIEL DE TRANSFORMATION en cabinet, pas seulement la destination actuelle.
> Zone, surface, priorités, format de sortie et garde-fous : voir SOUL.md
> (source unique — ne pas les répéter ici).

## 1. Étape 0 — VÉRIFIER L'OUTIL AVANT TOUT (indispensable)

⚠️ **L'outil existe : `/opt/tools/bienici.py`** (monté en lecture seule).
NE JAMAIS réécrire un appel direct à l'API Bien'ici : l'outil le fait mieux
(il résout la zone et construit `filters` correctement — un appel « à la main »
renvoie les ~950 000 annonces de France entière, la zone étant ignorée).

```bash
ls /opt/tools/
# → bienici.py dvf.py dpe.py geocode.py _http.py moteur.py

# Test de vie (doit renvoyer une liste avec "Lyon 6e" et son zoneIds) :
python3 /opt/tools/bienici.py zone "Lyon 6"
```

Si ce test échoue → s'arrêter et le signaler (ne pas bricoler un accès direct).

## 2. Résoudre la zone — OBLIGATOIRE

Sans `zoneId` résolu, le flux ignore le filtre et renvoie la France entière.
L'outil choisit le bon arrondissement quand le texte contient un numéro
(« Lyon 6 » → Lyon 6e, pas Lyon entier). Répéter pour chaque zone à couvrir.

```bash
python3 /opt/tools/bienici.py zone "Lyon 6"     # → {... "zoneIds": ["-10679"] ...}
```

## 3. Interroger Bien'ici

Types en français, traduits par l'outil (`appartement`→flat, `bureau`→office,
`local commercial`→commercial). Un type inconnu lève une erreur — jamais
0 annonce en silence.

```bash
# Priorité 1 — RDC (toutes destinations) : ratisser large puis filtrer.
python3 /opt/tools/bienici.py annonces --zone "Lyon 6" \
    --transaction buy --types appartement bureau "local commercial" \
    --surface-min 30 --surface-max 200

# Priorité 3 — locaux pro / bureaux en étage :
python3 /opt/tools/bienici.py annonces --zone "Lyon 6" \
    --transaction buy --types bureau "local commercial" \
    --surface-min 30 --surface-max 200
```

> Sous `execute_code`, on peut importer l'outil (pratique pour boucler sur
> plusieurs zones) — ajouter `/opt/tools` au `sys.path` :
> ```python
> import sys; sys.path.insert(0, "/opt/tools")
> from bienici import chercher_annonces, resoudre_zone
> ```

Résultat = JSON normalisé (format partagé) : `surface`, `prix`, `etage`, `rdc`,
`ascenseur`, `url_annonce`, `date_modification`, `prix_baisse`. Champs absents
→ `fiabilite: a_verifier`, jamais inventés.

> Le filtre RDC (`--rdc`) s'applique en local (`floor == 0`). Un appartement en
> RDC peut être annoncé SANS activité pro : c'est une cible à part entière.

### Procédure technique — consolidation

> Règle fondatrice : **collecte et calcul en Python pur, jamais un LLM pour
> produire un chiffre**. Chaque script sort du JSON structuré ; en échec, un
> JSON `{"erreur":...,"url":...}` + code 2 — jamais de trace brute.

1. **Paginer** — le CLI ne renvoie qu'**UNE page** (size=40). `nb_annonces` ne
   porte que sur la page reçue, `total_correspondant` sur la requête complète ;
   les filtres **LOCAUX** (dont `--rdc`) ne s'appliquent QU'À cette page. Pour
   un résultat complet, boucler `chercher_annonces(..., offset=n*40)` jusqu'à
   épuiser `total`. Détail flux : `references/bienici-flux.md`.
2. **Besoin « proche de <repère> »** (métro, gare, place) : la fiche normalisée
   n'a pas de coordonnées → rejouer la requête et lire le BRUT pour
   `blurInfo.position` (voir `references/bienici-flux.md`).
3. **Enrichir si demandé** : prix réel via DVF (`dvf.py`, commune `69386` pour
   Lyon 6e), DPE (`dpe.py`), ou tout-en-un `moteur.py`.

### Adresse — le flux Bien'ici n'en fournit PAS

Le flux public n'expose **aucune adresse rue** : seulement `city`,
`postalCode`, `district.libelle` et une position **floutée**
(`blurInfo.position`, rayon 50–250 m ; `1000` = centroïde d'arrondissement,
`addressKnown == false`).

- **Le titre/la description citent souvent rue + numéro** → cette adresse est
  plus fiable que le reverse-BAN ; la géocoder (`geocode.py`) et utiliser SA
  distance.
- Repli : reverse-géocodage BAN
  `https://api-adresse.data.gouv.fr/reverse/?lat=<lat>&lon=<lon>&limit=1`,
  **toujours marqué « approximatif »**.
- Si `addressKnown == false` → point = centroïde → « adresse non communiquée
  par l'annonce » (ne pas afficher de voie factice).

### Pièges durs (vérifiés) — à appliquer systématiquement

- `premises` n'est PAS dans `TYPES_VALIDES` du CLI : toute requête filtrée par
  `--types` perd les locaux professionnels **sans le dire**. Pour
  « local / bureau / cabinet », appeler le flux SANS `propertyType` puis trier
  sur le champ retourné.
- `floor` peut **contredire le texte** (annonce `floor == 0` dont la description
  dit « 1er étage ») → croiser titre + description avant de trancher.
- RDC / RDC surélevé / destination n'existent PAS dans les champs structurés :
  les qualifier sur le **texte** (« RDC surélevé », « surélevé »…). Si l'annonce
  ne le précise pas → « à confirmer », ne jamais l'affirmer.
- **Prix bas = souvent un montage** : viager (`lifeAnnuityAgeOfMan`/`…Woman`/
  `lifeAnnuityMonthlyAllowance`), vente à terme occupée, fonds de commerce,
  cession de bail → qualifier AVANT de présenter.
- **Doublons** : un même bien est souvent diffusé plusieurs fois (ids
  différents) et en plusieurs types (`flat` ET `office`/`premises` au même
  point) → le signaler.
- `programme` = programme neuf multi-lots (prix/surfaces en LISTES) → écarter
  pour un bien unique ; normaliser `price`/`surfaceArea` (peuvent être des listes).
- **Distance transport** : ne PAS reprendre le « à X m du métro » de l'annonce —
  le **calculer** depuis la position (ou la rue citée) vers le **nœud de
  station**, marqué approximatif. Ancres vérifiées : Place Jean Jaurès (ligne B)
  = 45,73758 / 4,83733 ; Brotteaux (ligne B) = 45,7670 / 4,8594.
- **Plafond de prix ambigu** : ne pas filtrer tant que le plafond n'est pas
  certain — collecter sans `minPrice`/`maxPrice` puis segmenter.
- **Ascenseur** : `hasElevator` souvent absent (locaux/bureaux) → écrire
  `n.c.`, jamais « non ». Pour un RDC, l'ascenseur est sans objet.
- **Attribution agence** : `accountDisplayName` souvent absent ; le chemin de
  `photos[].url_photo` contient le slug agence → utile pour nommer la source.
- **INTERDIT** : Leboncoin (403 + DataDome), Logic-Immo (DataDome). SeLoger via
  Playwright = voie modérée, non activée.

> Référence complète (endpoints, champs bruts, pagination, ancres transport,
> exemples de code) : `references/bienici-flux.md`.

## 4. Recherche multi-source

Objectif du client : retrouver le MÊME bien chez d'autres agences /
propriétaires, pour repérer les doublons et le bien vendu en direct.

1. Bien'ici est la source principale (flux JSON). Récupérer l'URL exacte de
   l'annonce (`url_annonce`).
2. `web_search` avec des indices précis — adresse ou rue, surface, nombre de
   pièces, prix, type, « cabinet » / « local pro ». Exemple :
   `"<rue> Lyon 6" local professionnel 78 m² à vendre`.
3. Consolider : un même bien apparaît souvent dans plusieurs agences (mandat
   partagé). Lister les URLs sous la même fiche, sans dupliquer le bien.

⚠ **Limite honnête (à dire au client)** : l'exhaustivité multi-portails n'est
pas garantie. On couvre Bien'ici + la recherche web + DVF. Dire que la
couverture est partielle plutôt que de prétendre à l'exhaustivité.

## 5. Vérification (« fini quand »)

- La zone a été résolue via l'outil (`bienici.py zone "<ville/arrondissement>"`),
  et la ville couverte est bien celle demandée (Lyon par défaut).
- Chaque bien a : adresse (ou niveau de précision), surface, prix, étage,
  type, destination, lien, et fiabilité.
- RDC / RDC surélevé / ascenseur sont qualifiés ou marqués « à confirmer ».
- Les biens vendus sont croisés avec d'autres sources quand c'est possible.
- Un blocage éventuel est signalé comme échec propre, sans donnée inventée.
