---
name: sante-serveur
description: >-
  Vérifier que l'installation Argus fonctionne, diagnostiquer une panne et
  réparer. À utiliser quand l'utilisateur dit « ça ne marche plus », « l'appli
  ne répond pas », « vérifie le serveur », ou automatiquement en tâche de fond.
  Couvre : conteneur de l'agent, serveur de l'interface, accès extérieur,
  magasin de notifications.
version: 1.0.0
author: Argus — profil serveur
license: MIT
metadata:
  hermes:
    tags: [sante, diagnostic, panne, surveillance]
    category: gestion
---

# Skill — SANTÉ DU SERVEUR (vérifier, diagnostiquer, réparer)

## Ce qui compose l'installation

```
Navigateur / appli  →  serveur de l'interface (machine)  →  conteneur agent  →  cerveau
```

Quatre choses peuvent tomber, dans cet ordre de probabilité :
1. le **conteneur de l'agent** (le plus fragile) ;
2. le **serveur de l'interface** ;
3. l'**accès extérieur** (Tailscale) ;
4. le **magasin de notifications** (fichier partagé).

## Le script de vérification (à utiliser, ne pas réinventer)

```bash
~/.hermes/scripts/argus-sante.sh
```

- **Sortie vide, code 0** → tout va bien. C'est le cas normal.
- **Affiche un diagnostic, code 1** → il y a un problème ; le texte affiché
  est déjà rédigé pour l'utilisateur.

Il **tente de réparer** avant de conclure (relance le conteneur, le serveur,
re-pointe l'accès extérieur) et **re-vérifie** ensuite.

## Diagnostic manuel (si le script ne suffit pas)

```bash
# 1. le conteneur de l'agent tourne-t-il ?
docker ps --filter name=argus-confine --format '{{.Names}} {{.Status}}'

# 2. l'interface répond-elle en local ?
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/api/sante     # attendu 200

# 3. l'accès extérieur répond-il ?
curl -s -o /dev/null -w '%{http_code}\n' https://<adresse-fixe>/api/sante   # attendu 200
```

## Réparer

```bash
# Tout relancer
cd ~/argus-ui && ./argus-ui          # démarre interface + agent + accès
cd ~/argus-ui && ./argus-ui --status # où en est-on, quelle adresse
cd ~/argus-ui && ./argus-ui --stop   # arrêter proprement
```

Le conteneur de l'agent se relance via son propre lanceur (celui du
déploiement). S'il ne redémarre pas, regarder ses journaux :

```bash
docker logs --tail 40 argus-confine
```

## Ce que tu dis à l'utilisateur

**Tout va bien** (cas normal) :
```
Serveur Argus : tout est en ligne.
Interface : https://<adresse-fixe>
```
Une phrase suffit. Pas de détail.

**Quelque chose n'allait pas, réparé :**
```
Le serveur Argus s'était arrêté — je l'ai relancé, il répond de nouveau.
Interface : https://<adresse-fixe>
```

**Pan­ne non résolue :**
```
Le serveur Argus ne répond toujours pas.
Ce que j'ai constaté : <une phrase simple>
Ce que je propose : <action concrète>
```
Jamais de log brut, jamais de trace d'erreur, jamais de commande.

## En tâche de fond (surveillance)

Quand tu es lancé en automatique : **tu ne dis rien si tout va bien.** Tu ne
parles que si tu as réparé quelque chose ou si quelque chose ne va pas.
Une surveillance bavarde devient du bruit qu'on finit par ignorer.
