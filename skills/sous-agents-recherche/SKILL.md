---
name: sous-agents-recherche
description: >-
  Lancer les recherches via des SOUS-AGENTS temporaires (outil de délégation)
  pour aller vite, en parallèle, sans bloquer la conversation : le client peut
  continuer à parler et à ajouter des critères pendant que la recherche tourne.
  À utiliser dès qu'une demande de biens exige plusieurs axes indépendants
  (plusieurs sources, plusieurs villes, plusieurs questions de fond : prix vs
  marché, transports, multi-sources d'un bien). Complète la skill
  chasse-professions-liberales (qui dit QUOI chercher) en disant COMMENT
  paralléliser sans perdre le client ni inventer.
version: 1.0.0
author: Argus Immo — profil client
license: MIT
metadata:
  hermes:
    tags: [recherche, sous-agents, delegation, parallelisme, rapidite]
    category: recherche
---

# Skill — SOUS-AGENTS DE RECHERCHE

> Le client veut une réponse UTILE VITE, et il veut pouvoir continuer à discuter
> pendant que tu cherches. La délégation sert ces deux buts. Ce n'est PAS une
> raison d'en faire trop : les bornes ci-dessous sont dures.

## Quand déléguer

Délègue seulement quand il y a **2–3 axes réellement indépendants**, par ex. :

- plusieurs sources à balayer en parallèle (Bien'ici + recherche web + DVF) ;
- plusieurs villes / arrondissements demandés en une fois ;
- une question de fond séparée de la collecte (comparer au marché DVF,
  distance aux transports d'un bien retenu, multi-sources d'un même bien).

Ne délègue PAS :

- une recherche unique et simple (tu la fais directement, c'est plus rapide) ;
- le panneau VISÉE (c'est toi, avec le client, pas un sous-agent) ;
- une question qui a besoin du contexte de la conversation (un sous-agent ne
  connaît RIEN de cet échange).

## Bornes dures (non négociables)

- **3 sous-agents maximum** lancés en même temps.
- **UN seul** sous-agent par axe. Jamais de relance du même axe, jamais de
  boucle, jamais de sous-agent de sous-agent.
- Si un sous-agent ne rend rien d'utilisable **après sa seule tentative** :
  dis-le et réponds avec ce que tu as. Ne relance pas, ne l'attends pas.

## Le brief d'un sous-agent (auto-suffisant)

Un sous-agent ne voit ni la conversation, ni le client. Le brief doit contenir :

1. le critère précis (zone/ville, surface, budget, rez-de-chaussée ou non) ;
2. les sources AUTORISÉES (Bien'ici flux JSON, recherche web, DVF) et les
   interdits (Leboncoin, Logic-Immo, tout contournement anti-bot) ;
3. le format de retour voulu (les champs de la chasse : adresse, surface,
   prix, étage, type, travaux, points forts/vigilance, lien) ;
4. la règle anti-invention (jamais de prix/adresse/téléphone inventé ;
   « à confirmer » si absent) ;
5. le budget : revenir vite, au maximum ~30 s de travail, quitte à rendre un
   résultat partiel honnête.

Exemple de brief : « Cherche sur Bien'ici (flux JSON public) les biens en
rez-de-chaussée ou locaux professionnels de 40 à 120 m² à Bordeaux, budget
400 000 € max. Rends au maximum 3 biens au format : adresse | surface | prix |
étage | type | travaux | points forts | vigilance | lien. N'invente aucun
champ absent : écris "à confirmer". Ne consulte ni Leboncoin ni Logic-Immo.
Reviens en moins de 30 secondes. »

## Pendant que les sous-agents travaillent

1. Accuse réception en une phrase et dis CE QUE tu lances (« je lance la
   recherche sur Bordeaux et la comparaison au marché en parallèle »).
2. **Reste disponible** : réponds aux questions du client, prends en compte les
   critères qu'il ajoute en cours de route.
3. Quand les retours arrivent : tu **consolides et réécris** (3 biens max, triés
   par priorité, sourcés, format client). Jamais de sortie brute de sous-agent.

## Pièges

- Ne pas coller la sortie d'un sous-agent telle quelle : elle est dans SON
  format et peut contenir des détails techniques internes.
- Ne pas attendre silencieusement : le client croit que tu es bloqué.
- Ne pas déléguer pour « faire plus » : si un seul appel suffit, fais-le.
