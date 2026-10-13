---
name: fichiers-sous-cerveau
description: >-
  Déposer et retrouver des FICHIERS et IMAGES dans le sous-cerveau (vault).
  À utiliser quand le client dit « stocke-moi ce fichier/cette image, tu me le
  ressortiras », « garde ça », « retrouve-moi la photo/le document de X », ou
  quand un document utile à la chasse doit être conservé (facture de charges,
  plan, DPE, photo d'une vitrine, bail, règlement de copropriété). Le dépôt et
  le rappel passent par /opt/tools/fichiers.py (index cherchable par mots-clés).
version: 1.0.0
author: Argus Immo — profil client
license: MIT
metadata:
  hermes:
    tags: [fichiers, images, memoire, vault, stockage]
    category: memoire
---

# Skill — FICHIERS & IMAGES (dépôt / rappel)

> Le client peut te confier un fichier ou une image : « garde ça », « tu me le
> ressortiras ». Tu les déposes dans le sous-cerveau, indexés, et tu les
> retrouves plus tard par mots-clés. La mémoire, c'est l'INDEX, pas le dossier.

## Déposer un fichier / une image

Quand le client te donne un fichier (ou un chemin vers un fichier) :

```bash
python3 /opt/tools/fichiers.py deposer \
    --chemin "<chemin du fichier à garder>" \
    --titre "<titre court et clair>" \
    --description "<à quoi ça sert, en 1 phrase>" \
    --mots-cles "mot1,mot2,mot3" \
    --source "client"
```

Règles de dépôt :
- **Titre explicite** : « Facture charges rue Sully 2025 », pas « doc1 ».
- **Mots-clés choisis pour la RECHERCHE future** : le lieu, le type de doc, le
  sujet (ex. `charges,syndic,sully,copropriete`). Ce sont eux qui permettront de
  le ressortir — choisis-les comme tu formulerais la question plus tard.
- Le fichier est **copié** dans le vault : l'original n'est pas touché.
- Ne dépose QUE ce qui a une valeur durable (document, photo, plan, référence).
  Pas de fichier temporaire.

## Retrouver un fichier

Quand le client demande « la photo de... », « le document sur... » :

```bash
python3 /opt/tools/fichiers.py chercher --q "charges sully"
```

Puis, avec l'`id` obtenu, récupère le **chemin réel** (à lire / afficher) :

```bash
python3 /opt/tools/fichiers.py montrer <id>
```

Et pour tout voir :

```bash
python3 /opt/tools/fichiers.py lister
```

## Comment répondre au client

- Donne le **titre**, la **date de dépôt**, le **type** (image/document) et le
  **chemin** ou le contenu utile.
- Si plusieurs fichiers correspondent, liste-les (titre + date) et demande lequel.
- Si un fichier n'est PAS dans l'index : dis « je n'ai pas ce fichier en
  mémoire » — n'invente jamais un fichier ni une image.

## Garde-fous

- On ne stocke pas de données personnelles sensibles au-delà du nécessaire à la
  chasse ; pas de mots de passe, pas de pièces d'identité.
- Ne dis jamais que tu « vois » une image si tu n'as pas pu lire son contenu :
  l'index contient les métadonnées, pas une analyse visuelle.
- Un fichier déposé reste la propriété du client : tu peux le citer, pas le
  divulguer hors du vault.
