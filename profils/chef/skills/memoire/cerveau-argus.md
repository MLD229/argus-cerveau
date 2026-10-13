---
name: cerveau-argus
description: Tenir et enrichir le sous-cerveau d'Argus (vault Obsidian monte sur /data/vault). A charger des qu'on apprend un fait durable (source validee, decision, methode, retour client, lecon) ou avant de repondre sur un point sensible (regle, source, methode d'estimation).
---

# Ton sous-cerveau (`/data/vault`)

C'est ta **memoire longue**. Elle survit aux conversations. Tu l'entretiens
TOI-MEME, sans qu'on te le demande.

## Quand tu LIS (avant de repondre)

Avant toute reponse sur un point sensible — une regle, une source, une methode,
un historique client — tu verifies dans le vault. Ordre de lecture :

1. `00_SYSTEM/BRAIN.md` — la carte : quelles notes existent, ou regarder.
2. La note du sujet (`20_METHODE/`, `30_SOURCES/`, `40_DECISIONS/`).
3. `99_LOGS/` — la derniere entree, pour savoir ou on en etait.

Ne recopie JAMAIS le vault dans ta reponse : tu t'en sers, tu cites la source
en clair, c'est tout.

## Quand tu ECRIS (sans qu'on te le demande)

Tu ecris **UNIQUEMENT** ce qui est DURABLE et reutilisable :

| Declencheur | Ou |
|---|---|
| Une source validee / invalidee (+ pourquoi) | `30_SOURCES/<Nom>.md` |
| Une methode qui marche (etape par etape) | `20_METHODE/<Sujet>.md` |
| Une decision prise (+ la raison) | `40_DECISIONS/<Titre>.md` |
| Un fait client stable (zone, criteres, historique) | `50_CLIENTS/<Nom>.md` |
| Une lecon tiree d'un echec | `40_DECISIONS/` ou la note concernee |

Tu n'ecris **JAMAIS** : du bavardage de conversation, une donnee qui change tout
le temps (un prix, une annonce), ou ce qui existe deja ailleurs dans le projet.

## Les 5 regles d'or de l'entretien

1. **UNE idee = UNE note.** Si le sujet a deja une note, tu la COMPLETES (tu
   ajoutes), tu n'en crees pas une deuxieme.
2. **Tu mets a jour l'index.** Apres avoir cree une note, tu ajoutes une ligne
   dans `00_SYSTEM/BRAIN.md` (et dans le `_INDEX.md` du dossier concerne).
3. **Tu dates et tu sources.** Chaque fait ecrit porte sa date et d'ou il vient.
   Un fait sans source ne vaut rien.
4. **Tu ne dupliques pas.** Avant d'ecrire, tu cherches si l'info est deja la
   (grep dans le vault). Si oui : tu corriges ou tu ne fais rien.
5. **Tu ne contredis pas en silence.** Si une nouvelle info contredit une note
   existante, tu CORRIGES la note (et tu notes pourquoi ca a change), tu
   n'ajoutes pas une note contradictoire a cote.

## Ce qu'il ne faut PAS laisser arriver

- **Le vault qui gonfle** : 50 notes sur le meme sujet = echec. Une note par
  sujet, complete.
- **Les liens casses** : si tu renommes une note, tu repares les liens
  (`[[Nom]]`) qui pointaient vers elle.
- **Les notes orphelines** : toute note doit etre atteignable depuis l'index.
- **L'info perimee** : une source qui ne marche plus doit etre marquee comme
  telle, pas laissee comme si elle marchait.

## Verifier que ta memoire est saine (quand on te le demande)

Tu peux inspecter ton vault et signaler : les liens casses, les orphelins,
les manques dans l'index, les doublons, les notes non datees. Tu le fais avec
les outils normaux (lecture de fichiers, recherche de motif).

## Frontmatter standard d'une note

```markdown
---
titre: Prix au m2 Lyon 3e
type: source | methode | decision | client
maj: 2026-10-08
source: DVF (base officielle des ventes notariees)
---
```
