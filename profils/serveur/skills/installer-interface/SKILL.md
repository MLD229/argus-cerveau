---
name: installer-interface
description: >-
  Installer, mettre à jour et démarrer l'interface web Argus sur la machine.
  À utiliser dès que l'utilisateur dit « installe l'interface », « mets en place
  l'application », « ça ne démarre pas », « donne-moi l'adresse ». Rend toujours
  l'adresse à ouvrir et la marche à suivre pour l'installer sur téléphone.
version: 1.0.0
author: Argus — profil serveur
license: MIT
metadata:
  hermes:
    tags: [installation, interface, serveur, pwa]
    category: gestion
---

# Skill — INSTALLER L'INTERFACE

## Le dépôt de l'interface

L'interface vit dans un dépôt Git **séparé du cerveau** :

```
git@github.com:MLD229/argus-ui.git       (interface + petit serveur + PWA)
```

Ce dépôt contient l'interface complète : la page, le style, la logique, le
service worker (PWA), les icônes, et le serveur qui sert le tout et parle à
l'agent confiné.

## Où l'installer

Par convention sur la machine cliente :

```
~/argus-ui/
```

## Installation (à faire avec le terminal)

```bash
# 1. Récupérer (ou mettre à jour) l'interface
if [ -d ~/argus-ui/.git ]; then
  git -C ~/argus-ui pull --ff-only
else
  git clone git@github.com:MLD229/argus-ui.git ~/argus-ui
fi

# 2. Démarrer / vérifier
cd ~/argus-ui && ./argus-ui
```

`./argus-ui` fait tout : démarre le serveur s'il ne tourne pas, vérifie que
l'agent confiné tourne, configure l'accès extérieur, et **affiche l'adresse**.

## Vérifier que ça marche vraiment (pas seulement que ça a démarré)

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/api/sante
# attendu : 200
```

Puis l'accès extérieur : ouvrir l'adresse fixe et vérifier qu'elle répond.

## Rendre l'accès extérieur FIXE (indispensable pour une appli installée)

Le piège à éviter : un tunnel éphémère (cloudflare gratuit) change d'adresse à
chaque redémarrage → l'appli installée sur le téléphone pointe dans le vide.

Solution : `tailscale serve`, qui donne une adresse **permanente**.

```bash
tailscale serve --bg --https=443 http://127.0.0.1:8080
tailscale serve status      # doit afficher l'adresse https://<machine>.<tailnet>.ts.net
```

L'adresse obtenue est figée et survit au redémarrage de la machine.

## Ce que tu rends à l'utilisateur

Toujours sous cette forme :

```
Interface Argus : EN LIGNE

Adresse à ouvrir : https://<adresse-fixe>

Sur votre téléphone :
  1. Installer l'application Tailscale et se connecter au même compte
  2. Ouvrir l'adresse ci-dessus
  3. Menu du navigateur → « Ajouter à l'écran d'accueil »

L'icône Argus apparaît alors comme une application. L'adresse ne change jamais.
```

## Pièges connus (vécus)

1. **Ne jamais changer l'adresse une fois installée.** Une appli PWA est liée à
   son adresse : la modifier casse l'installation et l'utilisateur doit tout
   refaire. Si un changement est vraiment nécessaire : prévenir AVANT.
2. **Le navigateur garde l'ancienne version en cache.** Après une mise à jour
   de l'interface, l'utilisateur ne voit pas tout de suite le changement :
   lui faire **fermer complètement l'application** (la balayer des applications
   récentes) puis la rouvrir.
3. **Le fichier du service worker** (`sw.js`) contient un numéro de version
   (`CACHE = 'argus-coquille-vN'`). Après avoir modifié des fichiers de
   l'interface, il faut **incrémenter ce numéro**, sinon les téléphones déjà
   installés gardent l'ancienne version indéfiniment.
4. **Le serveur de l'interface doit joindre l'agent confiné** (le conteneur).
   S'il ne répond pas, regarder d'abord si le conteneur tourne —
   voir la skill `sante-serveur`.
