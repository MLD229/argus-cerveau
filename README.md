# ARGUS — cerveau immobilier « Signature Libérale »

> **Le cerveau seul.** Aucune interface. Utilisable en terminal, derrière une
> UI web, ou via n'importe quel canal de messagerie.
>
> Ce dépôt n'est **pas une application** : c'est un **profil Hermes packagé**
> (`distribution.yaml`) qu'on installe en une commande. L'interface est un
> détail interchangeable.

## Ce que c'est

Un agent qui aide un particulier non technique à trouver, partout en France,
des biens pouvant accueillir une **profession libérale** (cabinet médical,
paramédical, avocat…). Lyon est la zone par défaut ; toute ville nommée est
couverte.

Décisions de conception (ne pas les contredire) :

- **Un seul agent** parle au client. Pas de cascade de profils.
- Les procédures du quotidien sont des **skills**.
- Le volume se traite par **sous-agents temporaires** (`delegate_task`),
  parallèles et jetables — jamais un profil par métier.
- **Collecte et calcul en Python pur** (`outils/`), jamais un LLM pour
  produire un chiffre.
- Le client **ne voit jamais** la mécanique interne (commandes, chemins,
  raisonnement). Seule la réponse finale est visible.
- **Gratuit et légal d'abord** : refus des anti-bot et des CGU interdites
  (Leboncoin, Logic-Immo).

## Installation

```bash
# 1. Installer le cerveau (profil Hermes nommé « argus »)
hermes profile install github.com/MLD229/argus-cerveau --alias

# 2. Fournir la clé du modèle
cp ~/.hermes/profiles/argus/.env.EXAMPLE ~/.hermes/profiles/argus/.env
$EDITOR ~/.hermes/profiles/argus/.env      # renseigner DEEPSEEK_API_KEY

# 3. Rendre les outils Python accessibles à l'agent
git clone https://github.com/MLD229/argus-cerveau /tmp/argus-cerveau
/tmp/argus-cerveau/installer.sh

# 4. Parler au cerveau
hermes -p argus chat
```

En une fois, sans session interactive :

```bash
hermes -p argus -z "trouve un bien pour mon cabinet à Lyon 6e, 400 000 € max"
```

## Pourquoi `installer.sh` en plus ?

`hermes profile install` copie le cerveau (SOUL, config, skills, outils) dans
le profil. Mais les skills appellent les outils par un **chemin absolu**
(`/opt/tools/bienici.py`). `installer.sh` pose les scripts à cet endroit et
**vérifie par un vrai appel** que ça répond.

Sans cette étape, l'agent ne trouve pas son outil et **réinvente l'appel à la
main** — ce qui échoue silencieusement (la zone est ignorée, on récupère les
~950 000 annonces de France entière). C'est un piège documenté.

```bash
./installer.sh --check              # vérifie sans rien copier
TOOLS_DIR=~/argus-tools ./installer.sh   # emplacement personnalisé
```

## Structure

```
argus-cerveau/
├── distribution.yaml   ← le manifeste : nom, version, prérequis, ce qui suit
├── SOUL.md             ← l'identité et les règles de l'agent
├── config.yaml         ← modèle, toolsets, réglages (sans dépendance UI)
├── .env.template       ← variables à fournir (copié en .env.EXAMPLE)
├── installer.sh        ← pose les outils Python + test de vie
├── skills/             ← les procédures métier
│   ├── chasse-professions-liberales/   (+ references/bienici-flux.md)
│   ├── filtre-recherche/               ← le panneau de critères « VISÉE »
│   ├── sous-agents-recherche/          ← déléguer les recherches proprement
│   ├── notifications-alertes/
│   └── fichiers-sous-cerveau/
├── outils/             ← Python pur : collecte et calcul (aucune clé)
└── docs/               ← documentation de référence
```

## Ce qui suit le cerveau, et ce qui reste local

C'est la propriété centrale du format « distribution » :

| Mis à jour par le cerveau | Jamais écrasé (local à l'utilisateur) |
|---|---|
| `SOUL.md`, `config.yaml`, `skills/`, `outils/` | `memories/`, `sessions/`, `state.db`, `.env`, `logs/` |

Autrement dit : `hermes profile update argus` rafraîchit le cerveau **sans
toucher** à l'historique, aux souvenirs ni aux clés du client.

## Brancher une interface

Le cerveau ne sait rien de l'interface. N'importe quelle porte d'entrée
fonctionne tant qu'elle sait appeler un profil Hermes :

- **Terminal** : `hermes -p argus chat`
- **UI web** : un hôte qui lance le profil et affiche son flux (l'UI actuelle
  du projet `argus-immo` en est un exemple)
- **Messagerie** : le gateway Hermes (Telegram, Discord…)
- **Programme** : tout code qui exécute `hermes -p argus -z "<question>"`

### Ce que l'interface doit fournir

1. **Le profil installé** (étapes 1–3 ci-dessus).
2. **Rien d'autre.** Ni base de données, ni compte, ni port.

### Ce que l'interface peut ajouter (confort, non requis)

- **Masquer la mécanique interne** : si l'interface affiche le raisonnement ou
  les appels d'outils (comme le fait hermes-webui par défaut), elle doit les
  replier. Le SOUL l'interdit à l'agent, mais une interface bavarde peut
  l'exposer quand même — c'est un réglage **d'interface**, pas du cerveau.
- **Un panneau de critères riche** (curseurs/plages) : la skill
  `filtre-recherche` décrit un protocole optionnel pour ce confort. Sans
  interface compatible, l'agent retombe proprement sur des questions à choix.
- **La dicter vocale** (bouton micro).

En résumé : **le cerveau est portable, l'habillage se refait par interface.**

## Documentation

| Document | Contenu |
|---|---|
| `docs/architecture.md` | pourquoi un seul agent, et ce que coûte une cascade |
| `docs/contrat-outils.md` | les modules Python : signatures et format de sortie |
| `docs/legal.md` | sources autorisées et interdites, la règle « gratuit et légal » |
| `outils/README.md` | utilisation directe des outils, hors agent |

## Licence

MIT.
