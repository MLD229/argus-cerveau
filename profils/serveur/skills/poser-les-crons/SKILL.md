---
name: poser-les-crons
description: >-
  Créer, mettre à jour et vérifier les tâches automatiques d'Argus (surveillance
  du serveur, veille des mises à jour, lecture du canal de commandement). À
  utiliser quand l'utilisateur dit « mets en place la surveillance », « vérifie
  que les tâches tournent », « ajoute une vérification ». Hermes n'installe PAS
  les tâches automatiques avec un profil : ce profil doit les créer lui-même.
version: 1.0.0
author: Argus — profil serveur
license: MIT
metadata:
  hermes:
    tags: [cron, automatisation, surveillance, planification]
    category: gestion
---

# Skill — POSER LES TÂCHES AUTOMATIQUES (crons)

## Pourquoi cette skill existe

Quand on installe un profil Hermes, **ses tâches automatiques ne sont PAS
installées avec**. Un profil neuf n'a aucun cron. C'est donc à ce profil de
les **poser lui-même** — sinon la surveillance n'existe pas et personne ne s'en
aperçoit avant la panne.

## Les trois tâches à poser

| Nom | Rôle | Fréquence conseillée |
|---|---|---|
| `argus-sante` | vérifie que tout répond, répare, ne parle que si problème | toutes les 15 min |
| `argus-maj-github` | signale les nouveautés du cerveau | toutes les 6 h |
| `argus-commandement` | lit la demande déposée à distance et l'exécute | toutes les 5 min |

## Comment les poser

Les scripts vivent dans `~/.hermes/scripts/`. Les créer/actualiser d'abord
(ils sont fournis avec ce profil — les copier depuis `outils/`), puis :

```
hermes cron create --name argus-sante --schedule "*/15 * * * *" \
  --script argus-sante.sh --no-agent

hermes cron create --name argus-maj-github --schedule "0 */6 * * *" \
  --script argus-maj-github.sh --no-agent

hermes cron create --name argus-commandement --schedule "*/5 * * * *" \
  --script argus-commandement.sh --no-agent
```

- `--script` prend le **nom du fichier seul** (relatif à `~/.hermes/scripts/`),
  jamais un chemin absolu : le système refuse un chemin absolu.
- `--no-agent` : la tâche lance juste le script, sans réveiller un agent.
  Plus léger, plus sûr, et le texte produit par le script est envoyé tel quel.

## Vérifier qu'elles tournent vraiment

```
hermes cron list
```

Puis forcer un passage pour voir si elles fonctionnent :

```
hermes cron run <identifiant>
```

Contrôler que `last_status` vaut `ok`. Une tâche qui existe mais ne s'exécute
jamais ne sert à rien : toujours **provoquer un passage** après l'avoir posée.

## Le point à ne pas oublier : la LIVRAISON des alertes

Par défaut, une tâche enregistre sa sortie **sans l'envoyer** : le message
reste dans un fichier que personne ne lit. Pour que l'utilisateur soit
réellement prévenu (panne, mise à jour disponible), la tâche doit avoir une
**destination** : Telegram, Discord, ou autre canal connecté.

Poser la question à l'utilisateur si aucune destination n'est configurée :
sans canal, la surveillance est muette et donc inutile.

## Règle d'or des scripts de surveillance

**Silence quand tout va bien.** Le script n'écrit rien et sort avec le code 0
s'il n'y a rien à signaler ; il n'écrit son diagnostic que s'il y a un
problème. Un watchdog qui parle à chaque passage est un watchdog qu'on ignore.
