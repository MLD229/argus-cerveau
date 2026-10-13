---
name: notifications-alertes
description: >-
  Consulter et expliquer les notifications de veille (nouvelles annonces,
  baisses de prix, ventes DVF, alertes portail). À utiliser dès que le client
  demande « quelles notifications a-t-on reçues ? », « qu'est-ce qui est
  nouveau ? », « montre-moi mes alertes », « des nouveautés depuis hier ? ».
  Le magasin est lu via /opt/tools/notifications.py (lecture seule côté agent).
version: 1.0.0
author: Argus Immo — profil client
license: MIT
metadata:
  hermes:
    tags: [notifications, veille, alertes, nouveautes]
    category: recherche
---

# Skill — NOTIFICATIONS & ALERTES

> Le client veut savoir ce qui est NOUVEAU (nouvelles annonces, baisses de prix,
> ventes, alertes portail). Les notifications sont produites en arrière-plan par
> la veille et le connecteur d'alerte e-mail, et stockées dans un magasin local.

## Quand l'utiliser

- « Quelles notifications a-t-on reçues ? »
- « Qu'est-ce qui est nouveau ? »
- « Montre-moi mes alertes / mes nouveautés depuis hier. »
- « Est-ce qu'il y a des baisses de prix ? »

## Comment lire (via execute_code → /opt/tools)

Le magasin est **en lecture** pour l'agent (route en écriture réservée au
système). Utiliser l'outil :

```bash
python3 /opt/tools/notifications.py resume           # compteurs (badge)
python3 /opt/tools/notifications.py lister --limite 20
python3 /opt/tools/notifications.py lister --non-lues
python3 /opt/tools/notifications.py lister --type annonce
```

Réponse : JSON `resultat.notifications` = liste de notifications, chacune
avec `type`, `severite` (info/important/urgent), `titre`, `corps`, `source`,
`cree_le`, `donnees` (parfois `url_annonce`).

## Comment répondre au client

1. **Résume d'abord** : « X nouvelles notifications, dont Y non lues. »
2. **Groupe par type** : annonces / baisses de prix (marche) / ventes / alertes.
3. Pour chaque notification utile, donne : le titre, la **source**, la **date**
   et — si présente — le **lien** (`donnees.url_annonce`).
4. **Priorise** : mets en avant les `important` et `urgent`, et les baisses de
   prix (levier de négociation).
5. Termine par une action proposée : « voulez-vous que je qualifie ces biens
   selon votre brief ? »

## Garde-fous

- Les notifications proviennent de sources variées : **rappelle la source** et
  ne présente jamais un prix d'annonce comme un prix vérifié.
- Si le magasin est vide : dis « aucune notification pour le moment » et propose
  de lancer une recherche — n'invente rien.
- N'écris PAS dans le magasin depuis le chat (l'agent est en lecture seule).
- Les notifications sont un **radar** : elles signalent, elles ne qualifient pas.
