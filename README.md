# ARGUS — cerveaux immobiliers (écosystème complet)

> **Trois cerveaux, zéro interface.** Installables partout : terminal, UI web,
> ou n'importe quel canal de messagerie.
>
> Ce dépôt n'est **pas une application** : c'est un ensemble de **profils Hermes
> packagés** (format natif `distribution.yaml`) qui s'installent en une
> commande. L'interface est un détail interchangeable.

## Les trois cerveaux

| Profil | Rôle | Parle au client ? | Outils |
|---|---|---|---|
| **chef** | Comprend la demande, route vers les skills/outils/sous-agents, agrège, répond | **Oui** — le seul | Tous (terminal, cron, web, delegation…) |
| **veille** | Recherche lourde et réutilisable, en arrière-plan, produit des rapports | Non | web, recherche, code |
| **client** | « Signature Libérale » : trouve des biens pour un particulier non technique | Oui (c'est son client à lui) | Métier seul (pas de terminal/cron) |

Le **client** est le profil livrable (celui qu'on donne au particulier) ;
**chef** et **veille** sont l'outillage d'agence.

### Qui parle à qui

```
        LE CLIENT FINAL
              │
              ▼
        ┌──────────┐
        │   chef   │  ← seul agent exposé au client
        └────┬─────┘
             │ skills · outils Python · sous-agents temporaires (delegate_task)
             ▼
     ┌───────────────┐        ┌──────────┐
     │ sous-cerveau  │◄───────│  veille  │  arrière-plan, aucun contact client
     │   (vault)     │        └──────────┘
     └───────────────┘

   ┌──────────┐
   │  client  │  profil autonome livré au particulier (Signature Libérale)
   └──────────┘
```

## Installation

### Tout l'écosystème, en une commande

```bash
git clone git@github.com:MLD229/argus-cerveau.git
cd argus-cerveau
./installer-tout.sh
```

Puis fournir la clé de chaque profil (le script affiche la commande) :

```bash
for p in argus-chef argus-veille argus-client; do
  cp ~/.hermes/profiles/$p/.env.EXAMPLE ~/.hermes/profiles/$p/.env
done
$EDITOR ~/.hermes/profiles/argus-client/.env    # renseigner DEEPSEEK_API_KEY
```

Essais :

```bash
hermes -p argus-chef   chat                                      # l'agent d'agence
hermes -p argus-client -z "un local pour mon cabinet à Lyon 6e"
hermes -p argus-veille -z "prépare une fiche marché sur Lyon 6e"
```

### Un seul profil

```bash
./installer-tout.sh client          # installe seulement 'argus-client'
./installer-tout.sh --check         # état, sans rien installer
```

Ou directement, sans le script :

```bash
hermes profile install ./profils/client --name argus-client --alias
```

### Le préfixe des noms

Les profils s'installent sous `argus-chef`, `argus-veille`, `argus-client`.
Le préfixe évite la collision avec un profil local qui s'appellerait déjà
`chef` ou `client` — **piège réel** : sans préfixe, l'installation écrase un
profil existant du même nom. Pour changer :

```bash
ARGUS_PROFILE_PREFIX="argus-immo-" ./installer-tout.sh
```

## Les outils Python (étape indispensable)

`installer-tout.sh` appelle `installer.sh`, qui pose les outils et **vérifie par
un vrai appel**. Les skills les appellent par **chemin absolu**
(`/opt/tools/bienici.py`) : sans cette étape, l'agent ne trouve pas son outil et
**réinvente l'appel à la main** — ce qui échoue silencieusement (la zone est
ignorée, on récupère les ~950 000 annonces de France entière au lieu du
quartier). C'est un piège documenté.

```bash
./installer.sh                       # /opt/tools (sudo si nécessaire)
TOOLS_DIR=~/argus-tools ./installer.sh   # emplacement personnalisé
./installer.sh --check               # vérifie sans copier
```

Une interface web doit monter ce dossier en lecture seule pour l'agent.

## Structure

```
argus-cerveau/
├── installer-tout.sh       ← installe les 3 profils + les outils
├── installer.sh            ← pose les outils Python + test de vie
├── profils/
│   ├── chef/               distribution.yaml · SOUL.md · config.yaml · skills/
│   ├── veille/             distribution.yaml · SOUL.md · config.yaml
│   └── client/             distribution.yaml · SOUL.md · config.yaml · skills/ · outils/
└── docs/                   architecture · contrat des outils · cadre légal
```

Un dépôt = plusieurs profils, mais **`hermes profile install` installe UN
profil**. C'est pourquoi `installer-tout.sh` fait la boucle ; chaque
`profils/<nom>/` est un dossier de distribution autonome.

## Ce qui suit un cerveau, et ce qui reste local

Propriété centrale du format « distribution » :

| Mis à jour par le cerveau | Jamais écrasé (local à l'utilisateur) |
|---|---|
| `SOUL.md`, `config.yaml`, `skills/`, `outils/` | `memories/`, `sessions/`, `state.db`, `.env`, `logs/` |

`hermes profile update argus-client` rafraîchit le cerveau **sans toucher** à
l'historique, aux souvenirs ni aux clés du client.

## Limite connue : chemins en dur dans le SOUL de `veille`

Le `profils/veille/SOUL.md` cite des chemins absolus de la machine d'origine :

```
/home/momo/projects/argus-immo/
/home/momo/Obsidian/ArgusImmoVault/
```

C'est **volontaire et non corrigé** : `veille` est l'agent d'agence, lié à
l'installation de l'opérateur (il lit le dépôt et écrit dans le sous-cerveau
Obsidian). Il n'est pas destiné à être installé ailleurs sans adaptation.

Pour un déploiement sur une autre machine, éditer ces chemins dans le SOUL
après installation — ou remplacer par des variables (`$ARGUS_VAULT`).
`chef` et `client` n'ont pas cette dépendance.

## Brancher une interface

Aucun cerveau ne sait de quelle interface il est appelé. N'importe quelle porte
d'entrée fonctionne tant qu'elle sait invoquer un profil Hermes :

- **Terminal** : `hermes -p argus-client chat`
- **UI web** : un hôte qui lance le profil et affiche son flux
- **Messagerie** : le gateway Hermes (Telegram, Discord…)
- **Programme** : tout code qui exécute `hermes -p argus-client -z "<question>"`

### Ce que l'interface peut ajouter (confort, non requis)

- **Masquer la mécanique interne** : si l'interface affiche raisonnement et
  appels d'outils (comme hermes-webui par défaut), elle doit les replier. Les
  SOUL l'interdisent à l'agent, mais une interface bavarde peut l'exposer quand
  même — c'est un réglage **d'interface**, pas du cerveau.
- **Un panneau de critères riche** (curseurs/plages) : la skill
  `filtre-recherche` décrit un protocole optionnel. Sans interface compatible,
  l'agent retombe proprement sur des questions à choix.
- **La dictée vocale** (bouton micro).

**Le cerveau est portable, l'habillage se refait par interface.**

## Documentation

| Document | Contenu |
|---|---|
| `docs/architecture.md` | pourquoi un seul agent qui parle, et le coût d'une cascade |
| `docs/contrat-outils.md` | les modules Python : signatures et format de sortie |
| `docs/legal.md` | sources autorisées/interdites, la règle « gratuit et légal » |

## Licence

MIT.
